# Fault Recovery Log

Baseline: commit e005cc4 (tag: green-baseline), 30/30 public fixtures passing.

## Fault 1: Finance established-return handling removed

- **Injected**: commit 26b0a29 -- oifname eth3 (finance) ct state established,related drop rule added before the global established-return accept in nftables.conf.j2
- **Failing signal**: automated pytest (P-NET-19, P-NET-27) did not detect this fault -- both cases pass on the outbound new-connection accept rule alone, before the broken return leg is ever exercised. Documented as a known harness limitation (decision-log D-005).
- **Diagnosis evidence**: `docker exec clab-netforge-a3-gateway nft list ruleset | grep FAULT_FINANCE`
  - Before nc attempt: FAULT_FINANCE_RETURN_BROKEN counter = 4 packets, 160 bytes (background traffic baseline)
  - After `nc -z -w2 10.81.70.10 443` from finance: counter = 8 packets, 320 bytes
  - Delta of 4 packets directly attributable to the nc attempt's return-leg traffic being dropped
- **Fix**: commit 2cce479 -- removed the fault rule, restoring the single global established-return accept
- **Retest**: 30/30 passed; FAULT_FINANCE_RETURN_BROKEN rule confirmed absent from ruleset post-fix

## Fault 2: Management ingress broadened beyond declared source

- **Injected**: commit 3a26469 -- added iifname eth5 (users) oifname {eth3,eth4,eth6,eth7} tcp/22 accept rule, granting users the same admin reach that should be management-only
- **Failing signal**: pytest suite remained 30/30 green -- public-fixtures.json has no users-sourced admin-port case in this specific direction (fixture coverage gap, documented D-006)
- **Diagnosis evidence**: `docker exec clab-netforge-a3-gateway nft list ruleset | grep FAULT_USERS_ADMIN`
  - Before nc: FAULT_USERS_ADMIN_INGRESS counter = 0 packets
  - After `nc -z -w2 10.81.20.10 22` from users: counter = 1 packet, 60 bytes
  - Direct proof users reached finance's admin port through the broadened rule
- **Fix**: commit 4b4bd0a -- removed the fault rule, restoring management as the sole admin-ingress source
- **Retest**: 30/30 passed; FAULT_USERS_ADMIN_INGRESS rule confirmed absent from ruleset post-fix

## Fault 3: DMZ traffic removed from sensor mirror

- **Injected**: commit 0651cf4 -- dmz's gateway interface (eth7) excluded from the mirror loop in bootstrap.sh.j2 -- no tc qdisc/filter created for it
- **Diagnosis evidence**: `docker exec clab-netforge-a3-gateway tc filter show dev eth7 ingress`
  - Returns empty -- no mirred/mirror action present on dmz's interface, confirming structural absence of the tap
  - Control comparison: `tc filter show dev eth3 ingress` (finance, unaffected) shows the mirred action present and functioning, proving the mirror mechanism itself works generally and dmz specifically was excluded
- **Fix**: commit f98a7b3 -- restored dmz to the mirror loop
- **Retest**: 30/30 passed; `tc filter show dev eth7 ingress` confirmed mirred action restored, matching eth3's control output

## Fault 4 (D4, private condition): UDP DNS return-state broken, TCP DNS preserved

- **Injected**: commit 43923b6 -- added `udp sport 53 ct state established,related drop` rule before the global established-return accept; added a dedicated `central-dns-tcp` accept rule (none existed previously) so TCP DNS had a real path to preserve
- **Bug found and fixed during evidence-gathering**: commit eea4210 -- the initial "generic reachability grid" rules (added for public-fixtures.json coverage) shared duplicate comments per zone-pair, causing the test harness's comment-keyed counter lookup to silently collide. Fixed by giving each rule a unique `-tcp`/`-udp` suffixed comment. Unrelated to D4 itself but discovered and resolved during this fault's verification pass.
- **Diagnosis evidence**: `docker exec clab-netforge-a3-gateway nft list ruleset | grep -E 'FAULT_D4|central-dns'`
  - No real DNS service exists in the lab containers, so a UDP echo listener was stood up on servers (`nc -u -l -p 53 -e /bin/echo pong`) to generate genuine bidirectional DNS-port traffic
  - Before: FAULT_D4_UDP_DNS_RETURN_BROKEN = 0 packets
  - After `echo hello | nc -u -w2 10.81.50.10 53` from finance: FAULT_D4 counter = 1 packet, 33 bytes -- the reply was dropped on the way back
  - Same window: central-dns-tcp counter incremented independently and correctly from a separate TCP DNS test, confirming the UDP-only fault did not affect TCP DNS
- **Fix**: commit d4161a5 -- removed the fault rule; central-dns-tcp rule retained permanently (legitimate addition, not part of the fault)
- **Retest**: 30/30 passed; retried the UDP echo exchange post-fix and received a genuine `pong` reply end-to-end, confirming real functionality restored (not just rule absence)

## Clean rebuild and variant-swap verification

- `make clean && make lab && make test` run unattended from zero: 30/30 passed
- Addressing variant swapped from second_octet=81 to second_octet=91 via variant.yml only, no topology/test code changes: `make clean && make lab && make test` re-run, 30/30 passed
- Restored second_octet=81 (correct assigned overlay value) before final packaging: `make clean && make lab && make test` re-run, 30/30 passed
