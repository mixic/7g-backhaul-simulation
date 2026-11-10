# 7g-backhaul-simulation
# Copyright (C) 2026 MILAN NIKOLIC
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


"""Kernel configuration for every stack in the frozen predictions.

Every function issues plain ``ip`` / ``wg`` / ``tc`` commands through
:class:`Shell`, so ``--dry-run`` prints the complete configuration for review.
The exact command syntax is an implementation detail, not a prediction: if a
tool rejects a command, fix it in an addendum without touching the predictions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .capture import PROTO_AH, PROTO_ESP, PROTO_IPIP, Predicate, is_proto, is_udp_to
from .shell import Shell
from .topology import ADDR_A, ADDR_B, ADDR_N1, ADDR_N2, NS_A, NS_B, NS_N

APP_PORT = 9999
PROBE_PORT = 9998
WG_PORT_A, WG_PORT_B = 51821, 51820
WG_MTU = 1420
INNER_A, INNER_B = "10.201.0.1", "10.201.0.2"
OVERLAY_A, OVERLAY_B = "10.99.0.1", "10.99.0.2"
UNDERLAY_A, UNDERLAY_B = "10.88.0.1", "10.88.0.2"

AEAD = "rfc4106(gcm(aes))"
AUTH = "hmac(sha256)"


@dataclass(frozen=True)
class Flow:
    """What the traffic generator and the verdict logic need to know about a stack."""

    stack: str
    src: str
    dst: str
    port: int
    wire_filter: Predicate
    wireguard: bool = False
    nat_visible_src: str = ADDR_A  # outer source address before NAT


def _hex(nbytes: int) -> str:
    return "0x" + os.urandom(nbytes).hex()


def _spi() -> str:
    return "0x" + os.urandom(4).hex()


# --- IPsec ---------------------------------------------------------------------------


def _xfrm_sa_args(proto: str) -> list[str]:
    if proto == "ah":
        return ["auth-trunc", AUTH, _hex(32), "128"]
    return ["aead", AEAD, _hex(20), "128"]


def setup_xfrm_tunnel(sh: Shell, proto: str) -> Flow:
    """IPsec tunnel mode, one-way A -> B, inner 10.201.0.1 -> 10.201.0.2."""
    spi = _spi()
    sa_tail = _xfrm_sa_args(proto)  # identical key material on both ends
    for ns in (NS_A, NS_B):
        sh.ns(ns, ["ip", "xfrm", "state", "add", "src", ADDR_A, "dst", ADDR_B, "proto", proto, "spi", spi, "mode", "tunnel", *sa_tail])
    sh.ns(NS_A, ["ip", "addr", "add", f"{INNER_A}/32", "dev", "lo"])
    sh.ns(NS_A, ["ip", "route", "add", f"{INNER_B}/32", "via", ADDR_N1, "dev", "vA1"])
    sh.ns(NS_A, ["ip", "xfrm", "policy", "add", "src", f"{INNER_A}/32", "dst", f"{INNER_B}/32", "dir", "out",
                 "tmpl", "src", ADDR_A, "dst", ADDR_B, "proto", proto, "mode", "tunnel"])
    sh.ns(NS_B, ["ip", "addr", "add", f"{INNER_B}/32", "dev", "lo"])
    sh.ns(NS_B, ["ip", "xfrm", "policy", "add", "src", f"{INNER_A}/32", "dst", f"{INNER_B}/32", "dir", "in",
                 "tmpl", "src", ADDR_A, "dst", ADDR_B, "proto", proto, "mode", "tunnel"])
    wire = is_proto(PROTO_AH if proto == "ah" else PROTO_ESP)
    return Flow(stack=f"{proto}_tunnel", src=INNER_A, dst=INNER_B, port=APP_PORT, wire_filter=wire)


def setup_esp_transport(sh: Shell) -> Flow:
    """ESP transport mode carrying UDP port 9999, with a wildcard inbound source selector.

    The wildcard is required by the frozen P12: otherwise the policy selector, not the
    inner UDP checksum, would decide the outcome.
    """
    spi = _spi()
    sa_tail = _xfrm_sa_args("esp")
    for ns in (NS_A, NS_B):
        sh.ns(ns, ["ip", "xfrm", "state", "add", "src", ADDR_A, "dst", ADDR_B, "proto", "esp", "spi", spi, "mode", "transport", *sa_tail])
    sh.ns(NS_A, ["ip", "xfrm", "policy", "add", "src", f"{ADDR_A}/32", "dst", f"{ADDR_B}/32", "proto", "udp", "dport", APP_PORT,
                 "dir", "out", "tmpl", "src", ADDR_A, "dst", ADDR_B, "proto", "esp", "mode", "transport"])
    sh.ns(NS_B, ["ip", "xfrm", "policy", "add", "src", "0.0.0.0/0", "dst", f"{ADDR_B}/32", "proto", "udp", "dport", APP_PORT,
                 "dir", "in", "tmpl", "proto", "esp", "mode", "transport"])
    return Flow(stack="esp_transport", src=ADDR_A, dst=ADDR_B, port=APP_PORT, wire_filter=is_proto(PROTO_ESP))


# --- WireGuard -----------------------------------------------------------------------


def _wg_keypair(sh: Shell) -> tuple[str, str]:
    private = sh.run(["wg", "genkey"]).stdout.strip() or "DRYRUN-PRIVATE-KEY"
    public = sh.run(["wg", "pubkey"], input_text=private + "\n").stdout.strip() or "DRYRUN-PUBLIC-KEY"
    return private, public


def _wg_interface(sh: Shell, ns: str, *, address: str, port: int, private: str, peer_public: str,
                  allowed: str, endpoint: str | None) -> None:
    sh.run(["ip", "-n", ns, "link", "add", "wg0", "type", "wireguard"])
    command = ["wg", "set", "wg0", "private-key", "/dev/stdin", "listen-port", port, "peer", peer_public, "allowed-ips", allowed]
    if endpoint:
        command += ["endpoint", endpoint]
    sh.ns(ns, command, input_text=private + "\n")
    sh.ns(ns, ["ip", "addr", "add", address, "dev", "wg0"])
    sh.ns(ns, ["ip", "link", "set", "wg0", "mtu", WG_MTU, "up"])


def setup_wireguard(sh: Shell) -> Flow:
    """WireGuard over the veth underlay; overlay 10.99.0.1 <-> 10.99.0.2."""
    priv_a, pub_a = _wg_keypair(sh)
    priv_b, pub_b = _wg_keypair(sh)
    _wg_interface(sh, NS_A, address=f"{OVERLAY_A}/24", port=WG_PORT_A, private=priv_a, peer_public=pub_b,
                  allowed=f"{OVERLAY_B}/32", endpoint=f"{ADDR_B}:{WG_PORT_B}")
    _wg_interface(sh, NS_B, address=f"{OVERLAY_B}/24", port=WG_PORT_B, private=priv_b, peer_public=pub_a,
                  allowed=f"{OVERLAY_A}/32", endpoint=None)
    return Flow(stack="wireguard", src=OVERLAY_A, dst=OVERLAY_B, port=APP_PORT,
                wire_filter=is_udp_to(WG_PORT_B), wireguard=True)


def _ipip(sh: Shell, ns: str, name: str, local: str, remote: str, address: str, peer_route: str, mtu: int) -> None:
    sh.run(["ip", "-n", ns, "link", "add", name, "type", "ipip", "local", local, "remote", remote])
    sh.ns(ns, ["ip", "addr", "add", f"{address}/32", "dev", name])
    sh.ns(ns, ["ip", "link", "set", name, "mtu", mtu, "up"])
    sh.ns(ns, ["ip", "route", "add", f"{peer_route}/32", "dev", name])


def setup_ipip_over_wg(sh: Shell) -> Flow:
    """P10 order ``Y -> W``: inner packet enters IPIP first, WireGuard is outermost."""
    setup_wireguard(sh)
    _ipip(sh, NS_A, "ipip0", OVERLAY_A, OVERLAY_B, INNER_A, INNER_B, 1400)
    _ipip(sh, NS_B, "ipip0", OVERLAY_B, OVERLAY_A, INNER_B, INNER_A, 1400)
    return Flow(stack="ipip_over_wg", src=INNER_A, dst=INNER_B, port=APP_PORT,
                wire_filter=is_udp_to(WG_PORT_B), wireguard=True)


def setup_wg_over_ipip(sh: Shell) -> Flow:
    """P10 order ``W -> Y``: inner packet enters WireGuard first, IPIP is outermost."""
    _ipip(sh, NS_A, "ipip1", ADDR_A, ADDR_B, UNDERLAY_A, UNDERLAY_B, 1480)
    _ipip(sh, NS_B, "ipip1", ADDR_B, ADDR_A, UNDERLAY_B, UNDERLAY_A, 1480)
    priv_a, pub_a = _wg_keypair(sh)
    priv_b, pub_b = _wg_keypair(sh)
    _wg_interface(sh, NS_A, address=f"{INNER_A}/32", port=WG_PORT_A, private=priv_a, peer_public=pub_b,
                  allowed=f"{INNER_B}/32", endpoint=f"{UNDERLAY_B}:{WG_PORT_B}")
    _wg_interface(sh, NS_B, address=f"{INNER_B}/32", port=WG_PORT_B, private=priv_b, peer_public=pub_a,
                  allowed=f"{INNER_A}/32", endpoint=None)
    sh.ns(NS_A, ["ip", "route", "add", f"{INNER_B}/32", "dev", "wg0"])
    sh.ns(NS_B, ["ip", "route", "add", f"{INNER_A}/32", "dev", "wg0"])
    return Flow(stack="wg_over_ipip", src=INNER_A, dst=INNER_B, port=APP_PORT,
                wire_filter=is_proto(PROTO_IPIP), wireguard=True)


# --- Byte mangler (P11) ----------------------------------------------------------------

MANGLERS = {
    # iproute2 6.19 rejects the layered ``udp len`` pedit field ("bad pedit
    # parsing"); the outer UDP length lives at IPv4-header offset 24
    # (20 IP + 4 UDP = src/dst ports), so rewrite it with the raw 2-byte form.
    "len9": ["action", "pedit", "ex", "munge", "offset", "24", "u16", "set", "0x0009"],
    "len9_csum": ["action", "pedit", "ex", "munge", "offset", "24", "u16", "set", "0x0009",
                  "pipe", "action", "csum", "udp"],
    # The inert control: rewrite the IPv4 ToS byte (offset 1 of the IP header)
    # and recompute the IP header checksum. If this does not deliver, the mangler
    # path itself is suspect; see docs/layering-real-stack-results.md §P11 bisect.
    "tos": ["action", "pedit", "ex", "munge", "ip", "tos", "set", "0x10", "pipe", "action", "csum", "ip4h"],
}


def install_mangler(sh: Shell, kind: str) -> None:
    """Rewrite WireGuard data packets on ``vN2`` egress (router namespace)."""
    sh.ns(NS_N, ["tc", "qdisc", "add", "dev", "vN2", "clsact"])
    sh.ns(NS_N, ["tc", "filter", "add", "dev", "vN2", "egress", "protocol", "ip", "prio", "1", "u32",
                 "match", "ip", "protocol", "17", "0xff", "match", "ip", "dport", WG_PORT_B, "0xffff", *MANGLERS[kind]])


STACK_BUILDERS = {
    "ah_tunnel": lambda sh: setup_xfrm_tunnel(sh, "ah"),
    "esp_tunnel": lambda sh: setup_xfrm_tunnel(sh, "esp"),
    "esp_transport": setup_esp_transport,
    "wireguard": setup_wireguard,
    "ipip_over_wg": setup_ipip_over_wg,
    "wg_over_ipip": setup_wg_over_ipip,
}

__all__ = [
    "ADDR_N2",
    "APP_PORT",
    "PROBE_PORT",
    "STACK_BUILDERS",
    "Flow",
    "install_mangler",
]
