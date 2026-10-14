# SOC Analyst / Stage 7 — Build a Network Detection Range as Code

**Intern:** UBI-2026-0210 **Track:** SOC_ANALYSIS
**Private assignment set:** D4 **Evidence marker:** UBI-A7-3C77035E7384
**Addressing variant:** second_octet = 81

## What this is

A seven-zone routed enterprise range (management, finance, engineering, users,
servers, dmz, guest) plus a passive sensor zone, built entirely as code with
containerlab, FRRouting, and nftables, with a Suricata sensor mirrored off the
gateway. Policy, addressing, and telemetry are all generated from a single
`variant.yml` via a Jinja2 render pipeline — nothing is hand-edited after
build. A pytest suite, data-driven off `tests/fixtures/public-fixtures.json`,
proves 30 published allow/deny/return/spoof/sensor paths.

## Repository layout


```
soc-stage7/
├── network-range/          build tooling (variant.yml, render.py, Makefile-adjacent scripts)
├── topology.clab.yml       generated
├── configs/                generated (core/frr.conf, gateway/nftables.conf, gateway/bootstrap.sh)
├── services/                suricata.yaml
├── detections/              suricata.rules (real signatures, not the original placeholder)
├── tests/                   pytest suite, data-driven off tests/fixtures/public-fixtures.json
├── pcaps/
├── evidence/                collect-state.sh output, hashed per snapshot
├── test-results.xml
├── fault-recovery-log.md
├── evidence-index.csv
├── manifest.sha256          generated LAST, after everything else is final
├── integrity-attestation.md
├── assessment-manifest.json
├── continuity-record.md
└── decision-log.md
```

## Environment used for development and testing

- **Host:** Windows 11, WSL2 (kernel `6.6.87.2-microsoft-standard-WSL2`), Ubuntu (WSL2 distro)
- **Docker:** Docker Engine - Community, version 29.6.2
- **containerlab:** 0.77.0
- **nftables:** 1.0.9
- **Python:** 3.12.3, via a `venv` at repo root
- **pytest:** 9.1.1, **PyYAML** and **Jinja2** (latest via pip at time of build)
- **Container images:** `alpine:3.20` (zone hosts), `quay.io/frrouting/frr:10.2.1` (core router), `jasonish/suricata:7.0.8` (sensor), `soc-gateway:local` (gateway — custom image, see below)

WSL2-specific notes that affected this build (documented in `decision-log.md`
and `fault-recovery-log.md` in more detail): IPv6 must be disabled inside the
gateway container before any package operation, or outbound package fetches
silently fail with "Network unreachable"; the WSL2 Alpine mirror occasionally
returns transient fetch errors, which is why the gateway's dependencies
(nftables, iproute2, tcpdump) are baked into a prebuilt image rather than
installed live at every deploy.

## One-time setup (before the first `make lab`)

The gateway node uses a custom-built image so that `make lab` never depends
on live package installation (see notes above). Build it once:

```bash
cd soc-stage7
sudo docker build -t soc-gateway:local -f network-range/Dockerfile.gateway network-range/
```

Set up the Python environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install pytest pyyaml jinja2
```

Install containerlab if not already present:

```bash
bash -c "$(curl -sL https://get.containerlab.dev)"
```

## Exact reproduction order

All commands below run from `soc-stage7/`, with the
venv activated.

- Full clean rebuild and test, unattended, from zero
```bash
make clean && make lab && make test
```

`make lab` internally runs `make render` first (regenerating
`topology.clab.yml` and `configs/` from `network-range/variant.yml`), then
`sudo containerlab deploy`. `make test` runs the full 30-case pytest suite
and writes `test-results.xml`. Expected result: **30 passed**.

If `containerlab deploy`/`destroy` or `docker exec` fail with permission
errors, either prefix with `sudo` or add your user to the `docker` group (`sudo usermod -aG docker $USER && newgrp
docker` as done in this) — `containerlab` itself still needs `sudo` regardless, since it
manipulates network namespaces directly.


- Verify the live policy actually loaded (should show every rule with its comment, all counters at zero on a fresh deploy)
```bash
sudo docker exec clab-netforge-a3-gateway nft list ruleset
```

- Confirm the addressing variant is swappable 
- Edit network-range/variant.yml's second_octet, then:
```bash
make clean && make lab && make test
```

- Collect a fresh evidence snapshot (routes, nftables ruleset, gateway addresses, sensor log) into evidence/<name>/, hashed and timestamped
```bash
bash network-range/scripts/collect-state.sh evidence/<name>
```

- Tear down when done
```bash
make destroy
```

## Fault-recovery reproduction

The four required fault conditions (finance established-return removed,
management ingress broadened, dmz removed from sensor mirror, and the
private D4 condition — UDP DNS return-state broken with TCP DNS preserved)
are each isolated to a single named commit pair (`FAULT: ...` / `FIX: ...`)
in the git history. Full diagnosis evidence, exact commands, and before/after
counter values for each are in `fault-recovery-log.md`. To reproduce any
single fault: `git checkout <fault-commit>`, `make clean && make lab`, run
the diagnostic command shown in the log entry, then `git checkout master`
(or the fix commit) and repeat to confirm the green retest.

