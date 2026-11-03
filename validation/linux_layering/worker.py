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

"""Linux network-namespace worker for the layering testbed.

Run as root inside a container or WSL2.  The worker creates two namespaces
joined by a veth pair, puts a TUN device in each, applies ``tc netem`` loss on
the veth, and drives the same frozen cases as the executable model.  It writes
long-form observations with ``source = linux_netns``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation.layering.experiments import METRIC_UNITS  # noqa: E402
from simulation.layering.scenarios import (  # noqa: E402
    LINUX_DATAGRAMS,
    LINUX_RUNS,
    Case,
    p1_cases,
    p2_cases,
    p3_cases,
    p4_cases,
    p5_cases,
    p6_cases,
    p7_cases,
)
from validation.layering._io import write_observations  # noqa: E402

APP = REPO / "validation" / "linux_layering" / "app.py"
RELAY = REPO / "validation" / "linux_layering" / "tun_relay.py"
NS_A = "layA"
NS_B = "layB"
TUN_A = "tunA"
TUN_B = "tunB"


def _run(arguments: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, check=check, capture_output=True, text=True)


class Harness:
    def __init__(self) -> None:
        self.environment = os.environ.copy()
        self.environment["PYTHONPATH"] = str(REPO)
        self.temporary = Path(tempfile.mkdtemp(prefix="layering_linux_"))

    def setup(self) -> None:
        self.teardown()
        self._run(["ip", "netns", "add", NS_A])
        self._run(["ip", "netns", "add", NS_B])
        self._run(["ip", "link", "add", "vA", "type", "veth", "peer", "name", "vB"])
        self._run(["ip", "link", "set", "vA", "netns", NS_A])
        self._run(["ip", "link", "set", "vB", "netns", NS_B])
        for namespace in (NS_A, NS_B):
            self._run(["ip", "-n", namespace, "link", "set", "lo", "up"])
        self._run(["ip", "-n", NS_A, "link", "set", "vA", "up", "mtu", "40000"])
        self._run(["ip", "-n", NS_B, "link", "set", "vB", "up", "mtu", "40000"])
        self._run(["ip", "-n", NS_A, "addr", "add", "10.200.0.1/24", "dev", "vA"])
        self._run(["ip", "-n", NS_B, "addr", "add", "10.200.0.2/24", "dev", "vB"])
        for namespace, tun in ((NS_A, TUN_A), (NS_B, TUN_B)):
            self._run(
                ["ip", "netns", "exec", namespace, "ip", "tuntap", "add", "dev", tun, "mode", "tun"]
            )
        self._run(
            ["ip", "-n", NS_A, "addr", "add", "10.201.0.1", "peer", "10.201.0.2", "dev", TUN_A]
        )
        self._run(
            ["ip", "-n", NS_B, "addr", "add", "10.201.0.2", "peer", "10.201.0.1", "dev", TUN_B]
        )
        self._run(["ip", "-n", NS_A, "link", "set", TUN_A, "up", "mtu", "40000"])
        self._run(["ip", "-n", NS_B, "link", "set", TUN_B, "up", "mtu", "40000"])

    def _run(self, arguments: list[str]) -> None:
        result = _run(arguments, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(arguments)}\n{result.stderr}"
            )

    def netem(self, loss: float, seed: int) -> None:
        self._run(
            [
                "ip",
                "netns",
                "exec",
                NS_A,
                "tc",
                "qdisc",
                "replace",
                "dev",
                "vA",
                "root",
                "netem",
                "loss",
                f"{100.0 * loss:.1f}%",
                "seed",
                str(seed),
            ]
        )

    def teardown(self) -> None:
        _run(["ip", "netns", "delete", NS_A], check=False)
        _run(["ip", "netns", "delete", NS_B], check=False)

    def close(self) -> None:
        self.teardown()
        shutil.rmtree(self.temporary, ignore_errors=True)

    def _start(self, namespace: str, arguments: list[str], log_name: str):
        log_path = self.temporary / log_name
        handle = log_path.open("wb")
        process = subprocess.Popen(
            ["ip", "netns", "exec", namespace, sys.executable] + arguments,
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=self.environment,
        )
        process._layering_log = handle  # type: ignore[attr-defined]
        return process

    @staticmethod
    def _reap(process, timeout: float = 15.0) -> None:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        handle = getattr(process, "_layering_log", None)
        if handle is not None:
            handle.close()

    def run_once(self, case: Case, run_seed: int, datagrams: int) -> dict[str, object]:
        self.netem(case.loss, run_seed)
        src_result = self.temporary / "src.json"
        dst_result = self.temporary / "dst.json"
        for path in (src_result, dst_result):
            if path.exists():
                path.unlink()
        dst_app = self._start(NS_B, [str(APP), "recv", "--timeout", "3"], "dst_app.log")
        dst_relay = self._start(
            NS_B,
            [
                str(RELAY),
                "--role",
                "dst",
                "--tun",
                TUN_B,
                "--local",
                "10.200.0.2",
                "--peer",
                "10.200.0.1",
                "--stack",
                ",".join(case.kinds),
                "--aad",
                ",".join(f"{layer}.{name}" for layer, name in case.aad),
                "--target",
                f"{case.target[0]}.{case.target[1]}" if case.target else "",
                "--rewrite",
                (case.rewrite or b"").hex(),
                "--max-depth",
                str(case.max_depth) if case.max_depth is not None else "-1",
                "--datagrams",
                str(datagrams),
                "--result",
                str(dst_result),
            ],
            "dst_relay.log",
        )
        time.sleep(0.3)
        src_relay = self._start(
            NS_A,
            [
                str(RELAY),
                "--role",
                "src",
                "--tun",
                TUN_A,
                "--local",
                "10.200.0.1",
                "--peer",
                "10.200.0.2",
                "--stack",
                ",".join(case.kinds),
                "--aad",
                ",".join(f"{layer}.{name}" for layer, name in case.aad),
                "--datagrams",
                str(datagrams),
                "--result",
                str(src_result),
            ],
            "src_relay.log",
        )
        time.sleep(0.2)
        send = subprocess.run(
            [
                "ip",
                "netns",
                "exec",
                NS_A,
                sys.executable,
                str(APP),
                "send",
                "--count",
                str(datagrams),
                "--payload",
                case.payload,
                "--interval",
                "0.005",
            ],
            capture_output=True,
            text=True,
            env=self.environment,
            timeout=30,
        )
        for process in (src_relay, dst_relay):
            self._reap(process)
        dst_app.terminate()
        self._reap(dst_app, timeout=5.0)
        if not src_result.exists():
            log = (self.temporary / "src_relay.log").read_text(errors="replace")
            raise RuntimeError(f"Linux source relay failed: {send.stderr}\n{log}")
        source = json.loads(src_result.read_text())
        destination = (
            json.loads(dst_result.read_text()) if dst_result.exists() else {}
        )
        complete = int(destination.get("received_complete", 0))
        delivered = int(destination.get("delivered", 0))
        auth = int(destination.get("auth_ok", 0))
        return {
            "sent": int(source.get("sent", 0)),
            "wire_bytes": float(source.get("wire_bytes", 0.0)),
            "fragment_count": float(source.get("fragment_count", 0.0)),
            "delivery_percent": 100.0 * delivered / datagrams,
            "auth_accept_percent": 100.0 * auth / complete if complete else 0.0,
            "mutation_applied": bool(destination.get("mutation_applied", False)),
            "field_visible": bool(destination.get("field_visible", False)),
            "complete": complete,
        }


def _record(
    prediction: str,
    case: str,
    seed: int,
    metric: str,
    value: float,
) -> dict[str, object]:
    return {
        "source": "linux_netns",
        "scenario": prediction,
        "policy": case,
        "seed": seed,
        "metric": metric,
        "value": float(value),
        "unit": METRIC_UNITS[metric],
    }


def _aux_rows(prediction: str, case: Case, metrics: dict[str, object], seed: int):
    return [
        _record(prediction, case.name, seed, "wire_bytes", metrics["wire_bytes"]),
        _record(
            prediction,
            case.name,
            seed,
            "fragment_count",
            metrics["fragment_count"],
        ),
        _record(
            prediction,
            case.name,
            seed,
            "mutation_applied",
            1.0 if metrics["mutation_applied"] else 0.0,
        ),
        _record(
            prediction,
            case.name,
            seed,
            "field_visible",
            1.0 if metrics["field_visible"] else 0.0,
        ),
        _record(
            prediction,
            case.name,
            seed,
            "auth_accept_percent",
            metrics["auth_accept_percent"],
        ),
    ]


def _delivery_row(prediction: str, case: Case, metrics: dict[str, object], seed: int):
    return [
        _record(
            prediction, case.name, seed, "delivery_percent", metrics["delivery_percent"]
        ),
        _record(
            prediction,
            case.name,
            seed,
            "in_order_delivery_percent",
            metrics["delivery_percent"],
        ),
        _record(prediction, case.name, seed, "duplicate_percent", 0.0),
    ]


def run_linux(predictions: tuple[str, ...] | None = None) -> list[dict[str, object]]:
    if os.geteuid() != 0:
        raise PermissionError(
            "Linux layering emulation needs root for netns, veth, TUN and tc."
        )
    selected = predictions or ("P1", "P2", "P3", "P4", "P5", "P6", "P7")
    cases: list[Case] = []
    for prediction in selected:
        cases.extend(
            {
                "P1": p1_cases,
                "P2": p2_cases,
                "P3": p3_cases,
                "P4": p4_cases,
                "P5": p5_cases,
                "P6": p6_cases,
                "P7": p7_cases,
            }[prediction]()
        )
    harness = Harness()
    harness.setup()
    rows: list[dict[str, object]] = []
    try:
        for case in cases:
            if case.prediction in {"P2", "P5"}:
                first = True
                for run in range(1, LINUX_RUNS + 1):
                    metrics = harness.run_once(case, run, LINUX_DATAGRAMS)
                    if first:
                        rows.extend(_aux_rows(case.prediction, case, metrics, 0))
                        first = False
                    rows.extend(_delivery_row(case.prediction, case, metrics, run))
            else:
                datagrams = 100 if case.prediction in {"P1", "P4", "P7"} else 50
                metrics = harness.run_once(case, 1, datagrams)
                rows.extend(_aux_rows(case.prediction, case, metrics, 0))
                rows.extend(_delivery_row(case.prediction, case, metrics, 0))
            print(
                f"{case.prediction} {case.name}: "
                f"delivery={metrics['delivery_percent']:.0f}%",
                flush=True,
            )
    finally:
        harness.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    predictions = tuple(args.only.split(",")) if args.only else None
    count = write_observations(args.output, run_linux(predictions))
    print(f"Layering observations: {count}")
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
