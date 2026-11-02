#!/usr/bin/env bash
# Build and run the ns-3 half of cross-validation scenario S1.
#
# Requirements: an ns-3.49 source tree with the module subset used by this
# program (core, network, internet, point-to-point, applications), Linux/WSL,
# and a C++17 toolchain. See validation/ns3/README.md.
#
#   NS3_DIR=~/ns-3-dev SEEDS=8 ./validation/ns3/run-s1.sh
#
# Environment:
#   NS3_DIR  ns-3 source tree            (default: $HOME/ns-3-dev)
#   SEEDS    number of seeds to run      (default: 8)
#   OUT      CSV output path             (default: <repo>/output/validation/ns3_s1.csv)
set -euo pipefail

NS3_DIR="${NS3_DIR:-$HOME/ns-3-dev}"
SEEDS="${SEEDS:-8}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$REPO/output/validation/ns3_s1.csv}"

if [ ! -d "$NS3_DIR" ]; then
  echo "ns-3 tree not found at $NS3_DIR; set NS3_DIR to an ns-3.49 checkout." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
cp "$HERE/s1-multipath-handover.cc" "$NS3_DIR/scratch/"

cd "$NS3_DIR"
./ns3 build >/dev/null
BIN="$(find build/scratch -maxdepth 1 -type f -name 'ns3.*s1-multipath-handover*' | head -1)"
if [ -z "$BIN" ]; then
  echo "ns-3 build did not produce the s1-multipath-handover binary." >&2
  exit 1
fi

rm -f "$OUT"
first=1
for scenario in s0_nominal s1_handover; do
  for seed in $(seq 1 "$SEEDS"); do
    "$BIN" --scenario="$scenario" --seed="$seed" --out="$OUT" --append=$((1 - first))
    first=0
  done
done
echo "ns-3 replicates: $(($(wc -l < "$OUT") - 1))"
echo "CSV: $OUT"
