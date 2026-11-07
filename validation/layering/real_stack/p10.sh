#!/bin/bash
# P10: nested IPIP/WireGuard orderings (quantisation vs fixed overhead).
#  Y->W: inner -> ipip0 (10.88.x) -> wg0 (10.99.x) -> underlay; wire = 60+R(L+20)
#  W->Y: inner -> wg0 (10.77.x) -> ipip1 (10.99.x over underlay); wire = 80+R(L)
set -u
CLEAN() { ip netns del cA 2>/dev/null; ip netns del cN 2>/dev/null; ip netns del cB 2>/dev/null; }
CLEAN
ip netns add cA; ip netns add cN; ip netns add cB
ip link add vA1 type veth peer name vN1; ip link set vA1 netns cA; ip link set vN1 netns cN
ip link add vN2 type veth peer name vB2; ip link set vN2 netns cN; ip link set vB2 netns cB
ip netns exec cA ip addr add 10.200.1.2/24 dev vA1
ip netns exec cN ip addr add 10.200.1.1/24 dev vN1
ip netns exec cN ip addr add 10.200.2.1/24 dev vN2
ip netns exec cB ip addr add 10.200.2.2/24 dev vB2
for ns in cA cN cB; do ip netns exec $ns ip link set lo up; done
ip netns exec cA ip link set vA1 up
ip netns exec cN ip link set vN1 up; ip netns exec cN ip link set vN2 up
ip netns exec cB ip link set vB2 up
ip netns exec cN sysctl -qw net.ipv4.ip_forward=1
ip netns exec cA ip route add 10.200.2.0/24 via 10.200.1.1
ip netns exec cB ip route add 10.200.1.0/24 via 10.200.2.1
for x in "cA vA1" "cN vN1" "cN vN2" "cB vB2"; do set -- $x; ip netns exec $1 ethtool -K $2 tx off rx off gso off tso off >/dev/null 2>&1; done

# WireGuard keys
APRIV=$(ip netns exec cA wg genkey); APUB=$(printf '%s' "$APRIV" | ip netns exec cA wg pubkey)
BPRIV=$(ip netns exec cB wg genkey); BPUB=$(printf '%s' "$BPRIV" | ip netns exec cB wg pubkey)
printf '%s' "$APRIV" > /tmp/a.key; printf '%s' "$BPRIV" > /tmp/b.key

# ---- Y->W : inner 10.88.x -> ipip0(10.99.x) -> wg0 -> underlay ----
setup_yw() {
  for ns in cA cB; do ip netns exec $ns ip link del wg0 2>/dev/null; ip netns exec $ns ip link del ipip0 2>/dev/null; done
  ip netns exec cA ip link add wg0 type wireguard
  ip netns exec cA ip addr add 10.99.0.1/32 dev wg0
  ip netns exec cA ip link set wg0 up mtu 1420
  ip netns exec cA wg set wg0 private-key /tmp/a.key listen-port 51821 peer "$BPUB" allowed-ips 10.99.0.2/32 endpoint 10.200.2.2:51820
  ip netns exec cA ip route add 10.99.0.2/32 dev wg0
  ip netns exec cB ip link add wg0 type wireguard
  ip netns exec cB ip addr add 10.99.0.2/32 dev wg0
  ip netns exec cB ip link set wg0 up mtu 1420
  ip netns exec cB wg set wg0 private-key /tmp/b.key listen-port 51820 peer "$APUB" allowed-ips 10.99.0.1/32 endpoint 10.200.1.2:51821
  ip netns exec cB ip route add 10.99.0.1/32 dev wg0
  # ipip0 with endpoints on the wg overlay
  ip netns exec cA ip link add ipip0 type ipip local 10.99.0.1 remote 10.99.0.2
  ip netns exec cA ip addr add 10.88.0.1/24 dev ipip0
  ip netns exec cA ip link set ipip0 up mtu 1400
  ip netns exec cB ip link add ipip0 type ipip local 10.99.0.2 remote 10.99.0.1
  ip netns exec cB ip addr add 10.88.0.2/24 dev ipip0
  ip netns exec cB ip link set ipip0 up mtu 1400
}

# ---- W->Y : inner 10.77.x -> wg0(10.99.x) -> ipip1(underlay) ----
setup_wy() {
  for ns in cA cB; do ip netns exec $ns ip link del wg0 2>/dev/null; ip netns exec $ns ip link del ipip1 2>/dev/null; done
  ip netns exec cA ip link add wg0 type wireguard
  ip netns exec cA ip addr add 10.77.0.1/32 dev wg0
  ip netns exec cA ip link set wg0 up mtu 1420
  ip netns exec cA wg set wg0 private-key /tmp/a.key listen-port 51821 peer "$BPUB" allowed-ips 10.77.0.2/32 endpoint 10.99.0.2:51820
  ip netns exec cA ip route add 10.77.0.2/32 dev wg0
  ip netns exec cB ip link add wg0 type wireguard
  ip netns exec cB ip addr add 10.77.0.2/32 dev wg0
  ip netns exec cB ip link set wg0 up mtu 1420
  ip netns exec cB wg set wg0 private-key /tmp/b.key listen-port 51820 peer "$APUB" allowed-ips 10.77.0.1/32 endpoint 10.99.0.1:51821
  ip netns exec cB ip route add 10.77.0.1/32 dev wg0
  # ipip1 carries the wg overlay endpoint over the underlay
  ip netns exec cA ip link add ipip1 type ipip local 10.200.1.2 remote 10.200.2.2
  ip netns exec cA ip link set ipip1 up mtu 1400
  ip netns exec cA ip route add 10.99.0.2/32 dev ipip1
  ip netns exec cB ip link add ipip1 type ipip local 10.200.2.2 remote 10.200.1.2
  ip netns exec cB ip link set ipip1 up mtu 1400
  ip netns exec cB ip route add 10.99.0.1/32 dev ipip1
}

capture_wire() {  # $1=proto-filter $2=inner-dst $3=payload
  ip netns exec cA timeout 3 tcpdump -i vA1 -n -Q out -c 1 -v "$1" > /tmp/p10cap.txt 2>&1 &
  local T=$!; sleep 0.4
  ip netns exec cA python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.sendto(b'x'*$3, ('$2',9999))
"
  wait $T 2>/dev/null
  grep -E 'proto (ESP|UDP|IPIP)' /tmp/p10cap.txt | grep -oE 'length [0-9]+' | head -1 | awk '{print $2}'
}

echo "stack,L,predicted,measured"
# Y->W
setup_yw
sleep 1.5
for L in 64 65 76 77 79 100 1000 1008; do
  PAY=$((L-28))
  m=$(capture_wire 'udp dst port 51820' 10.88.0.2 $PAY)
  if [ "$(((L+20) % 16))" -eq 0 ]; then R=$((L+20)); else R=$(( (( (L+20)/16)+1)*16 )); fi
  P=$((60+R)); echo "Y->W,$L,$P,${m:-NA}"
done
# W->Y
setup_wy
sleep 1.5
for L in 64 65 76 77 79 100 1000 1008; do
  PAY=$((L-28))
  m=$(capture_wire 'ip proto 4' 10.77.0.2 $PAY)
  if [ "$((L % 16))" -eq 0 ]; then R=$L; else R=$(( ((L/16)+1)*16 )); fi
  P=$((80+R)); echo "W->Y,$L,$P,${m:-NA}"
done
CLEAN
echo P10_DONE
