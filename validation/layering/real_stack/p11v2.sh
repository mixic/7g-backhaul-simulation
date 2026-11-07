#!/bin/bash
# P11 v2: structural rewrite, with checksum offload disabled on all veth ends.
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
# disable offloads on every veth end (the pedit/csum path needs real checksums)
for x in "cA vA1" "cN vN1" "cN vN2" "cB vB2"; do set -- $x; ip netns exec $1 ethtool -K $2 tx off rx off gso off tso off >/dev/null 2>&1; done

APRIV=$(ip netns exec cA wg genkey); APUB=$(printf '%s' "$APRIV" | ip netns exec cA wg pubkey)
BPRIV=$(ip netns exec cB wg genkey); BPUB=$(printf '%s' "$BPRIV" | ip netns exec cB wg pubkey)
printf '%s' "$APRIV" > /tmp/a.key; printf '%s' "$BPRIV" > /tmp/b.key
ip netns exec cA ip link add wg0 type wireguard
ip netns exec cA ip addr add 10.99.0.1/32 dev wg0; ip netns exec cA ip link set wg0 up mtu 1420
ip netns exec cA wg set wg0 private-key /tmp/a.key listen-port 51821 peer "$BPUB" allowed-ips 10.99.0.2/32 endpoint 10.200.2.2:51820
ip netns exec cA ip route add 10.99.0.2/32 dev wg0
ip netns exec cB ip link add wg0 type wireguard
ip netns exec cB ip addr add 10.99.0.2/32 dev wg0; ip netns exec cB ip link set wg0 up mtu 1420
ip netns exec cB wg set wg0 private-key /tmp/b.key listen-port 51820 peer "$APUB" allowed-ips 10.99.0.1/32 endpoint 10.200.1.2:51821
ip netns exec cB ip route add 10.99.0.1/32 dev wg0

rm -f /tmp/p11c; ip netns exec cB python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('10.99.0.2',9999)); s.settimeout(30)
open('/tmp/p11c','w').write('0')
while True:
    try:
        s.recvfrom(65535)
        with open('/tmp/p11c','r+') as f:
            n=int(f.read() or 0)+1; f.seek(0); f.write(str(n)); f.truncate()
    except Exception: break
" & SINK=$!
sleep 0.3
SEND() { ip netns exec cA python3 -c "
import socket,time
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
for i in range($1): s.sendto(b'x'*172,('10.99.0.2',9999)); time.sleep(0.01)
"; }
GET() { cat /tmp/p11c 2>/dev/null || echo 0; }
SEND 3; sleep 1.2
echo "baseline=$(GET)"

run_case() { # $1 name  $2... pedit spec
  local name=$1; shift
  ip netns exec cN tc qdisc del dev vN2 root 2>/dev/null
  ip netns exec cN tc qdisc add dev vN2 root handle 1: prio
  ip netns exec cN tc filter add dev vN2 parent 1: protocol ip u32 match ip protocol 17 0xff match ip dport 51820 0xffff \
     action pedit ex munge "$@" 2>&1
  if [ $? -ne 0 ]; then echo "$name,SETUP_FAIL"; return; fi
  local c0=$(GET); SEND 50; sleep 0.6; echo "$name,$(( $(GET)-c0 )),50"
  ip netns exec cN tc qdisc del dev vN2 root 2>/dev/null
}
run_case P11_noop_control ip tos set 0 action csum ip
run_case P11c_tos_inert ip tos set 16 action csum ip
run_case P11a_len_nocsum offset 24 u16 set 9
run_case P11b_len_csum offset 24 u16 set 9 action csum ip udp
kill $SINK 2>/dev/null
CLEAN
echo P11V2_DONE
