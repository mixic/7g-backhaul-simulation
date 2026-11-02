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

"""Optional ONNX Runtime inference with strict execution-provider verification."""

from __future__ import annotations

import json
import math
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


class NPUInferenceError(RuntimeError):
    """Raised when a requested inference provider cannot be verified."""


class OnnxNPUInference:
    """Run a single-input ONNX model and reject CPU fallback in its profile.

    The model must accept one float32 input tensor with shape ``[1, feature_count]``.
    Feature order and meaning are defined by the particular model.
    """

    def __init__(
        self,
        model_path: str | Path,
        provider: str,
        provider_options: Mapping[str, str] | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.provider = provider
        self.provider_options = dict(provider_options or {})
        if not self.model_path.is_file():
            raise FileNotFoundError(f"ONNX model not found: {self.model_path}")
        if not provider or provider == "CPUExecutionProvider":
            raise ValueError("Select an explicit non-CPU ONNX execution provider.")

    @staticmethod
    def _profile_providers(profile_path: str | Path) -> set[str]:
        with Path(profile_path).open(encoding="utf-8") as profile_file:
            events = json.load(profile_file)
        providers = {
            event.get("args", {}).get("provider")
            for event in events
            if event.get("cat") == "Node" and event.get("args", {}).get("provider")
        }
        return providers

    @staticmethod
    def _verify_profile_providers(
        executed_providers: set[str],
        requested_provider: str,
    ) -> None:
        if not executed_providers:
            raise NPUInferenceError(
                "The ONNX Runtime profile contains no execution-provider node events; "
                "hardware execution could not be verified."
            )
        if executed_providers != {requested_provider}:
            raise NPUInferenceError(
                f"Expected all profiled nodes on {requested_provider!r}, but observed "
                f"{sorted(executed_providers)!r}; CPU or other-provider fallback "
                "cannot be ruled out."
            )

    def infer(self, features: Sequence[float]) -> list[np.ndarray]:
        if len(features) == 0 or not all(
            math.isfinite(float(value)) for value in features
        ):
            raise ValueError("Model features must be a non-empty sequence of finite numbers.")

        try:
            ort = import_module("onnxruntime")
        except ImportError as error:
            raise NPUInferenceError(
                "ONNX Runtime is not installed. Install a vendor-compatible "
                "ONNX Runtime build with the requested NPU execution provider."
            ) from error

        available = ort.get_available_providers()
        if self.provider not in available:
            raise NPUInferenceError(
                f"Requested provider {self.provider!r} is unavailable. "
                f"Available providers: {available}."
            )

        with tempfile.TemporaryDirectory(prefix="7g-npu-profile-") as directory:
            options = ort.SessionOptions()
            options.enable_profiling = True
            options.profile_file_prefix = str(Path(directory) / "inference")
            session = ort.InferenceSession(
                str(self.model_path),
                sess_options=options,
                providers=[self.provider],
                provider_options=[self.provider_options],
            )
            inputs = session.get_inputs()
            if len(inputs) != 1:
                raise NPUInferenceError(
                    f"Expected one ONNX input, found {len(inputs)}."
                )
            input_name = inputs[0].name
            outputs = session.run(
                None,
                {input_name: np.asarray([features], dtype=np.float32)},
            )
            profile_path = session.end_profiling()
            executed_providers = self._profile_providers(profile_path)

        self._verify_profile_providers(executed_providers, self.provider)
        return outputs
