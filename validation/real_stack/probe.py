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


"""Detect which kernel facilities exist, and turn gaps into NOT RUN reasons.

NOT RUN is a disposition of the frozen file (section 3): a case whose required
facility is missing is neither confirmed nor refuted.  Every facility is tried
for real inside a throw-away namespace; nothing outside it is touched.
"""

from __future__ import annotations

import os
import shutil

from .cases import Case
from .shell import CommandError, Shell
from .topology import disable_offload

PROBE_NS = "rsprobe"
_AH_KEY = "0x" + "11" * 32
_ESP_KEY = "0x" + "22" * 20

TOOLS = ("ip", "nft", "wg", "tc", "ethtool")

STACK_FACILITIES = {
    "ah_tunnel": ["xfrm_ah"],
    "esp_tunnel": ["xfrm_esp"],
    "esp_transport": ["xfrm_esp"],
    "wireguard": ["tool:wg", "wireguard"],
    "ipip_over_wg": ["tool:wg", "wireguard", "ipip"],
    "wg_over_ipip": ["tool:wg", "wireguard", "ipip"],
}


def requirements(case: Case) -> list[str]:
    needed = ["root", "tool:ip", "netns", "veth", *STACK_FACILITIES[case.stack]]
    if case.nat:
        needed += ["tool:nft", "nft_masq"]
    if case.mangler:
        needed += ["tool:tc", "tc_pedit_csum"]
    if case.needs_offload_off:
        needed += ["tool:ethtool", "offload"]
    return needed


def _try(shell: Shell, argv: list[object]) -> str | None:
    """``None`` on success, otherwise the first line of the error."""
    try:
        shell.run(argv)
    except CommandError as error:
        text = error.stderr.strip().splitlines()
        return text[0] if text else f"exit {error.returncode}"
    return None


def probe(shell: Shell) -> dict[str, str | None]:
    """Map facility name -> ``None`` (available) or a reason string (missing)."""
    result: dict[str, str | None] = {}
    geteuid = getattr(os, "geteuid", None)
    result["root"] = None if geteuid is not None and geteuid() == 0 else "not running as root"
    for tool in TOOLS:
        result[f"tool:{tool}"] = None if shutil.which(tool) else f"`{tool}` not installed"

    if result["tool:ip"] is not None or result["root"] is not None:
        reason = result["tool:ip"] or result["root"]
        for name in ("netns", "veth", "wireguard", "ipip", "xfrm_ah", "xfrm_esp", "nft_masq", "tc_pedit_csum", "offload"):
            result[name] = f"requires ip and root ({reason})"
        return result

    shell.run(["ip", "netns", "del", PROBE_NS], check=False)
    result["netns"] = _try(shell, ["ip", "netns", "add", PROBE_NS])
    if result["netns"] is not None:
        for name in ("veth", "wireguard", "ipip", "xfrm_ah", "xfrm_esp", "nft_masq", "tc_pedit_csum", "offload"):
            result[name] = f"requires network namespaces ({result['netns']})"
        return result
    try:
        result["veth"] = _try(shell, ["ip", "-n", PROBE_NS, "link", "add", "pv0", "type", "veth", "peer", "name", "pv1"])
        result["wireguard"] = _try(shell, ["ip", "-n", PROBE_NS, "link", "add", "wgp", "type", "wireguard"])
        result["ipip"] = _try(shell, ["ip", "-n", PROBE_NS, "link", "add", "ipp", "type", "ipip",
                                      "local", "192.0.2.1", "remote", "192.0.2.2"])
        result["xfrm_ah"] = _try(shell, ["ip", "-n", PROBE_NS, "xfrm", "state", "add", "src", "192.0.2.1", "dst", "192.0.2.2",
                                         "proto", "ah", "spi", "0x1", "mode", "tunnel", "auth-trunc", "hmac(sha256)", _AH_KEY, "128"])
        result["xfrm_esp"] = _try(shell, ["ip", "-n", PROBE_NS, "xfrm", "state", "add", "src", "192.0.2.1", "dst", "192.0.2.2",
                                          "proto", "esp", "spi", "0x2", "mode", "tunnel", "aead", "rfc4106(gcm(aes))", _ESP_KEY, "128"])
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
            steps = [
                ["tc", "qdisc", "add", "dev", "pv0", "clsact"],
                ["tc", "filter", "add", "dev", "pv0", "egress", "protocol", "ip", "prio", "1", "u32", "match", "ip", "protocol", "17", "0xff",
                 "action", "pedit", "ex", "munge", "udp", "len", "set", "9", "pipe", "action", "csum", "udp"],
            ]
            result["tc_pedit_csum"] = next((r for r in (_try(shell, ["ip", "netns", "exec", PROBE_NS, *s]) for s in steps) if r), None)
        else:
            result["tc_pedit_csum"] = "`tc` missing or veth unavailable"
        if result["tool:ethtool"] is None and result["veth"] is None:
            both = disable_offload(shell, PROBE_NS, "pv0") and disable_offload(shell, PROBE_NS, "pv1")
            result["offload"] = None if both else "veth TX/RX checksumming cannot be turned off (verified with `ethtool -k`)"
        else:
            result["offload"] = "`ethtool` missing or veth unavailable"
    finally:
        shell.run(["ip", "netns", "del", PROBE_NS], check=False)
    return result


def not_run_reason(case: Case, facilities: dict[str, str | None]) -> str | None:
    """Root causes only: facilities that failed merely because ``ip`` or namespaces are missing are collapsed."""
    missing = [(name, facilities.get(name) or "unknown") for name in requirements(case) if facilities.get(name, "unknown")]
    if not missing:
        return None
    roots = [(name, reason) for name, reason in missing if not reason.startswith("requires ")]
    chosen = roots or missing
    return "; ".join(f"{name}: {reason}" for name, reason in chosen)
