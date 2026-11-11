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


"""Stacks for P13-P16: IPIP, WireGuard and ESP tunnel, plus their ECN mangler.

Command syntax is an implementation detail, not a prediction.  Every function
issues plain ``ip``/``wg`` commands through :class:`Shell`, so ``--dry-run``
prints the full configuration for review before a root run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .capture import PROTO_ESP, PROTO_IPIP, PROTO_UDP, Predicate, is_proto, is_udp_to
from .net import ADDR_A, ADDR_A2, ADDR_B, ADDR_N1, ADDR_N3, NS_A, NS_A2, NS_B, NS_N
from validation.real_stack.shell import Shell

APP_PORT = 9999
PROBE_PORT = 9998
WG_PORT_A, WG_PORT_B = 51821, 51820
ESP_IN_UDP_PORT = 4500
INNER_A, INNER_B = "10.201.0.1", "10.201.0.2"
INNER2_A, INNER2_B = "10.202.0.1", "10.202.0.2"
OVERLAY_A, OVERLAY_B = "10.99.0.1", "10.99.0.2"
AEAD = "rfc4106(gcm(aes))"


@dataclass(frozen=True)
class Flow:
    """What the traffic generator, the gates and the verdict logic need to know."""

    stack: str
    src: str
    dst: str
    port: int
    wire_filter: Predicate
    wireguard: bool = False
    esp: bool = False
    encap_udp: bool = False
    ipip_device: str | None = None
    # outer protocol number seen at vN2 egress, for the ECN gate
    outer_proto: int = PROTO_UDP
    outer_dport: int | None = None


def _hex(nbytes: int) -> str:
    return "0x" + os.urandom(nbytes).hex()


def _spi() -> str:
    return "0x" + os.urandom(4).hex()


# --- IPIP (P13a-c) --------------------------------------------------------------------


def setup_ipip(sh: Shell) -> Flow:
    """IPIP tunnel over the underlay; inner 10.201.0.1 -> 10.201.0.2."""
    for ns, local, remote, inner in ((NS_A, ADDR_A, ADDR_B, INNER_A), (NS_B, ADDR_B, ADDR_A, INNER_B)):
        sh.run(["ip", "-n", ns, "link", "add", "ipip0", "type", "ipip", "local", local, "remote", remote])
        sh.ns(ns, ["ip", "addr", "add", f"{inner}/32", "dev", "ipip0"])
        sh.ns(ns, ["ip", "link", "set", "ipip0", "mtu", "1480", "up"])
    sh.ns(NS_A, ["ip", "route", "add", f"{INNER_B}/32", "dev", "ipip0"])
    sh.ns(NS_B, ["ip", "route", "add", f"{INNER_A}/32", "dev", "ipip0"])
    return Flow(stack="ipip", src=INNER_A, dst=INNER_B, port=APP_PORT,
                wire_filter=is_proto(PROTO_IPIP), ipip_device="ipip0", outer_proto=PROTO_IPIP)


# --- WireGuard (P13d-e, P15, P16c) ----------------------------------------------------


def _wg_keypair(sh: Shell) -> tuple[str, str]:
    private = sh.run(["wg", "genkey"]).stdout.strip() or "DRYRUN-PRIVATE-KEY"
    public = sh.run(["wg", "pubkey"], input_text=private + "\n").stdout.strip() or "DRYRUN-PUBLIC-KEY"
    return private, public


def _wg_interface(sh: Shell, ns: str, *, address: str, port: int, private: str, peer_public: str,
                  allowed: str, endpoint: str | None, mtu: int) -> None:
    sh.run(["ip", "-n", ns, "link", "add", "wg0", "type", "wireguard"])
    command = ["wg", "set", "wg0", "private-key", "/dev/stdin", "listen-port", port,
               "peer", peer_public, "allowed-ips", allowed]
    if endpoint:
        command += ["endpoint", endpoint]
    sh.ns(ns, command, input_text=private + "\n")
    sh.ns(ns, ["ip", "addr", "add", address, "dev", "wg0"])
    sh.ns(ns, ["ip", "link", "set", "wg0", "mtu", mtu, "up"])


def setup_wireguard(sh: Shell, mtu: int = 1420) -> Flow:
    """WireGuard over the veth underlay; overlay 10.99.0.1 <-> 10.99.0.2."""
    priv_a, pub_a = _wg_keypair(sh)
    priv_b, pub_b = _wg_keypair(sh)
    _wg_interface(sh, NS_A, address=f"{OVERLAY_A}/24", port=WG_PORT_A, private=priv_a, peer_public=pub_b,
                  allowed=f"{OVERLAY_B}/32", endpoint=f"{ADDR_B}:{WG_PORT_B}", mtu=mtu)
    _wg_interface(sh, NS_B, address=f"{OVERLAY_B}/24", port=WG_PORT_B, private=priv_b, peer_public=pub_a,
                  allowed=f"{OVERLAY_A}/32", endpoint=None, mtu=mtu)
    return Flow(stack="wireguard", src=OVERLAY_A, dst=OVERLAY_B, port=APP_PORT,
                wire_filter=is_udp_to(WG_PORT_B), wireguard=True, outer_proto=PROTO_UDP, outer_dport=WG_PORT_B)


# --- ESP tunnel mode (P13f-g, P14, P16a-b, P16d) --------------------------------------


def _esp_sa(sh: Shell, ns: str, *, src: str, dst: str, spi: str, key: str,
            replay_window: int | None, encap: bool) -> None:
    command = ["ip", "xfrm", "state", "add", "src", src, "dst", dst, "proto", "esp", "spi", spi, "mode", "tunnel"]
    if replay_window:
        command += ["replay-window", str(replay_window)]
    if encap:
        command += ["encap", "espinudp", str(ESP_IN_UDP_PORT), str(ESP_IN_UDP_PORT), "0.0.0.0"]
    command += ["aead", AEAD, key, "128"]
    sh.ns(ns, command)


def setup_esp_tunnel(sh: Shell, *, replay_window: int | None = None, encap: bool = False) -> Flow:
    """ESP tunnel mode, one-way A -> B, inner 10.201.0.1 -> 10.201.0.2."""
    spi = _spi()
    key = _hex(20)  # one key per SA pair: both ends must agree
    for ns in (NS_A, NS_B):
        _esp_sa(sh, ns, src=ADDR_A, dst=ADDR_B, spi=spi, key=key, replay_window=replay_window, encap=encap)
    sh.ns(NS_A, ["ip", "addr", "add", f"{INNER_A}/32", "dev", "lo"])
    sh.ns(NS_A, ["ip", "route", "add", f"{INNER_B}/32", "via", ADDR_N1, "dev", "vA1"])
    sh.ns(NS_A, ["ip", "xfrm", "policy", "add", "src", f"{INNER_A}/32", "dst", f"{INNER_B}/32", "dir", "out",
                 "tmpl", "src", ADDR_A, "dst", ADDR_B, "proto", "esp", "mode", "tunnel"])
    sh.ns(NS_B, ["ip", "addr", "add", f"{INNER_B}/32", "dev", "lo"])
    sh.ns(NS_B, ["ip", "xfrm", "policy", "add", "src", f"{INNER_A}/32", "dst", f"{INNER_B}/32", "dir", "in",
                 "tmpl", "src", ADDR_A, "dst", ADDR_B, "proto", "esp", "mode", "tunnel"])
    if encap:
        wire = is_udp_to(ESP_IN_UDP_PORT)
    else:
        wire = is_proto(PROTO_ESP)
    return Flow(stack="esp_tunnel", src=INNER_A, dst=INNER_B, port=APP_PORT, wire_filter=wire, esp=True,
                encap_udp=encap, outer_proto=PROTO_UDP if encap else PROTO_ESP,
                outer_dport=ESP_IN_UDP_PORT if encap else None)


def setup_esp_two_clients(sh: Shell, *, encap: bool, spis: tuple[str, str]) -> tuple[Flow, Flow]:
    """Two ESP tunnels from two client namespaces to one server (P14).

    Both clients share the single masqueraded address ``10.200.2.1`` at the
    middlebox; the SPIs are the only per-client field on the wire.
    """
    spi1, spi2 = spis
    client_specs = (
        (NS_A, ADDR_A, INNER_A, INNER_B, spi1),
        (NS_A2, ADDR_A2, INNER2_A, INNER2_B, spi2),
    )
    for ns, local, inner_src, inner_dst, spi in client_specs:
        key = _hex(20)  # one key per SA pair: both ends must agree
        _esp_sa(sh, ns, src=local, dst=ADDR_B, spi=spi, key=key, replay_window=None, encap=encap)
        sh.ns(ns, ["ip", "addr", "add", f"{inner_src}/32", "dev", "lo"])
        sh.ns(ns, ["ip", "route", "add", f"{inner_dst}/32", "via", (ADDR_N1 if ns == NS_A else ADDR_N3), "dev",
                   ("vA1" if ns == NS_A else "vA3")])
        sh.ns(ns, ["ip", "xfrm", "policy", "add", "src", f"{inner_src}/32", "dst", f"{inner_dst}/32", "dir", "out",
                   "tmpl", "src", local, "dst", ADDR_B, "proto", "esp", "mode", "tunnel"])
        # Inbound SA lookup is keyed on (dst, SPI): after masquerade both clients
        # arrive from 10.200.2.1, so the SPI is the only discriminator.
        _esp_sa(sh, NS_B, src=local, dst=ADDR_B, spi=spi, key=key, replay_window=None, encap=encap)
        sh.ns(NS_B, ["ip", "xfrm", "policy", "add", "src", f"{inner_src}/32", "dst", f"{inner_dst}/32", "dir", "in",
                     "tmpl", "src", local, "dst", ADDR_B, "proto", "esp", "mode", "tunnel"])
    for inner in (INNER_B, INNER2_B):
        sh.ns(NS_B, ["ip", "addr", "add", f"{inner}/32", "dev", "lo"])
    wire = is_udp_to(ESP_IN_UDP_PORT) if encap else is_proto(PROTO_ESP)
    flow1 = Flow(stack="esp_two_clients", src=INNER_A, dst=INNER_B, port=APP_PORT, wire_filter=wire, esp=True,
                 encap_udp=encap, outer_proto=PROTO_UDP if encap else PROTO_ESP,
                 outer_dport=ESP_IN_UDP_PORT if encap else None)
    flow2 = Flow(stack="esp_two_clients", src=INNER2_A, dst=INNER2_B, port=APP_PORT, wire_filter=wire, esp=True,
                 encap_udp=encap, outer_proto=PROTO_UDP if encap else PROTO_ESP,
                 outer_dport=ESP_IN_UDP_PORT if encap else None)
    return flow1, flow2


# --- ECN mangler (P13) ---------------------------------------------------------------

ECN_CE = 0x03
ECN_ECT0 = 0x02


def ecn_mangler(tos: int) -> list[str]:
    """Rewrite the outer ToS byte and recompute the IPv4 header checksum.

    The ``pedit ip tos`` / ``csum ip4h`` pair is the one round 1 used for its
    inert ToS rewrite (P11c), which worked on this iproute2; the value is the
    only difference between the ECT(0) and CE cases.
    """
    return ["action", "pedit", "ex", "munge", "ip", "tos", "set", hex(tos),
            "pipe", "action", "csum", "ip4h"]


def install_ecn_mangler(sh: Shell, flow: Flow, tos: int) -> None:
    """Set the outer ECN codepoint on ``vN2`` egress for this flow only."""
    sh.ns(NS_N, ["tc", "qdisc", "add", "dev", "vN2", "clsact"])
    match = ["match", "ip", "protocol", str(flow.outer_proto), "0xff"]
    if flow.outer_dport is not None:
        match += ["match", "ip", "dport", str(flow.outer_dport), "0xffff"]
    sh.ns(NS_N, ["tc", "filter", "add", "dev", "vN2", "egress", "protocol", "ip", "prio", "1", "u32", *match,
                 *ecn_mangler(tos)])


STACK_BUILDERS = {
    "ipip": setup_ipip,
    "wireguard": setup_wireguard,
    "esp_tunnel": setup_esp_tunnel,
}

__all__ = [
    "APP_PORT",
    "ECN_CE",
    "ECN_ECT0",
    "ESP_IN_UDP_PORT",
    "Flow",
    "PROBE_PORT",
    "STACK_BUILDERS",
    "install_ecn_mangler",
    "setup_esp_tunnel",
    "setup_esp_two_clients",
    "setup_ipip",
    "setup_wireguard",
]
