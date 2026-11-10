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


"""Thin subprocess wrapper used by every module that touches the kernel.

``Shell(dry_run=True)`` records the exact command lines and executes nothing.
That makes the full configuration of every case reviewable before a run that
needs root.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]


class CommandError(RuntimeError):
    """A command exited non-zero while ``check=True``."""

    def __init__(self, argv: Sequence[str], returncode: int, stderr: str) -> None:
        super().__init__(f"{' '.join(argv)} -> exit {returncode}: {stderr.strip()}")
        self.argv = list(argv)
        self.returncode = returncode
        self.stderr = stderr


class Shell:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.history: list[list[str]] = []

    def run(
        self,
        argv: Sequence[object],
        *,
        check: bool = True,
        input_text: str | None = None,
        timeout: float = 60.0,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(part) for part in argv]
        self.history.append(command)
        if self.dry_run:
            return subprocess.CompletedProcess(command, 0, "", "")
        try:
            result = subprocess.run(
                command,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                cwd=str(REPO_ROOT),
            )
        except FileNotFoundError as error:
            raise CommandError(command, 127, str(error)) from error
        if check and result.returncode != 0:
            raise CommandError(command, result.returncode, result.stderr)
        return result

    def ns(self, namespace: str, argv: Sequence[object], **kwargs) -> subprocess.CompletedProcess[str]:
        return self.run(["ip", "netns", "exec", namespace, *argv], **kwargs)

    def popen(self, namespace: str, argv: Sequence[object]) -> subprocess.Popen[str] | None:
        command = ["ip", "netns", "exec", namespace, *[str(part) for part in argv]]
        self.history.append(command)
        if self.dry_run:
            return None
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(REPO_ROOT),
        )

    def script(self) -> str:
        return "\n".join(" ".join(_quote(part) for part in command) for command in self.history)


def _quote(part: str) -> str:
    if part and all(ch.isalnum() or ch in "-_./:=,@%+" for ch in part):
        return part
    return "'" + part.replace("'", "'\"'\"'") + "'"
