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


"""Real-stack harness for round 2 of the layering predictions (P13-P16).

The frozen predictions are ``docs/layering-real-stack-predictions-round2.md``.
This package is the executable form of that file; it reuses the round-1
primitives (``validation.real_stack.shell`` and the observation schema) and adds
what round 2 needs: an ECN mangler, ESP-in-UDP, a second client namespace,
fragment and replay-window capture, and depth gates.
"""

SOURCE = "linux_real_stack_round2"
