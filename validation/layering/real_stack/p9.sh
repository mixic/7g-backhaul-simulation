#!/bin/bash
# P9: real WireGuard wire overhead.  cA --cN(router)-- cB, wg0 overlay.
set -u

CLEAN() {
  ip netns del cA 2>/dev/null; ip netns del cN 2>/dev/null; ip netns del cB 2>/dev/null
}
CLEAN

ip netns add cA && ip netns add cN && ip netns add cB || { echo SETUP_FAIL; exit 1; }
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
# underlay routes: each endpoint reaches the far subnet via the router
ip netns exec cA ip route add 10.200.2.0/24 via 10.200.1.1
ip netns exec cB ip route add 10.200.1.0/24 via 10.200.2.1
ip netns exec cA ping -c1 -W1 10.200.2.2 >/dev/null 2>&1 && echo UNDERLAY_PING_OK || echo UNDERLAY_PING_FAIL

ip netns exec cA ethtool -K vA1 tx off gso off tso off >/dev/null 2>&1
ip netns exec cB ethtool -K vB2 tx off gso off tso off >/dev/null 2>&1

APRIV=$(ip netns exec cA wg genkey); APUB=$(printf '%s' "$APRIV" | ip netns exec cA wg pubkey)
BPRIV=$(ip netns exec cB wg genkey); BPUB=$(printf '%s' "$BPRIV" | ip netns exec cB wg pubkey)
printf '%s' "$APRIV" > /tmp/a.key; printf '%s' "$BPRIV" > /tmp/b.key

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

ip netns exec cB python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('10.99.0.2',9999)); s.settimeout(60)
while True:
    try: s.recvfrom(65535)
    except Exception: break
" &
SINK=$!
sleep 0.3

# warm up: establish the handshake so later captures are data packets
ip netns exec cA python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.sendto(b'warmup', ('10.99.0.2',9999))
"
sleep 1.5
HS=$(ip netns exec cA wg show wg0 latest-handshakes | awk '{print $2}')
echo "handshake_epoch=$HS"

echo "L,predicted_wire,measured_wire"
for L in 29 44 60 61 76 100 1000 1024 1400; do
  PAY=$((L-28))
  ip netns exec cA timeout 3 tcpdump -i vA1 -n -Q out -c 1 -v 'udp dst port 51820' > /tmp/cap.txt 2>&1 &
  TPID=$!
  sleep 0.4
  ip netns exec cA python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.sendto(b'x'*$PAY, ('10.99.0.2',9999))
"
  wait $TPID 2>/dev/null
  MEAS=$(grep -E 'proto UDP' /tmp/cap.txt | grep -oE 'length [0-9]+' | head -1 | awk '{print $2}')
  if [ "$((L % 16))" -eq 0 ]; then R=$L; else R=$(( ((L/16)+1)*16 )); fi
  PRED=$((60+R))
  echo "$L,$PRED,${MEAS:-NA}"
done

kill $SINK 2>/dev/null
CLEAN
echo P9_DONE
