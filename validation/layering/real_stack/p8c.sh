#!/bin/bash
# P8c: WireGuard through an nftables NAT (masquerade).  Predicts 100 % delivery
# and that cB's wg endpoint learns the NAT address/port.
set -u
CLEAN() { ip netns del cA 2>/dev/null; ip netns del cN 2>/dev/null; ip netns del cB 2>/dev/null; }
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
ip netns exec cA ip route add 10.200.2.0/24 via 10.200.1.1
ip netns exec cB ip route add 10.200.1.0/24 via 10.200.2.1

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

COUNT=/tmp/p8c_count
rm -f $COUNT
ip netns exec cB python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('10.99.0.2',9999)); s.settimeout(20)
open('$COUNT','w').write('0')
while True:
    try:
        d,_=s.recvfrom(65535)
        with open('$COUNT','r+') as f:
            n=int(f.read() or 0)+1; f.seek(0); f.write(str(n)); f.truncate()
    except Exception: break
" &
SINK=$!
sleep 0.3

send_n() {
  ip netns exec cA python3 -c "
import socket,time
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
for i in range($1):
    s.sendto(b'x'*172, ('10.99.0.2',9999)); time.sleep(0.01)
"
}
get_n() { cat $COUNT 2>/dev/null || echo 0; }

# warm-up handshake
send_n 3; sleep 1.2
echo "CASE,delivered,expected"
# control: no NAT
c0=$(get_n); send_n 50; sleep 0.6; c1=$(get_n)
echo "P8c_control,$((c1-c0)),50"

# install masquerade on cN egress toward cB
ip netns exec cN nft add table ip nat
ip netns exec cN nft add chain ip nat postrouting "{ type nat hook postrouting priority 100; }"
ip netns exec cN nft add rule ip nat postrouting oifname vN2 masquerade
n0=$(get_n); send_n 50; sleep 0.6; n1=$(get_n)
echo "P8c_nat,$((n1-n0)),50"

echo "--- cB wg endpoints (should show NAT 10.200.2.1) ---"
ip netns exec cB wg show wg0 endpoints

kill $SINK 2>/dev/null
CLEAN
echo P8C_DONE
