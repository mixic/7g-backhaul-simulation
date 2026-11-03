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

"""Typed, executable layer model for the layering testbed."""

from simulation.layering.layers import (
    AEAD_OVERHEAD_BYTES,
    FRAGMENT_HEADER_BYTES,
    PATH_MTU,
    SEQUENCE_HEADER_BYTES,
    TUNNEL_HEADER_BYTES,
    CompressLayer,
    EncryptLayer,
    FragmentLayer,
    Layer,
    SequenceLayer,
    TunnelLayer,
)
from simulation.layering.stack import (
    DecodeResult,
    MiddleboxSpec,
    RewriteReport,
    Stack,
    apply_middlebox,
)

__all__ = [
    "AEAD_OVERHEAD_BYTES",
    "FRAGMENT_HEADER_BYTES",
    "PATH_MTU",
    "SEQUENCE_HEADER_BYTES",
    "TUNNEL_HEADER_BYTES",
    "CompressLayer",
    "DecodeResult",
    "EncryptLayer",
    "FragmentLayer",
    "Layer",
    "MiddleboxSpec",
    "RewriteReport",
    "SequenceLayer",
    "Stack",
    "TunnelLayer",
    "apply_middlebox",
]
