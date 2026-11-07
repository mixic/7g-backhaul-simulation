#!/bin/bash
# P10 W->Y: inner (10.77.x) -> wg0 -> WG endpoint 10.99.x -> ipip1 -> underlay.
# Wire = 80 + R(L) = 20 (ipip) + 60 (wg) + R(L).
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

# ipip1 carries the 10.99.x endpoints over the 10.200.x underlay
ip netns exec cA ip link add ipip1 type ipip local 10.200.1.2 remote 10.200.2.2
ip netns exec cA ip addr add 10.99.0.1/32 dev ipip1
ip netns exec cA ip link set ipip1 up mtu 1400
ip netns exec cA ip route add 10.99.0.2/32 dev ipip1
ip netns exec cB ip link add ipip1 type ipip local 10.200.2.2 remote 10.200.1.2
ip netns exec cB ip addr add 10.99.0.2/32 dev ipip1
ip netns exec cB ip link set ipip1 up mtu 1400
ip netns exec cB ip route add 10.99.0.1/32 dev ipip1

APRIV=$(ip netns exec cA wg genkey); APUB=$(printf '%s' "$APRIV" | ip netns exec cA wg pubkey)
BPRIV=$(ip netns exec cB wg genkey); BPUB=$(printf '%s' "$BPRIV" | ip netns exec cB wg pubkey)
printf '%s' "$APRIV" > /tmp/a.key; printf '%s' "$BPRIV" > /tmp/b.key

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

rm -f /tmp/wy; ip netns exec cB python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('10.77.0.2',9999)); s.settimeout(20)
open('/tmp/wy','w').write('0')
while True:
    try:
        s.recvfrom(65535)
        with open('/tmp/wy','r+') as f:
            n=int(f.read() or 0)+1; f.seek(0); f.write(str(n)); f.truncate()
    except Exception: break
" & SINK=$!
sleep 0.3
SEND() { ip netns exec cA python3 -c "
import socket,time
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('10.77.0.1',0))
for i in range($1): s.sendto(b'x'*$2,('10.77.0.2',9999)); time.sleep(0.02)
"; }
GET() { cat /tmp/wy 2>/dev/null || echo 0; }
SEND 3 172; sleep 1.5
echo "warmup_delivered=$(GET)"

echo "L,predicted,measured"
for L in 64 65 76 77 79 100 1000 1008; do
  PAY=$((L-28))
  ip netns exec cA timeout 3 tcpdump -i vA1 -n -Q out -c 1 -v 'ip proto 4' > /tmp/wycap.txt 2>&1 &
  T=$!; sleep 0.4
  SEND 1 $PAY
  wait $T 2>/dev/null
  M=$(grep -E 'proto IPIP' /tmp/wycap.txt | grep -oE 'length [0-9]+' | head -1 | awk '{print $2}')
  if [ "$((L % 16))" -eq 0 ]; then R=$L; else R=$(( ((L/16)+1)*16 )); fi
  echo "$L,$((80+R)),${M:-NA}"
done
kill $SINK 2>/dev/null
CLEAN
echo P10WY_DONE
