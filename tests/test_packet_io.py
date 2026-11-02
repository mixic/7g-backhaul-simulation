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

import json
import importlib.util
import math
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from simulation.npu_inference import NPUInferenceError, OnnxNPUInference
from simulation.packet_io import transmit_udp_loopback
from simulation.pretraining import (
    export_onnx,
    save_weights,
    train_synthetic_congestion_model,
)


class PacketIoTests(unittest.TestCase):
    def test_udp_loopback_reconstructs_payload_across_multiple_datagrams(self):
        payload = bytes(index % 251 for index in range(10_000))

        result = transmit_udp_loopback(payload, max_datagram_bytes=512)

        self.assertEqual(result.payload, payload)
        self.assertEqual(result.packet_count, 23)
        self.assertEqual(result.datagram_bytes_sent, len(payload) + 23 * 60)
        self.assertGreater(result.elapsed_ms, 0)
        self.assertGreater(result.goodput_mbps, 0)

    def test_udp_loopback_supports_empty_payload(self):
        result = transmit_udp_loopback(b"", max_datagram_bytes=256)

        self.assertEqual(result.payload, b"")
        self.assertEqual(result.packet_count, 1)

    def test_udp_loopback_rejects_invalid_datagram_and_timeout_values(self):
        with self.assertRaises(ValueError):
            transmit_udp_loopback(b"payload", max_datagram_bytes=60)
        with self.assertRaises(ValueError):
            transmit_udp_loopback(b"payload", timeout_seconds=0)

    def test_npu_backend_requires_a_non_cpu_provider_and_existing_model(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "model.onnx"
            model_path.touch()

            with self.assertRaises(ValueError):
                OnnxNPUInference(model_path, "CPUExecutionProvider")
            with self.assertRaises(FileNotFoundError):
                OnnxNPUInference(Path(directory) / "missing.onnx", "NpuProvider")

    def test_npu_backend_rejects_profiles_with_cpu_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_path = Path(directory) / "profile.json"
            profile_path.write_text(
                json.dumps(
                    [
                        {"cat": "Node", "args": {"provider": "OpenVINOExecutionProvider"}},
                        {"cat": "Node", "args": {"provider": "CPUExecutionProvider"}},
                    ]
                ),
                encoding="utf-8",
            )

            providers = OnnxNPUInference._profile_providers(profile_path)

        self.assertEqual(
            providers,
            {"OpenVINOExecutionProvider", "CPUExecutionProvider"},
        )
        with self.assertRaises(NPUInferenceError):
            OnnxNPUInference._verify_profile_providers(
                providers,
                "OpenVINOExecutionProvider",
            )
        OnnxNPUInference._verify_profile_providers(
            {"OpenVINOExecutionProvider"},
            "OpenVINOExecutionProvider",
        )

    def test_npu_backend_runs_input_and_verifies_profiled_provider(self):
        observed = {}

        class FakeSessionOptions:
            enable_profiling = False
            profile_file_prefix = ""

        class FakeSession:
            def __init__(self, _model, sess_options, providers, provider_options):
                self.options = sess_options
                observed["model"] = str(_model)
                observed["providers"] = providers
                observed["provider_options"] = provider_options

            def get_inputs(self):
                return [SimpleNamespace(name="telemetry")]

            def run(self, _outputs, inputs):
                observed["requested_outputs"] = _outputs
                observed["inputs"] = inputs["telemetry"]
                return [np.asarray([[0.4]], dtype=np.float32)]

            def end_profiling(self):
                profile_path = Path(f"{self.options.profile_file_prefix}.json")
                profile_path.write_text(
                    json.dumps(
                        [{"cat": "Node", "args": {"provider": "NpuExecutionProvider"}}]
                    ),
                    encoding="utf-8",
                )
                return str(profile_path)

        runtime = SimpleNamespace(
            get_available_providers=lambda: ["NpuExecutionProvider"],
            SessionOptions=FakeSessionOptions,
            InferenceSession=FakeSession,
        )
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "model.onnx"
            model_path.touch()
            backend = OnnxNPUInference(model_path, "NpuExecutionProvider")
            with patch("simulation.npu_inference.import_module", return_value=runtime):
                outputs = backend.infer([0.7, 0.2, 0.1, 0.7, 0.7, 0.05])

        self.assertEqual(observed["providers"], ["NpuExecutionProvider"])
        self.assertEqual(observed["inputs"].shape, (1, 6))
        self.assertEqual(observed["requested_outputs"], None)
        np.testing.assert_allclose(outputs[0], [[0.4]], atol=1e-7)

    def test_npu_backend_reports_missing_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "model.onnx"
            model_path.touch()
            backend = OnnxNPUInference(model_path, "NpuExecutionProvider")
            with patch(
                "simulation.npu_inference.import_module",
                side_effect=ImportError("runtime not installed"),
            ):
                with self.assertRaisesRegex(NPUInferenceError, "not installed"):
                    backend.infer([0.7, 0.2, 0.1, 0.7, 0.7, 0.05])

    def test_synthetic_pretraining_is_reproducible_and_saves_provenance(self):
        first = train_synthetic_congestion_model(sample_count=100, seed=19, epochs=5)
        second = train_synthetic_congestion_model(sample_count=100, seed=19, epochs=5)

        self.assertEqual(first.model.horizon_seconds, 5.0)
        self.assertTrue(
            (first.model.predict([[0.5, 0.0, 0.0, 0.5, 0.5, 0.0]]) >= 0.0).all()
        )
        self.assertTrue(
            (first.model.predict([[0.5, 0.0, 0.0, 0.5, 0.5, 0.0]]) <= 1.0).all()
        )
        self.assertEqual(
            first.model.predict([[0.5, 0.0, 0.0, 0.5, 0.5, 0.0]]).tolist(),
            second.model.predict([[0.5, 0.0, 0.0, 0.5, 0.5, 0.0]]).tolist(),
        )
        self.assertTrue(math.isfinite(first.root_mean_squared_error))

        with tempfile.TemporaryDirectory() as directory:
            weights_path = Path(directory) / "model.npz"
            save_weights(first.model, weights_path)
            with np.load(weights_path) as weights:
                self.assertIn("synthetic", str(weights["training_data"]))
                self.assertEqual(
                    tuple(weights["feature_names"]),
                    (
                        "pressure",
                        "pressure_velocity_x10",
                        "pressure_acceleration_x50",
                        "utilization",
                        "normalized_queue_delay",
                        "loss_rate_x10",
                    ),
                )

    @unittest.skipUnless(importlib.util.find_spec("onnx"), "optional ONNX exporter not installed")
    def test_pretrained_model_exports_as_valid_onnx(self):
        onnx = import_module("onnx")
        reference = import_module("onnx.reference")

        result = train_synthetic_congestion_model(sample_count=100, seed=3, epochs=3)
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "congestion.onnx"
            export_onnx(result.model, model_path)
            model = onnx.load(model_path)
            onnx.checker.check_model(model)
            sample = np.asarray([[0.7, 0.2, 0.1, 0.7, 0.7, 0.05]], dtype=np.float32)
            onnx_prediction = reference.ReferenceEvaluator(model).run(
                None,
                {"telemetry": sample},
            )[0]

        self.assertEqual(model.graph.input[0].name, "telemetry")
        self.assertEqual(model.graph.output[0].name, "forecast_pressure")
        self.assertEqual(
            {item.key: item.value for item in model.metadata_props}["training_data"],
            "synthetic only; not calibrated on measured network telemetry",
        )
        np.testing.assert_allclose(
            onnx_prediction,
            result.model.predict(sample),
            rtol=1e-5,
            atol=1e-6,
        )


if __name__ == "__main__":
    unittest.main()
