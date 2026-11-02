#!/usr/bin/env bash
# Build and run the IPv4/IPv6 comparison + IPv6-agnostic-service experiment.
#
#   NS3_DIR=~/ns-3-dev ./validation/ns3/run-ip46.sh
#
# Runs the experiment matrix and appends one CSV row per run:
#   overhead/ipv4  (MTU 1500, 128 B payload)
#   overhead/ipv6  (MTU 1500, 128 B payload)
#   fragment/ipv4  (MTU 1280, 1400 B payload -> source fragmentation)
#   fragment/ipv6  (MTU 1280, 1400 B payload -> source fragmentation)
#   agnostic       (MTU 1500, 128 B payload, family switch at t=5 s)
set -euo pipefail

NS3_DIR="${NS3_DIR:-$HOME/ns-3-dev}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$REPO/output/validation/ip46.csv}"

if [ ! -d "$NS3_DIR" ]; then
  echo "ns-3 tree not found at $NS3_DIR" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
cp "$HERE/ip46-fabric.cc" "$NS3_DIR/scratch/"
sed -i "s/\r$//" "$NS3_DIR/scratch/ip46-fabric.cc"
cd "$NS3_DIR"
./ns3 build >/dev/null
BIN="$(find build/scratch -maxdepth 1 -type f -name 'ns3.*ip46-fabric*' | head -1)"
[ -n "$BIN" ] || { echo "build failed" >&2; exit 1; }

rm -f "$OUT"
"$BIN" --experiment=overhead  --family=ipv4 --mtu=1500 --payload=128  --out="$OUT"
"$BIN" --experiment=overhead  --family=ipv6 --mtu=1500 --payload=128  --out="$OUT"
"$BIN" --experiment=fragment  --family=ipv4 --mtu=1280 --payload=1400 --out="$OUT"
"$BIN" --experiment=fragment  --family=ipv6 --mtu=1280 --payload=1400 --out="$OUT"
"$BIN" --experiment=agnostic  --family=ipv4 --mtu=1500 --payload=128  --out="$OUT"
echo "CSV: $OUT"
