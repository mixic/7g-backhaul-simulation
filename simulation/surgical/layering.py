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

"""Layering model for the fiber->satellite boundary (Experiment 3, H3).

The anti-cheat rule demands real cryptography: authentication uses AES-GCM from
the ``cryptography`` library, not the toy HMAC construction used elsewhere in
this repository for the layered-protocol testbed.  Compression uses zlib.

The four layer orderings from the layering predictions are applied to a payload
crossing a medium boundary whose path MTU drops from the fiber side to the
satellite side:

* ``CF``  compress then fragment
* ``FC``  fragment then compress (per-fragment compression)
* ``EF``  encrypt then fragment
* ``FE``  fragment then encrypt (per-fragment tag and nonce)

Fragmentation is to the satellite MTU with a stipulated 8-byte fragment header.
The function returns the fragment count, wire bytes, the realised fragment drop
rate under a per-fragment loss probability, the reassembly (reorder) buffer
occupancy, and the object loss rate.  The encryption key is freshly generated
per call: the testbed measures overhead and loss, never key secrecy.
"""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FRAG_HEADER_BYTES = 8
TAG_BYTES = 16
NONCE_BYTES = 12


@dataclass
class BoundaryResult:
    ordering: str
    fragments: int
    wire_bytes: int
    fragment_drop_rate: float      # realised, per seed
    reorder_occupancy: int         # fragments buffered awaiting reassembly
    object_loss_rate: float        # 1.0 if any fragment was lost else 0.0
    encrypted: bool
    compressed: bool


def _fragment(data: bytes, mtu: int) -> list[bytes]:
    chunk = max(1, mtu - FRAG_HEADER_BYTES)
    return [data[i:i + chunk] for i in range(0, len(data), chunk)]


def _nonce(rng: random.Random, part: int) -> bytes:
    return rng.randbytes(NONCE_BYTES)


def measure_boundary(
    payload_size: int,
    ordering: str,
    fiber_mtu: int = 1500,
    satellite_mtu: int = 500,
    drop_probability: float = 0.01,
    seed: int = 0,
) -> BoundaryResult:
    """Apply a layer ordering to one payload crossing the medium boundary."""
    ordering = ordering.upper()
    if set(ordering) - {"C", "E", "F"} or "F" not in ordering:
        raise ValueError(f"ordering must contain F and letters C/E/F, got {ordering!r}")

    rng = random.Random(seed)
    payload = rng.randbytes(payload_size)
    key = AESGCM.generate_key(bit_length=128)
    aes = AESGCM(key)

    data: object = payload
    fragmented = False
    for letter in ordering:
        if letter == "F":
            data = _fragment(data if isinstance(data, bytes) else b"".join(data),
                             satellite_mtu)
            fragmented = True
        elif letter == "C":
            if fragmented:
                data = [zlib.compress(f) for f in data]  # type: ignore[union-attr]
            else:
                data = zlib.compress(data)  # type: ignore[arg-type]
        elif letter == "E":
            if fragmented:
                data = [aes.encrypt(_nonce(rng, i), f, None)
                        for i, f in enumerate(data)]  # type: ignore[union-attr]
            else:
                data = aes.encrypt(_nonce(rng, 0), data, None)  # type: ignore[arg-type]

    fragments = data if fragmented else [data]  # type: ignore[list-item]
    n = len(fragments)
    wire_bytes = sum(len(f) + FRAG_HEADER_BYTES for f in fragments)  # type: ignore[arg-type]

    dropped = sum(1 for _ in fragments if rng.random() < drop_probability)
    return BoundaryResult(
        ordering=ordering,
        fragments=n,
        wire_bytes=wire_bytes,
        fragment_drop_rate=dropped / n if n else 0.0,
        reorder_occupancy=n,
        object_loss_rate=1.0 if dropped else 0.0,
        encrypted="E" in ordering,
        compressed="C" in ordering,
    )


ORDERINGS = ("CF", "FC", "EF", "FE")
