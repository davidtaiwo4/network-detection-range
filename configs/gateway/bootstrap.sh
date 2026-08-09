#!/bin/sh
set -eu
echo 1 > /proc/sys/net/ipv6/conf/all/disable_ipv6 2>/dev/null || true
echo 1 > /proc/sys/net/ipv6/conf/default/disable_ipv6 2>/dev/null || true
ip address add 10.81.254.2/30 dev eth1
ip address add 10.81.10.1/27 dev eth2
ip address add 10.81.20.1/26 dev eth3
ip address add 10.81.30.1/25 dev eth4
ip address add 10.81.40.1/24 dev eth5
ip address add 10.81.50.1/27 dev eth6
ip address add 10.81.60.1/28 dev eth7
ip address add 10.81.70.1/24 dev eth8
ip link set eth9 promisc on
for interface in eth2 eth3 eth4 eth5 eth6 eth7 eth8 ; do
  tc qdisc add dev "$interface" clsact
  tc filter add dev "$interface" ingress matchall action mirred egress mirror dev eth9
done
sysctl -w net.ipv4.ip_forward=1
# anti-spoof: reverse-path filtering per zone interface (supports NET-28)
echo 1 > /proc/sys/net/ipv4/conf/eth2/rp_filter
echo 1 > /proc/sys/net/ipv4/conf/eth3/rp_filter
echo 1 > /proc/sys/net/ipv4/conf/eth4/rp_filter
echo 1 > /proc/sys/net/ipv4/conf/eth5/rp_filter
echo 1 > /proc/sys/net/ipv4/conf/eth6/rp_filter
echo 1 > /proc/sys/net/ipv4/conf/eth7/rp_filter
echo 1 > /proc/sys/net/ipv4/conf/eth8/rp_filter
nft -f /etc/nftables.conf