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

"""Round-3 cases: rate-limited depth and captured/reinjected ESP boundaries."""

from __future__ import annotations

import json
import signal
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from validation.real_stack.shell import Shell
from validation.round2.capture import Sniffer
from validation.round2.cases import _collect, _receiver, _send, _warm_up
from validation.round2.counters import install_netem, read_xfrm_stat
from validation.round2.net import NS_A, NS_B, NS_N, Topology
from validation.round2.replay import delivered_percent, reference_accepted, reordering_depth
from validation.round2.stacks import setup_esp_tunnel

from .predictions import CASES, Round3Case

SOURCE = "linux_real_stack_round3"
PAYLOAD_INNER_LENGTH = 228
RAW_TOOL = ["python3", "-m", "validation.round3.raw"]


@dataclass
class RawCapture:
    shell: Shell
    namespace: str
    interface: str
    output: Path
    _process: object | None = None

    def start(self, timeout: float = 5.0) -> None:
        self._process = self.shell.popen(
            self.namespace,
            [*RAW_TOOL, "capture", "--iface", self.interface, "--out", str(self.output)],
        )
        if self._process is None:  # dry run
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process.stdout.readline().strip() == "READY":
                return
            if self._process.poll() is not None:
                break
        error = self._process.stderr.read() if self._process.poll() is not None else ""
        self.stop()
        raise RuntimeError(f"raw capture did not become ready: {error.strip()}")

    def stop(self) -> list[dict[str, object]]:
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except Exception:  # noqa: BLE001
                process.kill()
            self._process = None
        if not self.output.exists() or self.output.stat().st_size == 0:
            return []
        return [
            json.loads(line)
            for line in self.output.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def _row(case: Round3Case, run: int, metric: str, value: object, unit: str) -> dict[str, object]:
    return {
        "source": SOURCE,
        "scenario": case.id,
        "policy": case.id,
        "seed": run,
        "metric": metric,
        "value": value,
        "unit": unit,
    }


def _sa_mode(shell: Shell) -> str:
    output = shell.ns(NS_B, ["ip", "xfrm", "state"]).stdout or ""
    return "esn" if "anti-replay esn context" in output else "legacy"


def _install_drop(shell: Shell) -> None:
    shell.ns(NS_B, ["tc", "qdisc", "add", "dev", "vB2", "ingress"])
    shell.ns(
        NS_B,
        [
            "tc",
            "filter",
            "add",
            "dev",
            "vB2",
            "parent",
            "ffff:",
            "protocol",
            "ip",
            "u32",
            "match",
            "ip",
            "protocol",
            "50",
            "0xff",
            "action",
            "drop",
        ],
    )


def _remove_drop(shell: Shell) -> None:
    shell.ns(NS_B, ["tc", "filter", "del", "dev", "vB2", "parent", "ffff:"], check=False)
    shell.ns(NS_B, ["tc", "qdisc", "del", "dev", "vB2", "ingress"], check=False)


def _select(
    frames: list[dict[str, object]], offset: int
) -> tuple[dict[str, object], dict[str, object]] | None:
    if not frames:
        return None
    ordered = sorted(frames, key=lambda item: int(item["seq"]))
    maximum = ordered[-1]
    target_seq = int(maximum["seq"]) - offset
    target = next((frame for frame in ordered if int(frame["seq"]) == target_seq), None)
    if target is None:
        return None
    return maximum, target


def run_rate(case: Round3Case, run: int, shell: Shell) -> list[dict[str, object]]:
    topology = Topology(shell, nat=False)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="round3_rate_") as tmp:
        tmp_path = Path(tmp)
        try:
            topology.build()
            flow = setup_esp_tunnel(shell, replay_window=case.window)
            warmed = _warm_up(shell, flow, 10.0)
            install_netem(shell, delay_ms=100.0, reorder_percent=25.0)
            sniffer = Sniffer(shell, NS_N, "vN2", tmp_path / "n.jsonl")
            sniffer.start()
            xfrm_before = read_xfrm_stat(shell, NS_B)
            receiver = _receiver(
                shell,
                NS_B,
                flow.dst,
                flow.port,
                seconds=case.datagrams * case.interval + 8.0,
                idle=2.0,
            )
            sent_summary = _send(
                shell,
                NS_A,
                flow,
                count=case.datagrams,
                inner_length=PAYLOAD_INNER_LENGTH,
                interval=case.interval,
            )
            time.sleep(0.1 + 2.5)
            summary = _collect(receiver)
            records = sniffer.stop()
            xfrm_after = read_xfrm_stat(shell, NS_B)
            if shell.dry_run:
                return []
            sent = int(sent_summary.get("sent", case.datagrams))
            seqs = [
                int(record["esp_seq"])
                for record in records
                if isinstance(record.get("esp_seq"), int)
            ]
            delivered = int(summary.get("received", 0))
            depth = reordering_depth(seqs)
            accepted = reference_accepted(seqs, case.window or 0)
            depth_ok = int(case.min_depth is not None and case.min_depth <= depth <= (case.max_depth or depth))
            seq_errors = int(xfrm_after.get("XfrmInStateSeqError", 0)) - int(
                xfrm_before.get("XfrmInStateSeqError", 0)
            )
            rows += [
                _row(case, run, "warmup_ok", int(warmed), "boolean"),
                _row(case, run, "offload_disabled", int(topology.offload_disabled), "boolean"),
                _row(case, run, "sent_datagrams", sent, "count"),
                _row(case, run, "captured_packets", len(seqs), "count"),
                _row(case, run, "reorder_depth", depth, "count"),
                _row(case, run, "depth_gate", depth_ok, "boolean"),
                _row(case, run, "delivered_datagrams", delivered, "count"),
                _row(case, run, "reference_accepted", accepted, "count"),
                _row(case, run, "delivery_percent", delivered_percent(delivered, sent), "percent"),
                _row(case, run, "delivery_matches_reference", int(delivered == accepted), "boolean"),
                _row(case, run, "seq_error_delta", seq_errors, "count"),
                _row(case, run, "anti_replay_esn", int(_sa_mode(shell) == "esn"), "boolean"),
                _row(case, run, "replay_window", case.window or 0, "count"),
            ]
            return rows
        finally:
            topology.teardown()


def run_reinject(case: Round3Case, run: int, shell: Shell) -> list[dict[str, object]]:
    topology = Topology(shell, nat=False)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="round3_reinject_") as tmp:
        tmp_path = Path(tmp)
        try:
            topology.build()
            flow = setup_esp_tunnel(shell, replay_window=case.window)
            warmed = _warm_up(shell, flow, 10.0)
            mode = _sa_mode(shell)
            _install_drop(shell)
            original_receiver = _receiver(shell, NS_B, flow.dst, flow.port, seconds=2.0, idle=0.5)
            capture = RawCapture(shell, NS_N, "vN2", tmp_path / "frames.jsonl")
            capture.start()
            sent_summary = _send(
                shell,
                NS_A,
                flow,
                count=case.datagrams,
                inner_length=PAYLOAD_INNER_LENGTH,
                interval=case.interval,
            )
            time.sleep(0.5)
            frames = capture.stop()
            original_summary = _collect(original_receiver)
            _remove_drop(shell)
            if shell.dry_run:
                return []
            selected = _select(frames, case.offset or 0)
            sent = int(sent_summary.get("sent", case.datagrams))
            original_delivered = int(original_summary.get("received", 0))
            if selected is None:
                rows += [
                    _row(case, run, "warmup_ok", int(warmed), "boolean"),
                    _row(case, run, "offload_disabled", int(topology.offload_disabled), "boolean"),
                    _row(case, run, "sent_datagrams", sent, "count"),
                    _row(case, run, "captured_packets", len(frames), "count"),
                    _row(case, run, "capture_gate", 0, "boolean"),
                    _row(case, run, "original_drop_gate", int(original_delivered == 0), "boolean"),
                    _row(case, run, "anti_replay_esn", int(mode == "esn"), "boolean"),
                    _row(case, run, "replay_window", case.window or 0, "count"),
                ]
                return rows
            maximum, target = selected
            selected_path = tmp_path / "selected.jsonl"
            selected_path.write_text(
                "\n".join(
                    json.dumps({"frame": item["frame"], "seq": int(item["seq"])})
                    for item in (maximum, target)
                )
                + "\n",
                encoding="utf-8",
            )
            inject_receiver = _receiver(shell, NS_B, flow.dst, flow.port, seconds=3.0, idle=1.0)
            shell.ns(NS_N, [*RAW_TOOL, "inject", "--iface", "vN2", "--input", str(selected_path)])
            summary = _collect(inject_receiver)
            delivered = int(summary.get("received", 0))
            seqs = [int(maximum["seq"]), int(target["seq"])]
            accepted = reference_accepted(seqs, case.window or 0)
            rows += [
                _row(case, run, "warmup_ok", int(warmed), "boolean"),
                _row(case, run, "offload_disabled", int(topology.offload_disabled), "boolean"),
                _row(case, run, "sent_datagrams", sent, "count"),
                _row(case, run, "captured_packets", len(frames), "count"),
                _row(case, run, "capture_gate", int(len(frames) >= 2), "boolean"),
                _row(case, run, "original_drop_gate", int(original_delivered == 0), "boolean"),
                _row(case, run, "max_seq", int(maximum["seq"]), "count"),
                _row(case, run, "target_seq", int(target["seq"]), "count"),
                _row(case, run, "target_offset", int(maximum["seq"]) - int(target["seq"]), "count"),
                _row(case, run, "injected_datagrams", 2, "count"),
                _row(case, run, "delivered_datagrams", delivered, "count"),
                _row(case, run, "reference_accepted", accepted, "count"),
                _row(case, run, "delivery_matches_reference", int(delivered == accepted), "boolean"),
                _row(case, run, "anti_replay_esn", int(mode == "esn"), "boolean"),
                _row(case, run, "replay_window", case.window or 0, "count"),
            ]
            return rows
        finally:
            _remove_drop(shell)
            topology.teardown()


def run_case(case: Round3Case, run: int, shell: Shell) -> list[dict[str, object]]:
    if shell.dry_run:
        print(
            f"# {case.id}: {case.kind}, window={case.window}, offset={case.offset}, "
            f"datagrams={case.datagrams}, interval={case.interval}"
        )
        return []
    if case.kind == "rate":
        return run_rate(case, run, shell)
    if case.kind == "reinject":
        return run_reinject(case, run, shell)
    raise ValueError(f"unknown case kind: {case.kind}")


def select_cases(only: str) -> list[Round3Case]:
    if not only:
        return list(CASES.values())
    wanted = {token.strip() for token in only.split(",") if token.strip()}
    chosen = [case for case in CASES.values() if case.id in wanted]
    unknown = wanted - set(CASES)
    if unknown:
        raise SystemExit(f"unknown case: {', '.join(sorted(unknown))}")
    return chosen


__all__ = ["RawCapture", "run_case", "select_cases"]
