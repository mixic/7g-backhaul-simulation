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

"""Round 3 of the real-stack layering follow-up (P17).

This package is the executable form of
``docs/layering-real-stack-predictions-round3.md``, frozen at commit
``285c8e9`` before any round-3 harness code existed.  It reuses round 2's
topology, ESP setup, counters and receiver, and adds:

* a rate-limited sender for a gated depth (P17a);
* raw AF_PACKET capture and reinjection at an exact displacement (P17b-P17e);
* explicit legacy/ESN anti-replay mode recording (P17f).
"""
