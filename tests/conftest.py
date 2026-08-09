"""
Shared fixtures for the segmentation test suite.

Everything here reads from variant.yml and the containerlab-generated
node names (clab-<lab_name>-<node>) -- NO addresses or ports are
hardcoded in this file. That's what lets the same test code survive the hidden holdout fixture.
"""
import json
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
LAB_NAME = "netforge-a3"
GATEWAY_CONTAINER = f"clab-{LAB_NAME}-gateway"


def _node(zone: str) -> str:
    return f"clab-{LAB_NAME}-{zone}"


@pytest.fixture(scope="session")
def variant():
    with open(REPO_ROOT / "network-range" / "variant.yml") as f:
        raw = yaml.safe_load(f)
    octet = raw["second_octet"]
    zones = {}
    for name, z in raw["zones"].items():
        if z.get("mode") == "mirror":
            continue
        zones[name] = z
    return {"second_octet": octet, "zones": zones, "services": raw["services"]}


@pytest.fixture(scope="session")
def zone_ip(variant):
    """zone_ip('finance') -> the .10-style test host address inside that zone."""
    import ipaddress

    cache = {}

    def _get(zone_name):
        if zone_name in cache:
            return cache[zone_name]
        z = variant["zones"][zone_name]
        cidr = z["cidr"].format(second_octet=variant["second_octet"])
        net = ipaddress.ip_network(cidr, strict=False)
        hosts = list(net.hosts())
        ip = str(hosts[9]) if len(hosts) > 9 else str(hosts[1])
        cache[zone_name] = ip
        return ip

    return _get


def docker_exec(node: str, cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", _node(node), "sh", "-c", cmd],
        capture_output=True, text=True, timeout=15,
    )


@pytest.fixture
def attempt_connection():
    """attempt_connection('guest', '10.81.20.10', 443, 'tcp') -> CompletedProcess"""

    def _attempt(source_zone, dest_ip, port, proto):
        flag = "-u" if proto == "udp" else ""
        cmd = f"nc -z -w2 {flag} {dest_ip} {port}"
        return docker_exec(source_zone, cmd)

    return _attempt


def nft_counters() -> dict:
    """Returns {comment: packets} for every counter-bearing rule on the gateway."""
    result = subprocess.run(
        ["docker", "exec", GATEWAY_CONTAINER, "nft", "-j", "list", "ruleset"],
        capture_output=True, text=True, timeout=15,
    )
    result.check_returncode()
    data = json.loads(result.stdout)
    counters = {}
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
        counters[comment] = packets
    return counters


@pytest.fixture
def counters_before_after():
    """Usage: with counters_before_after() as get_delta: ... ; delta = get_delta()"""

    class _Ctx:
        def __enter__(self):
            self.before = nft_counters()
            return self

        def __exit__(self, *exc):
            self.after = nft_counters()

        def delta(self):
            return {
                k: self.after.get(k, 0) - self.before.get(k, 0)
                for k in set(self.before) | set(self.after)
            }

    return _Ctx
