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

"""P1-P5 commutation guardrails for the Cognitive Stack Compiler.

The Oracle (an LLM) proposes an encapsulation-layer ordering; this module
validates it against the formal rules frozen in ``docs/layering-predictions.md``
and, on a violation, forces the canonical valid stack.  Only the rules whose
outcome the predictions actually froze are enforced:

  P1  encrypt-before-compress inflates a compressible payload  (size)
  P5  fragment-before-compress raises the fragment count       (delivery)
  P3  authenticating the NAT-rewritten outer source breaks auth

P2 (encrypt-before-fragment is cheaper) and P4 (fixed-overhead layers commute)
are soft preferences, not hard constraints, so they are not enforced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Layer kind used by the layering codec (``simulation.layering.layers``).
C = "C"  # compress
E = "E"  # encrypt
F = "F"  # fragment
T = "T"  # tunnel (always outermost; NAT rewrites its source address)


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str


@dataclass(frozen=True)
class GuardrailResult:
    """Outcome of validating one Oracle proposal."""

    order: tuple[str, ...]            # corrected C/E/F order, innermost first
    authenticate_outer: bool          # corrected flag (E authenticates T.src_addr)
    violations: tuple[Violation, ...] = ()

    @property
    def intervened(self) -> bool:
        return bool(self.violations)


def canonical_order(compressible: bool) -> tuple[str, ...]:
    """The P1-P5-optimal C/E/F order; ``T`` is always appended outermost.

    Compress-first is never worse on incompressible data (zlib framing adds a
    few bytes once) and is strictly better on compressible data, and
    encrypt-before-fragment adds the AEAD overhead once instead of once per
    fragment, so ``C -> E -> F`` dominates the other five permutations for the
    payload classes this experiment uses.
    """
    return (C, E, F)


def validate(
    order,
    authenticate_outer: bool,
    state: dict,
) -> GuardrailResult:
    """Validate ``(order, authenticate_outer)`` against P1, P5 and P3.

    ``order`` is a sequence of ``C``/``E``/``F`` kind characters, innermost
    first.  ``state`` must carry ``compressible`` (bool) and ``nat`` (bool).
    """
    kinds = [k for k in order]
    compressible = bool(state.get("compressible", True))
    nat = bool(state.get("nat", False))

    violations: list[Violation] = []

    # P1: E before C on compressible data wastes the compressor (ciphertext is
    # incompressible), inflating the wire size.
    if (
        compressible
        and C in kinds
        and E in kinds
        and kinds.index(E) < kinds.index(C)
    ):
        violations.append(
            Violation(
                "P1",
                "Encrypt before Compress inflates a compressible payload "
                "(ciphertext is incompressible).",
            )
        )

    # P5: F before C on compressible data fragments before compression, which
    # has less per-fragment context and raises the fragment count.
    if (
        compressible
        and C in kinds
        and F in kinds
        and kinds.index(F) < kinds.index(C)
    ):
        violations.append(
            Violation(
                "P5",
                "Fragment before Compress splits the payload before it is "
                "compressed, raising the fragment count.",
            )
        )

    # P3: authenticating the outer source address is broken by NAT (RFC 4302;
    # RFC 3715).  The NAT rewrites T.src_addr on the wire.
    if nat and authenticate_outer:
        violations.append(
            Violation(
                "P3",
                "Authenticating the outer source address is broken by NAT "
                "(RFC 4302 / RFC 3715).",
            )
        )

    if violations:
        return GuardrailResult(
            order=canonical_order(compressible),
            authenticate_outer=False,
            violations=tuple(violations),
        )

    return GuardrailResult(
        order=tuple(kinds),
        authenticate_outer=bool(authenticate_outer),
    )
