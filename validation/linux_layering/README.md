# Linux namespace data plane

This directory contains the third fidelity level of the layering testbed: a
user-space TUN data plane running inside Linux network namespaces, with
`tc netem` supplying the stipulated i.i.d. loss.

The codec is shared with the executable model and SimPy. What differs here is
the execution path: applications run over TUN devices, wire parts cross a veth
pair, the kernel applies seeded netem loss, and a separate relay process on the
receiver reconstructs, rewrites and decodes the datagrams. Agreement therefore
checks the codec and the rewrite logic under kernel loss and real socket I/O,
not an independent protocol implementation.

## Privileges

The harness needs **root** (or a container user with the same capabilities) for:

- creating and deleting network namespaces (`ip netns add/delete`);
- creating a veth pair and moving one end into each namespace;
- creating TUN devices (`/dev/net/tun`, `ip tuntap add`);
- adding addresses, peer routes and MTUs;
- installing a `tc netem` qdisc.

Privileges are confined to the new namespaces; the host network configuration
is not modified. If a run is interrupted, remove leftovers with:

```bash
ip netns del layA 2>/dev/null
ip netns del layB 2>/dev/null
```

The Linux interpreter also needs the repository's Python dependencies (at
minimum `numpy`; install `requirements.txt` in that interpreter, for example
`python3 -m pip install --break-system-packages -r requirements.txt`). The
committed Linux results used stock zlib 1.3.1; the Windows model uses
zlib-ng, which compresses the synthetic corpus slightly differently. This is
recorded in the results and in the predictions addendum.

An unprivileged-in-a-container run is possible only if the container grants
`CAP_NET_ADMIN` and `/dev/net/tun`; user-namespace-only (`unshare -Urn`) setups
are kernel-dependent and are not supported by the harness. WSL2 Ubuntu works as
root and is the environment used for the committed results.

## Topology

```text
 layA                                   layB
 app 10.201.0.1                         app 10.201.0.2
   |  tunA (mtu 40000)                    |  tunB (mtu 40000)
 relay --encode--> UDP 10.200.0.1:9000    relay <--udp-- 10.200.0.2:9000
                    |  vA ==== veth ==== vB  |  netem loss p%, seed r
```

- The sender app emits IPv4/UDP datagrams to `10.201.0.2:9999`; the kernel
  routes them to `tunA`, where the source relay reads them.
- The relay encodes each datagram with the shared layer codec and sends every
  wire part as one UDP datagram with an 8-byte testbed header
  `(datagram_id, part_index, part_count)`. The header is transport plumbing and
  is not counted in the modelled wire size.
- `tc netem` on `vA` drops whole wire parts. This is the stipulated i.i.d.
  per-fragment loss.
- The destination relay buffers parts by datagram id, applies the middlebox
  rewrite to the received bytes, decodes, and writes accepted datagrams back to
  `tunB`, where the destination app receives them.

TUN and veth MTUs are 40000 B so that only the modelled `F` layer fragments.
The modelled path MTU stays 1500 B.

## Cases and seeds

The worker uses the same frozen cases as the Python runners
(`simulation/layering/scenarios.py`):

- P1 and P4: one replicate, 100 datagrams.
- P2 and P5: 40 replicates (netem seeds 1-40), 100 datagrams each.
- P3, P6 and P7: one replicate per case, 50-100 datagrams.
- P6 selects parser depth 1, 2 or 3 through `max_depth`.

Payload normalisation: the app sends `corpus(model_payload)[28:]` bytes, so the
IPv4/UDP datagram read from TUN is exactly `model_payload` bytes. Its first 28
bytes are real IP/UDP headers rather than corpus bytes; the predictions file
relaxes P1's text-ratio threshold for Linux for this reason.

## Run

From the repository root, as root on Linux:

```bash
python3 -m validation.layering.run_linux \
  --output validation/layering/results/linux_observations.csv
```

On Windows with WSL2:

```powershell
py -3 -m validation.layering.run_linux --output validation\layering\results\linux_observations.csv
```

The Windows wrapper maps the output path to `/mnt/c/...` and runs the worker as
root in the `Ubuntu` distro. Use `--only P3` (or another prediction id) for a
quick check.

## Outputs

The worker writes long-form observations with `source = linux_netns`:

```text
source, scenario, policy, seed, metric, value, unit
```

The metrics and units are the ones registered in `tools/validation_io.py`.
`delivery_percent` is over the datagrams the sender emitted; authentication
acceptance is over datagrams whose fragments all arrived. Datagrams that lose a
fragment are counted as not delivered and are excluded from the acceptance
denominator. P3, P6 and P7 use no loss, so the two denominators coincide.

## Limitations

- The middlebox is a stipulated user-space rewriter, not a measured middlebox.
- The AEAD is a toy; this directory makes no cryptographic security claim.
- All fidelities share the codec; the Linux run does not independently validate
  protocol semantics.
- netem loss is per wire part (per fragment), seeded per run; it is not a
  wireless channel model.
