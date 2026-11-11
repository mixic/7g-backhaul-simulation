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


"""Detect the kernel facilities round 2 needs and turn gaps into NOT RUN reasons.

Every facility is tried for real inside a throw-away namespace.  A case whose
required facility is missing is NOT RUN, which is neither confirmation nor
refutation (frozen section 3).
"""

from __future__ import annotations

import os
import shutil

from validation.real_stack.shell import CommandError, Shell
from validation.real_stack.topology import disable_offload

from .cases import Case
from .predictions import P14_CASES

PROBE_NS = "rs2probe"
_ESP_KEY = "0x" + "22" * 20
TOOLS = ("ip", "nft", "wg", "tc", "ethtool")


def requirements(case: Case) -> list[str]:
    needed = ["root", "tool:ip", "netns", "veth"]
    if case.kind == "p13":
        if case.stack == "ipip":
            needed += ["ipip"]
        elif case.stack == "wireguard":
            needed += ["tool:wg", "wireguard"]
        else:
            needed += ["xfrm_esp"]
        needed += ["tool:tc", "tc_pedit_tos"]
    elif case.kind == "p14":
        needed += ["xfrm_esp"]
        if case.encap:
            needed += ["espinudp"]
        else:
            needed += ["tool:nft", "nft_masq"]
        if P14_CASES[case.id][2]:
            needed += ["tool:nft", "nft_masq"]
    elif case.kind == "p15":
        needed += ["tool:wg", "wireguard"]
    elif case.kind == "p16":
        needed += ["tool:tc", "tc_netem_reorder", "replay_window"]
        if case.stack == "wireguard":
            needed += ["tool:wg", "wireguard"]
        else:
            needed += ["xfrm_esp"]
    if case.kind != "p13":
        needed += ["tool:ethtool", "offload"]
    return needed


def _try(shell: Shell, argv: list[object]) -> str | None:
    try:
        shell.run(argv)
    except CommandError as error:
        text = error.stderr.strip().splitlines()
        return text[0] if text else f"exit {error.returncode}"
    return None


def probe(shell: Shell) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    geteuid = getattr(os, "geteuid", None)
    result["root"] = None if geteuid is not None and geteuid() == 0 else "not running as root"
    for tool in TOOLS:
        result[f"tool:{tool}"] = None if shutil.which(tool) else f"`{tool}` not installed"

    if result["tool:ip"] is not None or result["root"] is not None:
        reason = result["tool:ip"] or result["root"]
        for name in ("netns", "veth", "wireguard", "ipip", "xfrm_esp", "nft_masq", "tc_pedit_tos",
                     "tc_netem_reorder", "espinudp", "replay_window", "offload"):
            result[name] = f"requires ip and root ({reason})"
        return result

    shell.run(["ip", "netns", "del", PROBE_NS], check=False)
    result["netns"] = _try(shell, ["ip", "netns", "add", PROBE_NS])
    if result["netns"] is not None:
        for name in ("veth", "wireguard", "ipip", "xfrm_esp", "nft_masq", "tc_pedit_tos",
                     "tc_netem_reorder", "espinudp", "replay_window", "offload"):
            result[name] = f"requires network namespaces ({result['netns']})"
        return result
    try:
        result["veth"] = _try(shell, ["ip", "-n", PROBE_NS, "link", "add", "pv0", "type", "veth", "peer", "name", "pv1"])
        result["wireguard"] = _try(shell, ["ip", "-n", PROBE_NS, "link", "add", "wgp", "type", "wireguard"])
        result["ipip"] = _try(shell, ["ip", "-n", PROBE_NS, "link", "add", "ipp", "type", "ipip",
                                      "local", "192.0.2.1", "remote", "192.0.2.2"])
        result["xfrm_esp"] = _try(shell, ["ip", "-n", PROBE_NS, "xfrm", "state", "add", "src", "192.0.2.1",
                                          "dst", "192.0.2.2", "proto", "esp", "spi", "0x2", "mode", "tunnel",
                                          "aead", "rfc4106(gcm(aes))", _ESP_KEY, "128"])
        result["replay_window"] = _try(shell, ["ip", "-n", PROBE_NS, "xfrm", "state", "add", "src", "192.0.2.1",
                                               "dst", "192.0.2.3", "proto", "esp", "spi", "0x3", "mode", "tunnel",
                                               "replay-window", "32", "aead", "rfc4106(gcm(aes))", _ESP_KEY, "128"])
        result["espinudp"] = _try(shell, ["ip", "-n", PROBE_NS, "xfrm", "state", "add", "src", "192.0.2.1",
                                          "dst", "192.0.2.4", "proto", "esp", "spi", "0x4", "mode", "tunnel",
                                          "encap", "espinudp", "4500", "4500", "0.0.0.0",
                                          "aead", "rfc4106(gcm(aes))", _ESP_KEY, "128"])
        if result["tool:nft"] is None:
            steps = [
                ["nft", "add", "table", "ip", "nat"],
                ["nft", "add", "chain", "ip", "nat", "post", "{ type nat hook postrouting priority 100 ; }"],
                ["nft", "add", "rule", "ip", "nat", "post", "oifname", "pv0", "masquerade"],
            ]
            result["nft_masq"] = next((r for r in (_try(shell, ["ip", "netns", "exec", PROBE_NS, *s]) for s in steps) if r), None)
        else:
            result["nft_masq"] = "`nft` not installed"
        if result["tool:tc"] is None and result["veth"] is None:
            shell.ns(PROBE_NS, ["ip", "link", "set", "pv0", "up"], check=False)
            pedit = [
                ["tc", "qdisc", "add", "dev", "pv0", "clsact"],
                ["tc", "filter", "add", "dev", "pv0", "egress", "protocol", "ip", "prio", "1", "u32",
                 "match", "ip", "protocol", "4", "0xff",
                 "action", "pedit", "ex", "munge", "ip", "tos", "set", "0x03", "pipe", "action", "csum", "ip4h"],
            ]
            result["tc_pedit_tos"] = next((r for r in (_try(shell, ["ip", "netns", "exec", PROBE_NS, *s]) for s in pedit) if r), None)
            netem = [["tc", "qdisc", "add", "dev", "pv0", "root", "netem", "delay", "100ms", "reorder", "25%",
                      "limit", "100000"]]
            result["tc_netem_reorder"] = next((r for r in (_try(shell, ["ip", "netns", "exec", PROBE_NS, *s]) for s in netem) if r), None)
        else:
            result["tc_pedit_tos"] = "`tc` missing or veth unavailable"
            result["tc_netem_reorder"] = "`tc` missing or veth unavailable"
        if result["tool:ethtool"] is None and result["veth"] is None:
            both = disable_offload(shell, PROBE_NS, "pv0") and disable_offload(shell, PROBE_NS, "pv1")
            result["offload"] = None if both else "veth TX/RX checksumming cannot be turned off (verified with `ethtool -k`)"
        else:
            result["offload"] = "`ethtool` missing or veth unavailable"
    finally:
        shell.run(["ip", "netns", "del", PROBE_NS], check=False)
    return result


def not_run_reason(case: Case, facilities: dict[str, str | None]) -> str | None:
    missing = [(name, facilities.get(name) or "unknown") for name in requirements(case) if facilities.get(name, "unknown")]
    if not missing:
        return None
    roots = [(name, reason) for name, reason in missing if not reason.startswith("requires ")]
    chosen = roots or missing
    return "; ".join(f"{name}: {reason}" for name, reason in chosen)


__all__ = ["not_run_reason", "probe", "requirements"]
