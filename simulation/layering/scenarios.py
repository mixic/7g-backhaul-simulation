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

"""Stipulated scenarios, corpora and frozen prediction cases.

Nothing in this module is measured from a deployed network.  The MTU, the
overheads, the loss rate, the seed sets and the corpus generator are
*stipulated* testbed parameters; only the zlib ratio of the corpus is measured
and recorded in ``docs/layering-predictions.md``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from itertools import permutations

from simulation.layering.layers import (
    CompressLayer,
    EncryptLayer,
    FragmentLayer,
    Layer,
    PATH_MTU,
    SequenceLayer,
    TunnelLayer,
)
from simulation.layering.stack import Stack

#: Stipulated i.i.d. per-fragment loss probability.
LOSS_P = 0.1

#: Stipulated paired seed sets.  Model and SimPy share the same seeds; Linux
#: uses one netem seed per run.
MODEL_SEEDS: tuple[int, ...] = tuple(range(1, 2001))
LINUX_RUNS = 40
LINUX_DATAGRAMS = 100

TEXT_SEED = 0x5EED1234
RANDOM_SEED = b"7g-layering-random-corpus-v1"

#: Synthetic pseudo-English corpus: consonant/vowel words from an LCG.
_CONS = "bcdfghjklmnpqrstvwz"
_VOW = "aeiou"


def _lcg(seed: int):
    state = seed & 0xFFFFFFFF
    while True:
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        yield state


def text_bytes(size: int) -> bytes:
    """Deterministic pseudo-English corpus of ``size`` bytes."""
    if size < 0:
        raise ValueError("Corpus size must be non-negative.")
    generator = _lcg(TEXT_SEED)
    out = bytearray()
    while len(out) < size:
        value = next(generator)
        syllables = 2 + (value % 2)
        for _ in range(syllables):
            value = next(generator)
            out.append(ord(_CONS[(value >> 3) % len(_CONS)]))
            out.append(ord(_VOW[(value >> 11) % len(_VOW)]))
        if (value >> 20) % 9 == 0:
            out.extend(b". ")
        else:
            out.append(32)
    return bytes(out[:size])


def random_bytes(size: int) -> bytes:
    """Deterministic incompressible corpus of ``size`` bytes."""
    if size < 0:
        raise ValueError("Corpus size must be non-negative.")
    return hashlib.shake_256(RANDOM_SEED).digest(size)


def loss_unit(seed: int, datagram: int, fragment: int) -> float:
    """Deterministic uniform draw for one fragment, independent across indices.

    The RFMP ``hash_unit`` mixes one integer and is not independent across
    adjacent fragment indices, which would bias all-fragments-survive
    probabilities.  A SHA-256 draw is used instead; the Linux run pairs on the
    netem seed rather than this value.
    """
    digest = hashlib.sha256(
        b"loss"
        + int(seed).to_bytes(8, "big")
        + int(datagram).to_bytes(4, "big")
        + int(fragment).to_bytes(4, "big")
    ).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def payload_bytes(spec: str) -> bytes:
    """Parse ``text:8192`` / ``random:12000`` payload specifications."""
    kind, _, size_text = spec.partition(":")
    size = int(size_text)
    if kind == "text":
        return text_bytes(size)
    if kind == "random":
        return random_bytes(size)
    raise ValueError(f"Unknown payload corpus: {spec!r}")


def make_stack(
    kinds: tuple[str, ...],
    aad: tuple[tuple[str, str], ...] = (),
    mtu: int = PATH_MTU,
    datagram_id: int = 1,
) -> Stack:
    """Build a stack from layer kinds in application order."""
    layers: list[Layer] = []
    for kind in kinds:
        if kind == "C":
            layers.append(CompressLayer())
        elif kind == "E":
            layers.append(EncryptLayer(aad=aad))
        elif kind == "T":
            layers.append(TunnelLayer())
        elif kind == "F":
            layers.append(FragmentLayer(mtu=mtu, datagram_id=datagram_id))
        elif kind == "S":
            layers.append(SequenceLayer())
        else:
            raise ValueError(f"Unknown layer kind: {kind!r}")
    return Stack(layers)


@dataclass(frozen=True)
class Case:
    prediction: str
    name: str
    kinds: tuple[str, ...]
    payload: str
    aad: tuple[tuple[str, str], ...] = ()
    target: tuple[str, str] | None = None
    rewrite: bytes | None = None
    max_depth: int | None = None
    loss: float = 0.0
    seeds: tuple[int, ...] = ()
    structural: bool = False

    def stack(self) -> Stack:
        return make_stack(self.kinds, self.aad)

    def data(self) -> bytes:
        return payload_bytes(self.payload)


def p1_cases() -> list[Case]:
    return [
        Case("P1", "C_to_E_text", ("C", "E"), "text:32768"),
        Case("P1", "E_to_C_text", ("E", "C"), "text:32768"),
        Case("P1", "C_to_E_random", ("C", "E"), "random:32768"),
        Case("P1", "E_to_C_random", ("E", "C"), "random:32768"),
    ]


def p2_cases() -> list[Case]:
    return [
        Case("P2", "E_to_F", ("E", "F"), "random:12000", loss=LOSS_P, seeds=MODEL_SEEDS),
        Case("P2", "F_to_E", ("F", "E"), "random:12000", loss=LOSS_P, seeds=MODEL_SEEDS),
    ]


def p3_cases() -> list[Case]:
    target = ("T", "src_port")
    return [
        Case(
            "P3",
            "aad_covers",
            ("E", "T"),
            "random:1200",
            aad=(target,),
            target=target,
            rewrite=b"\x9c\x40",
        ),
        Case(
            "P3",
            "aad_excludes",
            ("E", "T"),
            "random:1200",
            target=target,
            rewrite=b"\x9c\x40",
        ),
        Case(
            "P3",
            "inside_ciphertext",
            ("T", "E"),
            "random:1200",
            target=target,
            rewrite=b"\x9c\x40",
        ),
    ]


def p4_cases() -> list[Case]:
    return [
        Case("P4", ">".join(order), order, "random:1024")
        for order in permutations(("T", "E", "S"))
    ]


def p5_cases() -> list[Case]:
    return [
        Case("P5", "C_to_F", ("C", "F"), "text:8192", loss=LOSS_P, seeds=MODEL_SEEDS),
        Case("P5", "F_to_C", ("F", "C"), "text:8192", loss=LOSS_P, seeds=MODEL_SEEDS),
        Case(
            "P5",
            "control_C_to_F",
            ("C", "F"),
            "text:1000",
            loss=LOSS_P,
            seeds=MODEL_SEEDS,
        ),
        Case(
            "P5",
            "control_F_to_C",
            ("F", "C"),
            "text:1000",
            loss=LOSS_P,
            seeds=MODEL_SEEDS,
        ),
    ]


def _visible_formally(kinds: tuple[str, ...], layer: str) -> bool:
    index = kinds.index(layer)
    return not any(kind in {"E", "C"} for kind in kinds[index + 1 :])


def p6_cases() -> list[Case]:
    cases: list[Case] = []
    targets = (("T", "src_port"), ("S", "seq"))
    for kinds in permutations(("T", "E", "S")):
        for target in targets:
            if target[0] not in kinds:
                continue
            visible = _visible_formally(kinds, target[0])
            for depth in (1, 2, 3):
                variants = [("none", ())]
                if visible:
                    variants.append(("protect", (target,)))
                for aad_name, aad in variants:
                    cases.append(
                        Case(
                            "P6",
                            f"{'>'.join(kinds)}|{target[0]}.{target[1]}|d{depth}|{aad_name}",
                            kinds,
                            "random:1024",
                            aad=aad,
                            target=target,
                            rewrite=b"\x9c\x40" if target == ("T", "src_port") else b"\x00\x00\x00\x00\x00\x00\x00\x2a",
                            max_depth=depth,
                        )
                    )
    return cases


def p7_cases() -> list[Case]:
    return [
        Case(
            "P7",
            "fragment_length",
            ("T", "F"),
            "random:4096",
            target=("F", "length"),
            rewrite=b"\x00\x09",
            structural=True,
        ),
        Case(
            "P7",
            "tunnel_length",
            ("T", "F"),
            "random:4096",
            target=("T", "udp_len"),
            rewrite=b"\x00\x09",
            structural=True,
        ),
        Case(
            "P7",
            "inert_field",
            ("T", "F"),
            "random:4096",
            target=("T", "src_port"),
            rewrite=b"\x9c\x40",
        ),
    ]


def all_cases() -> list[Case]:
    return p1_cases() + p2_cases() + p3_cases() + p4_cases() + p5_cases() + p6_cases() + p7_cases()


#: Structural fields declared by the layer table.  Rewriting one of these can
#: break framing even when it is outside every integrity scope.
STRUCTURAL_FIELDS: frozenset[tuple[str, str]] = frozenset(
    {("F", "length"), ("F", "offset"), ("T", "udp_len")}
)
