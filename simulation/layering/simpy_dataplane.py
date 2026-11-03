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

"""SimPy data plane for the frozen layering predictions.

Datagrams are encoded by the shared codec and then handed to per-fragment
SimPy processes sharing one finite drop-tail queue
(:class:`simulation.link_queue.DropTailQueue`).  Loss uses the same
deterministic draws as the executable model, so the two orderings in P2 are
paired on the same seed.  Time is simulated but does not affect size or
authentication; the queue and event schedule are exercised so the codec does
not run on a single-threaded call path.
"""

from __future__ import annotations

from dataclasses import dataclass

import simpy

from simulation.layering.scenarios import Case, loss_unit
from simulation.layering.stack import DecodeResult, MiddleboxSpec
from simulation.link_queue import DropTailQueue

#: Stipulated link rate for the SimPy data plane; high enough that only the
#: stipuated netem-equivalent loss removes fragments.
CAPACITY_BPS = 100_000_000.0
QUEUE_LIMIT = 1000


@dataclass(frozen=True)
class SimOutcome:
    decode: DecodeResult
    wire_bytes: int
    fragment_count: int


def simulate_case(
    case: Case, seed: int, middlebox: MiddleboxSpec | None = None
) -> SimOutcome:
    stack = case.stack()
    encoded = stack.encode(case.data())
    env = simpy.Environment()
    queue = DropTailQueue(QUEUE_LIMIT)
    received: set[int] = set()

    def transmit(index: int, frame: bytes):
        yield env.timeout(index * 1e-6)
        service = len(frame) * 8.0 / CAPACITY_BPS
        outcome = queue.arrive(env.now, service)
        if outcome.dropped:
            return
        yield env.timeout(outcome.queue_delay_seconds + outcome.service_seconds)
        received.add(index)

    for index, frame in enumerate(encoded.parts):
        if loss_unit(seed, 0, index) < case.loss:
            continue
        env.process(transmit(index, frame))

    env.run()
    decode = stack.decode(encoded, received=received, middlebox=middlebox)
    return SimOutcome(
        decode=decode,
        wire_bytes=encoded.wire_bytes,
        fragment_count=encoded.fragment_count,
    )
