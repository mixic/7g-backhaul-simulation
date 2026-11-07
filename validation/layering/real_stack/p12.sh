#!/bin/bash
# P12: ESP transport mode + NAT.  The inner UDP checksum covers a pseudo-header
# with the outer address, which NAT rewrites.
#  a: computed inner checksum + NAT -> predict 0 %   (UdpInCsumErrors)
#  b: zeroed inner checksum (SO_NO_CHECK) + NAT -> predict 100 %
#  c: computed checksum, no NAT (control) -> predict 100 %
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

AUTH=0x$(printf 'a%.0s' $(seq 1 64))
ENC=0x$(printf 'b%.0s' $(seq 1 32))
for ns in cA cB; do
  ip netns exec $ns ip xfrm state flush 2>/dev/null
  ip netns exec $ns ip xfrm policy flush 2>/dev/null
  ip netns exec $ns ip xfrm state add src 10.200.1.2 dst 10.200.2.2 proto esp spi 0x300 mode transport auth "hmac(sha256)" $AUTH enc "cbc(aes)" $ENC
done
ip netns exec cA ip xfrm policy add dir out src 10.200.1.2/32 dst 10.200.2.2/32 proto udp tmpl src 10.200.1.2 dst 10.200.2.2 proto esp mode transport
ip netns exec cB ip xfrm policy add dir in  src 10.200.1.2/32 dst 10.200.2.2/32 proto udp tmpl src 10.200.1.2 dst 10.200.2.2 proto esp mode transport

COUNT=/tmp/p12_count
rm -f $COUNT
ip netns exec cB python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('10.200.2.2',9999)); s.settimeout(30)
open('$COUNT','w').write('0')
while True:
    try:
        s.recvfrom(65535)
        with open('$COUNT','r+') as f:
            n=int(f.read() or 0)+1; f.seek(0); f.write(str(n)); f.truncate()
    except Exception: break
" & SINK=$!
sleep 0.3
GET() { cat $COUNT 2>/dev/null || echo 0; }
SEND_CK() { ip netns exec cA python3 -c "
import socket,time
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
for i in range($1): s.sendto(b'x'*172,('10.200.2.2',9999)); time.sleep(0.01)
"; }
SEND_NOCK() { ip netns exec cA python3 -c "
import socket,time
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, 11, 1)  # SO_NO_CHECK on Linux
for i in range($1): s.sendto(b'x'*172,('10.200.2.2',9999)); time.sleep(0.01)
"; }
echo "CASE,delivered,expected"
# c: control, no NAT
c0=$(GET); SEND_CK 50; sleep 0.6; echo "P12c_control,$(( $(GET)-c0 )),50"
# a: NAT, computed checksum
ip netns exec cN nft add table ip nat
ip netns exec cN nft add chain ip nat postrouting "{ type nat hook postrouting priority 100; }"
ip netns exec cN nft add rule ip nat postrouting oifname vN2 masquerade
e0=$(ip netns exec cB nstat -az UdpInCsumErrors | awk 'END{print $2}')
a0=$(GET); SEND_CK 50; sleep 0.6; echo "P12a_nat_csum,$(( $(GET)-a0 )),0"
e1=$(ip netns exec cB nstat -az UdpInCsumErrors | awk 'END{print $2}')
echo "P12a_udp_in_csum_errors_delta,$((e1-e0)),50"
# b: NAT, zero checksum
b0=$(GET); SEND_NOCK 50; sleep 0.6; echo "P12b_nat_nocsum,$(( $(GET)-b0 )),50"
kill $SINK 2>/dev/null
CLEAN
echo P12_DONE
