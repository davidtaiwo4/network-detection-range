#!/usr/bin/env bash
set -euo pipefail

out="${1:-evidence/reference-state}"
mkdir -p "$out"
date -u +%FT%TZ > "$out/captured-at.txt"
containerlab inspect --name netforge-a3 --format json > "$out/containerlab-inspect.json"
docker exec clab-netforge-a3-core vtysh -c 'show ip route json' > "$out/routes.json"
docker exec clab-netforge-a3-gateway nft -j list ruleset > "$out/nftables.json"
docker exec clab-netforge-a3-gateway ip -j address > "$out/gateway-addresses.json"
docker logs clab-netforge-a3-sensor > "$out/sensor-container.log" 2>&1
find "$out" -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > "$out/manifest.sha256"
