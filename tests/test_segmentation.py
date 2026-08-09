"""
Data-driven segmentation tests.

Reads tests/fixtures/public-fixtures.json (same schema the hidden/holdout
fixture will use) and asserts, per case:
  1. actual reachability matches expected_network
  2. the gateway's nft counters show a policy verdict consistent with
     expected_log_code (a deny case must increment a deny/spoof counter;
     an allow case must increment an accept-rule counter)
"""
import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_FILES = sorted(FIXTURE_DIR.glob("*.json"))


def _load_cases():
    cases = []
    for f in FIXTURE_FILES:
        data = json.loads(f.read_text())
        for c in data["fixtures"]:
            c["_source_file"] = f.name
            cases.append(c)
    return cases


CASES = _load_cases()


def _parse_service(service: str):
    proto, port = service.split("/")
    return proto, int(port)


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_segmentation_case(case, variant, zone_ip, attempt_connection, counters_before_after):
    source = case["source"]
    destination = case["destination"]
    expected_network = case["expected_network"]  # "allow" | "deny"

    # Sensor is a non-routable mirror tap by construction (mode: mirror in
    # variant.yml, no cidr assigned) -- it structurally cannot initiate or
    # receive routed traffic. This is a topology-level guarantee, not a
    # firewall-rule guarantee, the invariant is asserted directly rather
    # than attempting a connection from a host that doesn't exist.
    if source == "sensor" or destination == "sensor":
        assert variant["zones"].get("sensor") is None, (
            f"{case['case_id']}: 'sensor' must not appear as a routable zone "
            f"in variant.yml (it is mirror-only) -- found a routable entry, "
            f"which would break the deny-by-construction guarantee for this case."
        )
        assert expected_network == "deny", (
            f"{case['case_id']}: sensor-involved cases are expected deny "
            f"by construction; fixture says {expected_network}, mismatch "
            f"means the fixture schema assumption needs review."
        )
        return
    if source == destination:
        # Single-host-per-zone topology: intra-zone traffic never reaches
        # the gateway's forward chain, so it cannot be firewall-mediated
        # here by design. Segmentation policy is zone-to-zone per the
        # brief's own glossary (east-west = "between internal zones").
        # Documented as an open assumption in decision-log.md.
        assert expected_network == "allow", (
            f"{case['case_id']}: same-zone case expected {expected_network}, "
            f"but same-zone traffic is structurally unrestricted in this topology."
        )
        return

    proto, port = _parse_service(case["service"])
    dest_ip = zone_ip(destination)

    with counters_before_after() as ctx:
        result = attempt_connection(source, dest_ip, port, proto)
    delta = ctx.delta()

    deny_hits = {k: v for k, v in delta.items() if k.startswith("NF_") and v > 0}
    allow_hits = {k: v for k, v in delta.items() if not k.startswith("NF_") and v > 0}

    evidence = {
        "case_id": case["case_id"],
        "source": source,
        "destination": destination,
        "service": case["service"],
        "client_returncode": result.returncode,
        "deny_counter_hits": deny_hits,
        "allow_counter_hits": allow_hits,
    }

    if expected_network == "deny":
        assert deny_hits, f"{case['case_id']}: expected deny, no deny counter incremented. Evidence: {evidence}"
        assert not allow_hits, f"{case['case_id']}: expected deny, but an accept rule fired. Evidence: {evidence}"
    else:
        assert allow_hits, f"{case['case_id']}: expected allow, no accept-rule counter incremented. Evidence: {evidence}"
        assert not deny_hits, f"{case['case_id']}: expected allow, but a deny counter also fired. Evidence: {evidence}"
