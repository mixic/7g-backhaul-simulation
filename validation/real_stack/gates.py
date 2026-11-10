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


"""Mutation and cause gates (section 3 of the frozen file), as pure functions.

A gate answers "did the experiment do what the case needs it to do?" before any
verdict is read.  A failed mutation gate makes a case INVALID; a failed cause
gate makes a predicted drop INCONCLUSIVE.  Neither is ever a refutation.
"""

from __future__ import annotations

from typing import Iterable, Mapping

Record = Mapping[str, object]

TOS_MARK = 0x10
SHORT_UDP_LENGTH = 9


def mutation_gate(
    kind: str,
    before: Iterable[Record],
    after: Iterable[Record],
    expected: int,
    *,
    original_src: str,
    nat_src: str,
) -> tuple[bool, str]:
    """Check that the targeted field changed (or, for ``none``, did not change).

    ``before`` is the capture at ``vA1`` egress, ``after`` the capture at ``vN2``
    egress (after NAT and after any mangler).  ``expected`` is the number of test
    packets the case sent; every one of them must show the mutation.
    """
    before = list(before)
    after = list(after)
    if len(before) < expected:
        return False, f"only {len(before)} of {expected} test packets seen before the middlebox"
    if len(after) < expected:
        return False, f"only {len(after)} of {expected} test packets seen after the middlebox"
    if kind == "none":
        changed = [r for r in after if r["src"] != original_src]
        return (not changed, "unmodified" if not changed else f"{len(changed)} packets unexpectedly changed source")
    if kind == "nat":
        translated = [r for r in after if r["src"] == nat_src]
        leaked = [r for r in after if r["src"] == original_src]
        ok = len(translated) >= expected and not leaked
        return ok, f"{len(translated)} translated, {len(leaked)} untranslated"
    if kind == "len9":
        mangled = [r for r in after if r.get("udp_len") == SHORT_UDP_LENGTH]
        pristine = [r for r in before if r.get("udp_len") == SHORT_UDP_LENGTH]
        ok = len(mangled) >= expected and not pristine
        return ok, f"{len(mangled)} packets with UDP length {SHORT_UDP_LENGTH} after the mangler"
    if kind == "tos":
        mangled = [r for r in after if r.get("tos") == TOS_MARK]
        pristine = [r for r in before if r.get("tos") == TOS_MARK]
        ok = len(mangled) >= expected and not pristine
        return ok, f"{len(mangled)} packets with ToS {TOS_MARK:#x} after the mangler"
    raise ValueError(f"unknown mutation kind: {kind}")


def cause_gate(case_id: str, metrics: Mapping[str, float], sent: int) -> tuple[bool, str]:
    """Frozen cause gates for every case that predicts a drop; ``True`` elsewhere."""
    xfrm = metrics.get("xfrm_in_error_delta", 0)
    csum = metrics.get("udp_in_csum_delta", 0)
    wg_rx = metrics.get("wg_rx_delta", 0)
    if case_id == "P8a":
        return xfrm > 0, f"XfrmIn*Error delta = {xfrm}"
    if case_id == "P11a":
        ok = csum > 0 or wg_rx == 0
        return ok, f"UdpInCsumErrors delta = {csum}, WireGuard rx delta = {wg_rx}"
    if case_id == "P11b":
        return wg_rx == 0, f"WireGuard rx delta = {wg_rx}"
    if case_id == "P12a":
        return csum >= sent, f"UdpInCsumErrors delta = {csum}, datagrams sent = {sent}"
    return True, "no cause gate for this case"
