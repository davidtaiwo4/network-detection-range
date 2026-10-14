#!/usr/bin/env python3
"""
Stage 5/6 evidence adapter for Stage 7 (network range).

Transforms three raw Stage 7 artifacts into the Stage 5/6 normalized
evidence-record shape (raw_locator, canonical_id, timestamp_utc, verdict,
plus optional extension fields), so Stage 8 can consume network-range
findings through the same interface it uses for honeypot/hunt-engine
findings.

Inputs:
  --junit   test-results.xml            (pytest JUnit output)
  --fixtures tests/fixtures/public-fixtures.json  (to resolve case_id -> zone pair/service)
  --nft     evidence/<snapshot>/nftables.json     (nft -j list ruleset snapshot, optional)
  --eve     a local copy of the sensor's eve.json  (optional; see README for docker cp step)
  --out     output path for the combined JSONL evidence file

Usage:
  python3 network-range/adapter.py \
    --junit test-results.xml \
    --fixtures tests/fixtures/public-fixtures.json \
    --nft evidence/detection-proof/nftables.json \
    --eve evidence/detection-proof/eve.json \
    --out evidence/stage8-handoff.jsonl

No raw artifact is modified. This script only reads inputs and writes one
new output file. Every record's raw_locator points back to its exact
source, per the submission contract's evidence standard.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def load_fixtures(path):
    """case_id -> {source, destination, service, expected_network, expected_log_code}"""
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text())
    return {c["case_id"]: c for c in data.get("fixtures", [])}


def canonical_id(zone_pair, service, when):
    date_str = when.strftime("%Y%m%d") if when else "unknown-date"
    safe_service = service.replace("/", "") if service else "unknown-service"
    return f"{zone_pair}-{safe_service}-{date_str}"


def adapt_junit(junit_path, fixtures, now):
    """One evidence record per pytest test case."""
    records = []
    if not junit_path or not Path(junit_path).exists():
        return records
    tree = ET.parse(junit_path)
    root = tree.getroot()
    testcases = root.iter("testcase")
    for tc in testcases:
        name = tc.get("name", "")
        m = re.search(r"\[(.*?)\]", name)
        case_id = m.group(1) if m else name
        fixture = fixtures.get(case_id, {})
        source = fixture.get("source", "unknown")
        destination = fixture.get("destination", "unknown")
        service = fixture.get("service", "unknown")
        zone_pair = f"{source}-{destination}"

        failure = tc.find("failure")
        error = tc.find("error")
        verdict = "fail" if (failure is not None or error is not None) else "pass"

        records.append({
            "raw_locator": f"test-results.xml#testcase[name={name}]",
            "canonical_id": canonical_id(zone_pair, service, now),
            "timestamp_utc": now.isoformat(),
            "verdict": verdict,
            "source_layer": "pytest",
            "source_stage": "stage7-network-range",
            "extension": {
                "case_id": case_id,
                "zone_pair": zone_pair,
                "source_zone": source,
                "destination_zone": destination,
                "service": service,
                "expected_network": fixture.get("expected_network"),
                "expected_log_code": fixture.get("expected_log_code"),
            },
        })
    return records


def adapt_nft(nft_path, now):
    """One evidence record per counter-bearing rule with nonzero packets."""
    records = []
    if not nft_path or not Path(nft_path).exists():
        return records
    data = json.loads(Path(nft_path).read_text())
    for item in data.get("nftables", []):
        rule = item.get("rule")
        if not rule:
            continue
        comment = rule.get("comment")
        if not comment:
            continue
        packets = 0
        for expr in rule.get("expr", []):
            if "counter" in expr:
                packets = expr["counter"].get("packets", 0)
        if packets <= 0:
            continue  # only emit findings for rules that actually fired

        verdict = "deny" if comment.startswith("NF_") else "allow"
        records.append({
            "raw_locator": f"{nft_path}#rule[comment={comment}]",
            "canonical_id": canonical_id(comment, "nftables", now),
            "timestamp_utc": now.isoformat(),
            "verdict": verdict,
            "source_layer": "nftables",
            "source_stage": "stage7-network-range",
            "extension": {
                "rule_comment": comment,
                "packets": packets,
                "gateway_interface_expr": [
                    e for e in rule.get("expr", []) if "match" in e
                ][:1],
            },
        })
    return records


def adapt_eve(eve_path):
    """One evidence record per Suricata alert (flow events are skipped -- too
    high volume and not independently decisive; alerts are the actionable
    detection layer)."""
    records = []
    if not eve_path or not Path(eve_path).exists():
        return records
    for line in Path(eve_path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("event_type") != "alert":
            continue
        alert = evt.get("alert", {})
        src = evt.get("src_ip", "unknown")
        dst = evt.get("dest_ip", "unknown")
        zone_pair = f"{src}-{dst}"
        ts = evt.get("timestamp", "")
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            when = None

        records.append({
            "raw_locator": f"eve.json#flow_id={evt.get('flow_id')}",
            "canonical_id": canonical_id(zone_pair, "suricata-alert", when),
            "timestamp_utc": ts,
            "verdict": "alert",
            "source_layer": "suricata",
            "source_stage": "stage7-network-range",
            "extension": {
                "signature": alert.get("signature"),
                "signature_id": alert.get("signature_id"),
                "severity": alert.get("severity"),
                "src_ip": src,
                "dest_ip": dst,
                "proto": evt.get("proto"),
            },
        })
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--junit", default="test-results.xml")
    p.add_argument("--fixtures", default="tests/fixtures/public-fixtures.json")
    p.add_argument("--nft", default=None)
    p.add_argument("--eve", default=None)
    p.add_argument("--out", default="evidence/stage8-handoff.jsonl")
    args = p.parse_args()

    now = datetime.now(timezone.utc)
    fixtures = load_fixtures(args.fixtures)

    records = []
    records += adapt_junit(args.junit, fixtures, now)
    records += adapt_nft(args.nft, now)
    records += adapt_eve(args.eve)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(f"wrote {len(records)} evidence records to {out_path}")
    print(f"  from junit: {sum(1 for r in records if r['source_layer'] == 'pytest')}")
    print(f"  from nft:   {sum(1 for r in records if r['source_layer'] == 'nftables')}")
    print(f"  from eve:   {sum(1 for r in records if r['source_layer'] == 'suricata')}")


if __name__ == "__main__":
    main()
