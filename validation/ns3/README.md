# ns-3 reference implementation of cross-validation scenario S1

This directory contains the independent packet-level reference used in
[docs/external-validation.md](../../docs/external-validation.md). It models the
same scenario as [`../scenario_s1.py`](../scenario_s1.py):

- two point-to-point paths from a client to a server (20 Mbit/s / 5 ms one-way
  delay / 0.1 % loss, and 8 Mbit/s / 25 ms / 0.5 % loss),
- a 12 Mbit/s constant-bit-rate UDP stream of 1200-byte payloads every 0.8 ms
  for 20 s,
- one 100-packet FIFO drop-tail buffer per path,
- smooth weighted round-robin path selection with weight
  `capacity / (delay + 1 ms)`, and
- optional handover: the primary path is unavailable on `[8 s, 12 s)`.

The scenario constants are duplicated from `../scenario_s1.py` on purpose. If
you change one file without the other, the comparison is invalid; the shared
values are marked with comments in both files.

## Requirements

- ns-3.49 (`git clone --depth 1 --branch ns-3.49 https://gitlab.com/nsnam/ns-3-dev.git`)
- a C++17 compiler, cmake, and a POSIX shell (Linux or WSL)
- Python 3.10+ for the comparison half (repository root)

## Installing ns-3.49 in WSL (Windows)

This is the shortened version of the official
[quick start](https://www.nsnam.org/docs/release/3.49/installation/html/quick-start.html)
that the reference below was built with. Open a WSL shell (`wsl` from
PowerShell) on an Ubuntu distribution and run:

```bash
# 1. Dependencies (a compiler, cmake, make, and basic tooling)
sudo apt update
sudo apt install -y build-essential cmake git

# 2. Download the tagged release, not the development branch
git clone --depth 1 --branch ns-3.49 https://gitlab.com/nsnam/ns-3-dev.git ~/ns-3-dev
cd ~/ns-3-dev

# 3. Configure and build (all buildable modules, examples and tests)
./ns3 configure --enable-examples --enable-tests
./ns3 build -j "$(nproc)"

# 4. Verify the installation
./ns3 run hello-simulator
```

A full build on a 24-core machine takes roughly 15-25 minutes and needs about
4 GB of disk. If you only need the modules used by this comparison, the
minimal configuration below builds in about 10 minutes and is what the
published numbers used:

```bash
cd ~/ns-3-dev
./ns3 configure \
  --enable-modules=core,network,internet,point-to-point,csma,applications,traffic-control \
  --disable-examples --disable-tests --disable-python \
  -- -DNS3_WARNINGS_AS_ERRORS=OFF
./ns3 build -j "$(nproc)"
```

Either configuration runs the S1 program; the module subset simply compiles
less. Switching between the two only requires re-running `./ns3 configure` and
`./ns3 build` in the same tree.

WSL notes:

- The tree lives in the Linux filesystem (`~/ns-3-dev`), not on `/mnt/c`, which
  keeps builds fast.
- WSL prints a warning about Windows path injection into `$PATH`; appending
  `[interop]` / `appendWindowsPath = false` to `/etc/wsl.conf` and restarting
  WSL (`wsl --shutdown`) removes it. It is cosmetic and not required.
- `ns3` output binaries land in `~/ns-3-dev/build/scratch/` for programs placed
  in `~/ns-3-dev/scratch/`; `run-s1.sh` copies the program there and finds it
  automatically.

## Building and running this comparison

The published build used this module subset:

```bash
cd ~/ns-3-dev
./ns3 configure \
  --enable-modules=core,network,internet,point-to-point,csma,applications,traffic-control \
  --disable-examples --disable-tests --disable-python \
  -- -DNS3_WARNINGS_AS_ERRORS=OFF
./ns3 build -j "$(nproc)"
```

## Run

```bash
NS3_DIR=~/ns-3-dev SEEDS=8 ./run-s1.sh
```

The script copies `s1-multipath-handover.cc` into `$NS3_DIR/scratch/`, builds
it with `./ns3 build`, and runs both scenarios for seeds `1..SEEDS`, appending
rows to `output/validation/ns3_s1.csv` in the repository.

Then, from the repository root:

```bash
py -3 -m validation.run_s1_experiment \
    --ns3-csv output/validation/ns3_s1.csv \
    --seeds 1 2 3 4 5 6 7 8 \
    --output-dir output/validation
```

`s1_mapping.json` maps the ns-3 CSV columns onto the canonical metric names used
by `tools/validation_io.py`.

## Buffer configuration (important)

ns-3.49 installs a default `FqCoDel` queue disc with a `10240p` limit on every
device, and the point-to-point device keeps its own `100p` `TxQueue`. The
program deletes the default disc, installs a `100p` `FifoQueueDisc`, and sets
the device queue to `1p` so that exactly one 100-packet FIFO buffer per path is
modelled. Leaving ns-3's defaults in place instead models a much deeper buffer
and produces a p95 delay about 7.5× larger for the same workload (see §6 of the
validation report). Report the buffer configuration in any comparison.

## Metrics

Per run, the program writes one CSV row:

| Column | Meaning |
| --- | --- |
| `scenario` | `s0_nominal` or `s1_handover` |
| `policy` | `capacity_weighted_swrr` |
| `seed` | `RngSeedManager` seed/run |
| `packet_delivery_percent` | received / sent packets × 100 |
| `one_way_delay_p95_ms` | 95th percentile of receive time minus send time |
| `goodput_mbps` | received payload bits / 20 s |
| `active_paths_mean` | mean available paths over the run |
| `primary_share_percent` | share of packets assigned to the primary path |

## Manual invocation

```bash
$NS3_DIR/build/scratch/ns3.49-s1-multipath-handover-default \
    --scenario=s1_handover --seed=3 --out=/tmp/s1.csv --append=0
```
