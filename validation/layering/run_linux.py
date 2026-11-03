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

"""Write the Linux namespace observations for the frozen predictions.

On Windows the command delegates to WSL2 (distro ``Ubuntu``) as root.  On
Linux it must already be running as root.  See
``validation/linux_layering/README.md`` for the privilege list.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive
    if not drive:
        return str(resolved).replace("\\", "/")
    return f"/mnt/{drive[0].lower()}{str(resolved)[2:].replace(chr(92), '/')}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    arguments = [
        "--output",
        _wsl_path(args.output) if os.name == "nt" else str(args.output),
    ]
    if args.only:
        arguments.extend(["--only", args.only])

    if os.name == "nt":
        command = [
            "wsl.exe",
            "-d",
            "Ubuntu",
            "-u",
            "root",
            "--cd",
            _wsl_path(repo),
            "--",
            "python3",
            "-m",
            "validation.linux_layering.worker",
            *arguments,
        ]
    else:
        command = [
            sys.executable,
            "-m",
            "validation.linux_layering.worker",
            *arguments,
        ]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
