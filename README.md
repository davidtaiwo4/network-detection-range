# Network Detection Range as Code

A seven-zone enterprise network built entirely from code, with stateful least-privilege firewall policy, a passive IDS sensor, and an automated test suite that proves the policy works. Nothing is configured by hand: one addressing file generates the topology, routing, firewall rules and gateway setup, and the whole lab can be destroyed and rebuilt identically with one command.

Built with containerlab, FRRouting, nftables, Suricata, Jinja2 and pytest.

## What it does

- **Seven zones plus a sensor:** management, finance, engineering, users, servers, DMZ and guest, joined by a routed gateway. A passive sensor receives a mirrored copy of all zone traffic and cannot initiate connections.
- **Policy as code:** every address, subnet, port and rule comes from `network-range/variant.yml`. Changing one value (the second octet) re-addresses the entire range with no edits to topology or tests.
- **Proof, not screenshots:** each test pairs a client-side result with the firewall's own rule counters, so a blocked connection is shown by a named deny counter incrementing, not by a failed ping.
- **Fault-and-recovery workflow:** four deliberate misconfigurations were injected, diagnosed from packet and counter evidence, fixed in version control and re-tested. Each is a `FAULT:` / `FIX:` commit pair in the git history.
- **Detection:** three Suricata signatures flag policy-violating traffic, and one was shown to fire on the same event the firewall denied.

## Architecture

```
                        core (FRRouting)
                              |
                        gateway (nftables)  ---- mirror ----> sensor (Suricata)
        ______________________|______________________
        |        |           |        |        |       |
   management  finance  engineering  users  servers   dmz   guest
```

| Zone | Subnet (default) | Gateway interface |
|---|---|---|
| management | 10.81.10.0/27 | eth2 |
| finance | 10.81.20.0/26 | eth3 |
| engineering | 10.81.30.0/25 | eth4 |
| users | 10.81.40.0/24 | eth5 |
| servers | 10.81.50.0/27 | eth6 |
| dmz | 10.81.60.0/28 | eth7 |
| guest | 10.81.70.0/24 | eth8 |
| sensor (mirror only) | none | eth9 |

The core-to-gateway backbone is `10.81.254.0/30`. The second octet (`81`) is the only value you change to re-address everything.

## Policy summary

The gateway's forward chain defaults to **drop**. Rules, in evaluation order:

1. **Anti-spoofing:** traffic entering a zone interface with a source address outside that zone's subnet is dropped and logged (`NF_SPOOF_DENY`).
2. **Return traffic:** `established,related` is accepted, so replies work while new sessions in the reverse direction do not.
3. **Management:** the only zone allowed to start admin sessions (tcp/22), to every zone except guest.
4. **Finance to servers:** payroll application and database ports.
5. **Engineering to servers:** the code service port only, not the payroll database.
6. **DNS/NTP:** all zones may reach the central resolver on servers (udp/tcp 53, udp 123).
7. **Guest to DMZ:** web ports only.
8. **DMZ to servers:** one approved application port only.
9. **Everything else:** dropped and logged (`NF_SEGMENT_DENY`).

Every accept rule carries a unique comment and counter, which is what the tests read.

## Quick start

### Prerequisites

- Linux host with Docker Engine (tested on Ubuntu under WSL2)
- [containerlab](https://containerlab.dev/install/) (tested on 0.77.0)
- Python 3.10+ and `sudo` access (containerlab needs it to manage network namespaces)

### One-time setup

```bash
git clone <your-repo-url> && cd <repo-name>

# Build the gateway image once, so deploys never depend on live package installs
sudo docker build -t soc-gateway:local -f network-range/Dockerfile.gateway network-range/

python3 -m venv venv
source venv/bin/activate
pip install pytest pyyaml jinja2
```

### Build, test, tear down

```bash
make clean && make lab && make test    # rebuild from zero and run all 30 tests
make destroy                           # remove the lab
```

`make lab` re-renders every generated file from `variant.yml` before deploying, so it always works from a clean checkout. Expected result: `30 passed`.

If `docker exec` fails with a permission error, either prefix commands with `sudo` or add yourself to the `docker` group (`sudo usermod -aG docker $USER && newgrp docker`).

## Make targets

| Target | What it does |
|---|---|
| `make render` | Generates `topology.clab.yml` and `configs/` from `network-range/variant.yml` |
| `make lab` | Cleans, renders, and deploys the lab |
| `make test` | Runs the pytest suite and writes `test-results.xml` |
| `make collect` | Snapshots routes, firewall ruleset, addresses and sensor log into `evidence/` |
| `make baseline` | Re-applies the firewall ruleset inside a running gateway |
| `make clean` | Removes the deployed lab and generated files (evidence is kept) |
| `make destroy` | Removes the deployed lab only |

## Testing approach

Tests are data-driven from `tests/fixtures/public-fixtures.json`. Each case names a source zone, destination zone, service and expected verdict. For every case the harness:

1. Reads the gateway's nftables counters.
2. Attempts the connection from inside the source zone container.
3. Reads the counters again and asserts that the expected rule fired: an accept rule for allow cases, a deny counter for deny cases.

No addresses or ports are hardcoded in the tests. Dropping in a different fixture file with the same schema runs through the same code unchanged.

### Changing the addressing plan

Edit `second_octet` in `network-range/variant.yml`, then rebuild:

```bash
make clean && make lab && make test
```

This was verified by running the suite under a second octet and then reverting.

## Fault-recovery exercises

Four faults were injected one at a time, each with a failing signal or packet-level diagnosis, a minimal fix, and a green retest:

1. Return-state handling removed on one zone's path
2. Admin ingress broadened beyond its intended source
3. One zone's traffic dropped from the sensor mirror
4. A protocol-specific return-state fault that left the other protocol working

Full evidence (counter values before and after, commands used, commit hashes) is in [`fault-recovery-log.md`](fault-recovery-log.md).

## Repository layout

```
.
├── Makefile
├── network-range/
│   ├── variant.yml            single source of truth for addressing and services
│   ├── render.py              renders templates into topology and configs
│   ├── templates/             Jinja2 templates (topology, FRR, nftables, gateway bootstrap)
│   ├── Dockerfile.gateway     gateway image with nftables, iproute2, tcpdump baked in
│   ├── adapter.py             converts test, firewall and sensor evidence into JSONL records
│   └── scripts/collect-state.sh
├── configs/core/daemons       FRR daemon list (hand-written)
├── services/suricata.yaml     sensor configuration
├── detections/suricata.rules  detection signatures
├── tests/                     pytest harness and fixtures
├── fault-recovery-log.md
└── README.md
```

Generated at build time: `topology.clab.yml`, `configs/core/frr.conf`, `configs/gateway/*`, `test-results.xml`, and the contents of `evidence/` and `pcaps/`.
