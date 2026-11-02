#!/usr/bin/env bash
# Build and run the role-fluid kinematic fabric scenarios in ns-3.
#
#   NS3_DIR=~/ns-3-dev ./validation/ns3/run-fabric.sh
#
# Runs A_static/A_turbo/B_dns/B_name/C_single/C_fabric (3 seeds each) and the
# 10 000 s stability run, appending one CSV row per run.
set -euo pipefail

NS3_DIR="${NS3_DIR:-$HOME/ns-3-dev}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$REPO/output/validation/fabric.csv}"

if [ ! -d "$NS3_DIR" ]; then
  echo "ns-3 tree not found at $NS3_DIR" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
cp "$HERE/role-fluid-fabric.cc" "$NS3_DIR/scratch/"
sed -i "s/\r$//" "$NS3_DIR/scratch/role-fluid-fabric.cc"
cd "$NS3_DIR"
./ns3 build >/dev/null
BIN="$(find build/scratch -maxdepth 1 -type f -name 'ns3.*role-fluid-fabric*' | head -1)"
[ -n "$BIN" ] || { echo "build failed" >&2; exit 1; }

rm -f "$OUT"
for scenario in A_static A_turbo B_dns B_name C_single C_fabric; do
  for seed in 1 2 3; do
    "$BIN" --scenario="$scenario" --seed="$seed" --out="$OUT"
  done
done
"$BIN" --scenario=stability --seed=1 --out="$OUT"
echo "CSV: $OUT"
