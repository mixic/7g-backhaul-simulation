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


"""Three network namespaces, two veth pairs, optional NAT (section 2 of the frozen file).

::

    rsA 10.200.1.2/24 -- vA1 == vN1 -- rsN -- vN2 == vB2 -- rsB 10.200.2.2/24
                           10.200.1.1   10.200.2.1
                           (ip_forward=1, optional nft masquerade on vN2 egress)

Veth MTU is 1500 and no netem loss is installed anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .shell import CommandError, Shell

NS_A, NS_N, NS_B = "rsA", "rsN", "rsB"
ADDR_A, ADDR_N1, ADDR_N2, ADDR_B = "10.200.1.2", "10.200.1.1", "10.200.2.1", "10.200.2.2"
VETHS = {NS_A: ["vA1"], NS_N: ["vN1", "vN2"], NS_B: ["vB2"]}
OFFLOAD_FLAGS = ["tx", "off", "rx", "off", "tso", "off", "gso", "off", "gro", "off", "sg", "off"]
REQUIRED_OFF = ("tx-checksumming", "rx-checksumming")


def parse_offload_off(text: str) -> bool:
    """True iff ``ethtool -k`` output shows TX and RX checksumming off.

    Both matter: veth marks a received packet CHECKSUM_UNNECESSARY (skipping UDP
    checksum verification) when RX checksumming is on, and leaves sender-side
    partial checksums unfinished when TX checksumming is on.
    """
    seen: dict[str, str] = {}
    for line in text.splitlines():
        name, _, value = line.partition(":")
        if name.strip() in REQUIRED_OFF:
            seen[name.strip()] = value.strip().split()[0] if value.strip() else ""
    return all(seen.get(name) == "off" for name in REQUIRED_OFF)


def disable_offload(shell: Shell, namespace: str, device: str) -> bool:
    """Turn offloads off, then *verify* with ``ethtool -k``; the exit code of ``-K`` is not trusted."""
    shell.ns(namespace, ["ethtool", "-K", device, *OFFLOAD_FLAGS], check=False)
    if shell.dry_run:
        shell.ns(namespace, ["ethtool", "-k", device], check=False)
        return True
    return parse_offload_off(shell.ns(namespace, ["ethtool", "-k", device], check=False).stdout)


@dataclass
class Topology:
    shell: Shell
    nat: bool = False
    disable_offload: bool = True
    offload_disabled: bool = field(default=False, init=False)

    def build(self) -> "Topology":
        sh = self.shell
        for name in (NS_A, NS_N, NS_B):
            sh.run(["ip", "netns", "add", name])
            sh.ns(name, ["ip", "link", "set", "lo", "up"])
        sh.run(["ip", "link", "add", "vA1", "type", "veth", "peer", "name", "vN1"])
        sh.run(["ip", "link", "add", "vN2", "type", "veth", "peer", "name", "vB2"])
        sh.run(["ip", "link", "set", "vA1", "netns", NS_A])
        sh.run(["ip", "link", "set", "vN1", "netns", NS_N])
        sh.run(["ip", "link", "set", "vN2", "netns", NS_N])
        sh.run(["ip", "link", "set", "vB2", "netns", NS_B])
        for ns, dev, addr in (
            (NS_A, "vA1", f"{ADDR_A}/24"),
            (NS_N, "vN1", f"{ADDR_N1}/24"),
            (NS_N, "vN2", f"{ADDR_N2}/24"),
            (NS_B, "vB2", f"{ADDR_B}/24"),
        ):
            sh.ns(ns, ["ip", "addr", "add", addr, "dev", dev])
            sh.ns(ns, ["ip", "link", "set", dev, "mtu", "1500", "up"])
        sh.ns(NS_A, ["ip", "route", "add", "default", "via", ADDR_N1])
        sh.ns(NS_B, ["ip", "route", "add", "default", "via", ADDR_N2])
        sh.ns(NS_N, ["sysctl", "-qw", "net.ipv4.ip_forward=1"])
        for ns in (NS_A, NS_N, NS_B):
            sh.ns(ns, ["sysctl", "-qw", "net.ipv4.conf.all.rp_filter=0"])
            sh.ns(ns, ["sysctl", "-qw", "net.ipv4.conf.default.rp_filter=0"])
        if self.disable_offload:
            self._disable_offload()
        if self.nat:
            self._enable_nat()
        return self

    def _disable_offload(self) -> None:
        """Best effort; the outcome is recorded because checksum cases depend on it."""
        ok = True
        for ns, devices in VETHS.items():
            for dev in devices:
                ok = disable_offload(self.shell, ns, dev) and ok
        self.offload_disabled = ok

    def _enable_nat(self) -> None:
        sh = self.shell
        sh.ns(NS_N, ["nft", "add", "table", "ip", "nat"])
        sh.ns(NS_N, ["nft", "add", "chain", "ip", "nat", "post", "{ type nat hook postrouting priority 100 ; }"])
        sh.ns(NS_N, ["nft", "add", "rule", "ip", "nat", "post", "oifname", "vN2", "masquerade"])

    def teardown(self) -> None:
        for name in (NS_A, NS_N, NS_B):
            try:
                self.shell.run(["ip", "netns", "del", name], check=False)
            except CommandError:
                pass


def cleanup_leftovers(shell: Shell) -> None:
    """Remove namespaces and leaked veths from an interrupted earlier run.

    ``ip netns del`` reclaims the interfaces inside a namespace, but a run that was
    killed *between* ``ip link add`` and ``ip link set ... netns`` can leave a veth
    pair in the root namespace, which makes the next ``ip link add`` fail with
    "File exists". Delete those explicitly.
    """
    for name in (NS_A, NS_N, NS_B):
        shell.run(["ip", "netns", "del", name], check=False)
    for veth in ("vA1", "vN1", "vN2", "vB2"):
        shell.run(["ip", "link", "del", veth], check=False)
