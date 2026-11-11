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


"""Four namespaces for round 2: the round-1 topology plus a second client.

::

    rs2A  10.200.1.2/24 -- vA1 == vN1 --+                 +-- vN2 == vB2 -- rs2B 10.200.2.2/24
    rs2A2 10.200.3.2/24 -- vA3 == vN3 --+-- rs2N (router) -+
                                          10.200.1.1 / 10.200.3.1 / 10.200.2.1
                                          (ip_forward=1, optional nft masquerade on vN2 egress)

Names are prefixed ``rs2`` so an interrupted round-1 run and a round-2 run
cannot delete each other's namespaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from validation.real_stack.shell import CommandError, Shell
from validation.real_stack.topology import disable_offload

NS_A, NS_A2, NS_N, NS_B = "rs2A", "rs2A2", "rs2N", "rs2B"
ADDR_A, ADDR_A2 = "10.200.1.2", "10.200.3.2"
ADDR_N1, ADDR_N3, ADDR_N2 = "10.200.1.1", "10.200.3.1", "10.200.2.1"
ADDR_B = "10.200.2.2"
VETHS = {NS_A: ["vA1"], NS_A2: ["vA3"], NS_N: ["vN1", "vN3", "vN2"], NS_B: ["vB2"]}
ALL_VETHS = ("vA1", "vN1", "vA3", "vN3", "vN2", "vB2")


@dataclass
class Topology:
    shell: Shell
    nat: bool = False
    second_client: bool = False
    disable_offload: bool = True
    offload_disabled: bool = field(default=False, init=False)

    def build(self) -> "Topology":
        sh = self.shell
        names = [NS_A, NS_N, NS_B] + ([NS_A2] if self.second_client else [])
        for name in names:
            sh.run(["ip", "netns", "add", name])
            sh.ns(name, ["ip", "link", "set", "lo", "up"])
        sh.run(["ip", "link", "add", "vA1", "type", "veth", "peer", "name", "vN1"])
        sh.run(["ip", "link", "add", "vN2", "type", "veth", "peer", "name", "vB2"])
        sh.run(["ip", "link", "set", "vA1", "netns", NS_A])
        sh.run(["ip", "link", "set", "vN1", "netns", NS_N])
        sh.run(["ip", "link", "set", "vN2", "netns", NS_N])
        sh.run(["ip", "link", "set", "vB2", "netns", NS_B])
        addressing = [
            (NS_A, "vA1", f"{ADDR_A}/24"),
            (NS_N, "vN1", f"{ADDR_N1}/24"),
            (NS_N, "vN2", f"{ADDR_N2}/24"),
            (NS_B, "vB2", f"{ADDR_B}/24"),
        ]
        if self.second_client:
            sh.run(["ip", "link", "add", "vA3", "type", "veth", "peer", "name", "vN3"])
            sh.run(["ip", "link", "set", "vA3", "netns", NS_A2])
            sh.run(["ip", "link", "set", "vN3", "netns", NS_N])
            addressing += [
                (NS_A2, "vA3", f"{ADDR_A2}/24"),
                (NS_N, "vN3", f"{ADDR_N3}/24"),
            ]
        for ns, dev, addr in addressing:
            sh.ns(ns, ["ip", "addr", "add", addr, "dev", dev])
            sh.ns(ns, ["ip", "link", "set", dev, "mtu", "1500", "up"])
        sh.ns(NS_A, ["ip", "route", "add", "default", "via", ADDR_N1])
        sh.ns(NS_B, ["ip", "route", "add", "default", "via", ADDR_N2])
        if self.second_client:
            sh.ns(NS_A2, ["ip", "route", "add", "default", "via", ADDR_N3])
        sh.ns(NS_N, ["sysctl", "-qw", "net.ipv4.ip_forward=1"])
        for ns in names + [NS_N]:
            sh.ns(ns, ["sysctl", "-qw", "net.ipv4.conf.all.rp_filter=0"])
            sh.ns(ns, ["sysctl", "-qw", "net.ipv4.conf.default.rp_filter=0"])
        # A 100 ms netem delay queues thousands of packets in P16; the receiver
        # socket buffer and the sniffer tap must hold the whole burst or P16
        # loses or under-captures for the wrong reason.
        for ns in names:
            sh.ns(ns, ["sysctl", "-qw", "net.core.rmem_max=67108864"])
            sh.ns(ns, ["sysctl", "-qw", "net.core.rmem_default=67108864"])
        if self.disable_offload:
            self._disable_offload(names)
        if self.nat:
            self._enable_nat()
        return self

    def _disable_offload(self, names: list[str]) -> None:
        ok = True
        for ns in names:
            for dev in VETHS[ns]:
                if self.shell.ns(ns, ["ip", "link", "show", dev], check=False).returncode != 0:
                    continue  # the second client is absent in most cases
                ok = disable_offload(self.shell, ns, dev) and ok
        self.offload_disabled = ok

    def _enable_nat(self) -> None:
        sh = self.shell
        sh.ns(NS_N, ["nft", "add", "table", "ip", "nat"])
        sh.ns(NS_N, ["nft", "add", "chain", "ip", "nat", "post", "{ type nat hook postrouting priority 100 ; }"])
        sh.ns(NS_N, ["nft", "add", "rule", "ip", "nat", "post", "oifname", "vN2", "masquerade"])

    def teardown(self) -> None:
        for name in (NS_A, NS_A2, NS_N, NS_B):
            try:
                self.shell.run(["ip", "netns", "del", name], check=False)
            except CommandError:
                pass


def cleanup_leftovers(shell: Shell) -> None:
    """Remove round-2 namespaces and veths leaked by an interrupted earlier run."""
    for name in (NS_A, NS_A2, NS_N, NS_B):
        shell.run(["ip", "netns", "del", name], check=False)
    for veth in ALL_VETHS:
        shell.run(["ip", "link", "del", veth], check=False)
