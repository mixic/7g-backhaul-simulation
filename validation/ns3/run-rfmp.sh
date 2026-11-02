#!/usr/bin/env bash
# Build and run the ns-3 half of the RFMP v0.1 role-transition cross-validation.
#
# Requirements: an ns-3.49 source tree with the module subset used by the
# program (core, network, internet, point-to-point, applications,
# traffic-control), Linux/WSL and a C++17 toolchain. See validation/ns3/README.md.
#
#   NS3_DIR=~/ns-3-dev SEEDS=5 ./validation/ns3/run-rfmp.sh
#
# Environment:
#   NS3_DIR  ns-3 source tree        (default: $HOME/ns-3-dev)
#   SEEDS    number of seeds to run  (default: 5)
#   OUT      CSV output path         (default: <repo>/output/validation/rfmp_ns3.csv)
set -euo pipefail

NS3_DIR="${NS3_DIR:-$HOME/ns-3-dev}"
SEEDS="${SEEDS:-5}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$REPO/output/validation/rfmp_ns3.csv}"

if [ ! -d "$NS3_DIR" ]; then
  echo "ns-3 tree not found at $NS3_DIR; set NS3_DIR to an ns-3.49 checkout." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
cp "$HERE/rfmp-role-transition.cc" "$NS3_DIR/scratch/"

cd "$NS3_DIR"
./ns3 build >/dev/null
BIN="$(find build/scratch -maxdepth 1 -type f -name 'ns3.*rfmp-role-transition*' | head -1)"
if [ -z "$BIN" ]; then
  echo "ns-3 build did not produce the rfmp-role-transition binary." >&2
  exit 1
fi

rm -f "$OUT"
first=1
for mode in rt1 rt2; do
  for seed in $(seq 1 "$SEEDS"); do
    "$BIN" --seed="$seed" --mode="$mode" --out="$OUT" --append=$((1 - first))
    first=0
  done
done
echo "ns-3 replicates: $(($(wc -l < "$OUT") - 1))"
echo "CSV: $OUT"
