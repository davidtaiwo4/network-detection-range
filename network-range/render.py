#!/usr/bin/env python3
"""
Render topology + config files from variant.yml.

Usage: python3 render.py [variant.yml]

"""
import ipaddress
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent.parent     # soc-stage7/ — outputs land here
SCRIPT_DIR = Path(__file__).parent      # network-range/ — templates & variant.yml live here
TEMPLATES = SCRIPT_DIR / "templates"


def load_variant(path):
    with open(path) as f:
        raw = yaml.safe_load(f)

    octet = raw["second_octet"]

    def fmt(s):
        return s.format(second_octet=octet) if isinstance(s, str) else s

    backbone = raw["backbone"]
    backbone = {k: fmt(v) for k, v in backbone.items()}

    zones = {}
    for name, z in raw["zones"].items():
        if z.get("mode") == "mirror":
            continue  # sensor handled separately
        cidr = fmt(z["cidr"])
        net = ipaddress.ip_network(cidr, strict=False)
        gw = fmt(z["gateway_ip"])
        hosts = list(net.hosts())
        # mirror the original bundle's convention: test host at .10 where it fits
        test_host = str(hosts[9]) if len(hosts) > 9 else str(hosts[1])
        zones[name] = {
            **z,
            "cidr": cidr,
            "gateway_ip": gw,
            "host_ip": test_host,
            "prefixlen": net.prefixlen,
        }

    sensor_eth = raw["zones"]["sensor"]["gateway_eth"]

    return {
        "evidence_marker": raw["evidence_marker"],
        "second_octet": octet,
        "backbone": backbone,
        "zones": zones,
        "services": raw["services"],
        "sensor_eth": sensor_eth,
    }


def main():
    variant_path = sys.argv[1] if len(sys.argv) > 1 else SCRIPT_DIR / "variant.yml"
    ctx = load_variant(variant_path)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), trim_blocks=True, lstrip_blocks=True)

    outputs = {
        "topology.clab.yml.j2": ROOT / "topology.clab.yml",
        "frr.conf.j2": ROOT / "configs" / "core" / "frr.conf",
        "nftables.conf.j2": ROOT / "configs" / "gateway" / "nftables.conf",
        "bootstrap.sh.j2": ROOT / "configs" / "gateway" / "bootstrap.sh",
    }

    for template_name, out_path in outputs.items():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = env.get_template(template_name).render(**ctx)
        out_path.write_text(rendered)
        print(f"rendered {out_path.relative_to(ROOT)}")

    print(f"\nvariant: second_octet={ctx['second_octet']} evidence_marker={ctx['evidence_marker']}")


if __name__ == "__main__":
    main()
