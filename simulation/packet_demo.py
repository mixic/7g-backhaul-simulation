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

"""Command-line real UDP packet and optional ONNX inference demonstration."""

from __future__ import annotations

import argparse

from .packet_io import transmit_udp_loopback


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-size", type=int, default=64_000)
    parser.add_argument("--max-datagram-bytes", type=int, default=1200)
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    parser.add_argument("--model", help="Optional compatible ONNX model path.")
    parser.add_argument(
        "--provider",
        help="Required with --model; explicit non-CPU ONNX Runtime provider name.",
    )
    parser.add_argument(
        "--features",
        help="Comma-separated model input values; required with --model.",
    )
    args = parser.parse_args()
    if args.payload_size < 0:
        parser.error("--payload-size must be non-negative.")
    if args.model and (not args.provider or not args.features):
        parser.error("--model requires both --provider and --features.")
    if not args.model and (args.provider or args.features):
        parser.error("--provider and --features require --model.")

    payload = bytes(index % 251 for index in range(args.payload_size))
    result = transmit_udp_loopback(
        payload,
        max_datagram_bytes=args.max_datagram_bytes,
        timeout_seconds=args.timeout_seconds,
    )
    print("Transport: UDP over IPv4 loopback (real local socket datagrams)")
    print(f"Payload bytes: {len(result.payload)}")
    print(f"Datagrams sent and received: {result.packet_count}")
    print(f"Framed datagram bytes sent: {result.datagram_bytes_sent}")
    print(f"Elapsed: {result.elapsed_ms:.3f} ms")
    print(f"Measured loopback goodput: {result.goodput_mbps:.3f} Mbps")
    print(f"Payload SHA-256: {result.sha256}")

    if args.model:
        from .npu_inference import OnnxNPUInference

        try:
            features = tuple(float(value) for value in args.features.split(","))
        except ValueError:
            parser.error("--features must be comma-separated numbers.")
        outputs = OnnxNPUInference(args.model, args.provider).infer(features)
        print(f"Verified ONNX execution provider: {args.provider}")
        print(f"Model outputs: {outputs}")


if __name__ == "__main__":
    main()
