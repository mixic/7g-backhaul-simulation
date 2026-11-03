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

"""Toy authenticated encryption used by the layering testbed.

This is an encrypt-then-MAC construction built from HMAC-SHA-256 and a
counter-mode keystream.  It exists so that the testbed can observe
authentication acceptance and integrity scopes deterministically across
Python, SimPy and Linux data planes.  It is **not** a cryptographic design and
the testbed makes no security claim about it.
"""

from __future__ import annotations

import hashlib
import hmac

TAG_BYTES = 16
NONCE_BYTES = 12

#: Stipulated test key.  It is printed in the source on purpose: the testbed
#: measures authentication scope, never key secrecy.
KEY = b"7g-layering-testbed-key-v1-not-secret"


def nonce_for(uid: str, part: int, plaintext: bytes) -> bytes:
    """Deterministic 12-byte nonce for one layer/part/plaintext triple."""
    digest = hashlib.sha256(
        KEY + uid.encode("ascii") + int(part).to_bytes(2, "big") + plaintext
    ).digest()
    return digest[:NONCE_BYTES]


def keystream(nonce: bytes, length: int) -> bytes:
    """HMAC-SHA-256 counter-mode keystream."""
    if length < 0:
        raise ValueError("Keystream length must be non-negative.")
    blocks: list[bytes] = []
    produced = 0
    counter = 0
    while produced < length:
        block = hmac.new(
            KEY,
            b"keystream" + nonce + counter.to_bytes(8, "big"),
            hashlib.sha256,
        ).digest()
        blocks.append(block)
        produced += len(block)
        counter += 1
    return b"".join(blocks)[:length]


def xor(data: bytes, stream: bytes) -> bytes:
    if len(data) != len(stream):
        raise ValueError("XOR operands must have equal length.")
    return bytes(left ^ right for left, right in zip(data, stream))


def tag(nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """Truncated HMAC tag over nonce, ciphertext and associated data."""
    return hmac.new(
        KEY,
        b"tag" + nonce + ciphertext + aad,
        hashlib.sha256,
    ).digest()[:TAG_BYTES]
