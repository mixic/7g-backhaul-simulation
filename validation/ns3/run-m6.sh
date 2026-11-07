#!/usr/bin/env bash
# Build and run the ns-3 half of M6 (H10) transmission-energy cross-validation.
#
# Requirements: an ns-3.49 source tree with the module subset used by this
# program (core is enough; the scratch links zlib), Linux/WSL, a C++17
# toolchain and zlib headers. See validation/ns3/README.md.
#
#   NS3_DIR=~/ns-3-dev SEEDS=30 ./validation/ns3/run-m6.sh
#
# Environment:
#   NS3_DIR  ns-3 source tree            (default: $HOME/ns-3-dev)
#   SEEDS    number of seeds to run      (default: 30)
#   OUT      CSV output path             (default: <repo>/output/validation/ns3_m6.csv)
set -euo pipefail

NS3_DIR="${NS3_DIR:-$HOME/ns-3-dev}"
SEEDS="${SEEDS:-30}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$REPO/output/validation/ns3_m6.csv}"

if [ ! -d "$NS3_DIR" ]; then
  echo "ns-3 tree not found at $NS3_DIR; set NS3_DIR to an ns-3.49 checkout." >&2
  exit 1
fi

# The program needs zlib, so it lives in a scratch subdirectory with its own
# CMakeLists.txt (the top-level create_scratch does not link external libs).
mkdir -p "$NS3_DIR/scratch/m6-energy"
cp "$HERE/m6-energy-transition.cc" "$NS3_DIR/scratch/m6-energy/"
cp "$HERE/m6-energy/CMakeLists.txt" "$NS3_DIR/scratch/m6-energy/"

cd "$NS3_DIR"
./ns3 build m6-energy-transition >/dev/null
BIN="$(find build/scratch/m6-energy -maxdepth 1 -type f -name 'ns3.*m6-energy-transition*' | head -1)"
if [ -z "$BIN" ]; then
  echo "ns-3 build did not produce the m6-energy-transition binary." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
"$BIN" --seeds="$SEEDS" --out="$OUT"
echo "ns-3 rows: $(($(wc -l < "$OUT") - 1))"
echo "CSV: $OUT"
