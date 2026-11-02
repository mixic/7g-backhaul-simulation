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

"""Train a small reproducible synthetic congestion-forecast model and export ONNX."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

import numpy as np

FEATURE_NAMES = (
    "pressure",
    "pressure_velocity_x10",
    "pressure_acceleration_x50",
    "utilization",
    "normalized_queue_delay",
    "loss_rate_x10",
)


@dataclass(frozen=True)
class CongestionForecastModel:
    """Single-hidden-layer MLP forecasting congestion pressure in [0, 1]."""

    weight_1: np.ndarray
    bias_1: np.ndarray
    weight_2: np.ndarray
    bias_2: np.ndarray
    horizon_seconds: float

    def predict(self, features: np.ndarray) -> np.ndarray:
        values = np.asarray(features, dtype=np.float32)
        if values.ndim != 2 or values.shape[1] != len(FEATURE_NAMES):
            raise ValueError(f"Expected a 2D array with {len(FEATURE_NAMES)} features.")
        hidden = np.tanh(values @ self.weight_1 + self.bias_1)
        logits = hidden @ self.weight_2 + self.bias_2
        return 1.0 / (1.0 + np.exp(-np.clip(logits, -30.0, 30.0)))


@dataclass(frozen=True)
class PretrainingResult:
    model: CongestionForecastModel
    mean_absolute_error: float
    root_mean_squared_error: float
    training_samples: int
    validation_samples: int


def _synthetic_data(
    sample_count: int,
    horizon_seconds: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    pressure = rng.uniform(0.0, 1.0, sample_count)
    velocity = np.clip(rng.normal(0.0, 0.035, sample_count), -0.1, 0.1)
    acceleration = np.clip(rng.normal(0.0, 0.01, sample_count), -0.02, 0.02)
    utilization = np.clip(
        pressure + rng.normal(0.0, 0.15, sample_count),
        0.0,
        1.0,
    )
    queue_pressure = np.clip(
        pressure + rng.normal(0.0, 0.15, sample_count),
        0.0,
        1.0,
    )
    loss_rate = np.clip(
        np.maximum(pressure - 0.5, 0.0) * 0.15
        + rng.normal(0.0, 0.01, sample_count),
        0.0,
        0.1,
    )
    features = np.column_stack(
        (
            pressure,
            velocity * 10.0,
            acceleration * 50.0,
            utilization,
            queue_pressure,
            loss_rate * 10.0,
        )
    ).astype(np.float32)
    target = np.clip(
        pressure
        + velocity * horizon_seconds
        + 0.5 * acceleration * horizon_seconds**2,
        0.0,
        1.0,
    ).astype(np.float32)
    return features, target[:, np.newaxis]


def train_synthetic_congestion_model(
    sample_count: int = 5_000,
    seed: int = 7,
    epochs: int = 120,
    horizon_seconds: float = 5.0,
) -> PretrainingResult:
    """Pretrain an acceleration-aware forecaster on deterministic synthetic data."""
    if (
        not isinstance(sample_count, int)
        or isinstance(sample_count, bool)
        or sample_count < 20
    ):
        raise ValueError("Sample count must be an integer of at least 20.")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("Seed must be an integer.")
    if not isinstance(epochs, int) or isinstance(epochs, bool) or epochs <= 0:
        raise ValueError("Epoch count must be a positive integer.")
    if not math.isfinite(horizon_seconds) or horizon_seconds <= 0:
        raise ValueError("Forecast horizon must be a positive finite number.")

    rng = np.random.default_rng(seed)
    features, targets = _synthetic_data(sample_count, horizon_seconds, rng)
    permutation = rng.permutation(sample_count)
    validation_count = max(1, sample_count // 5)
    validation_indices = permutation[:validation_count]
    training_indices = permutation[validation_count:]
    training_features = features[training_indices]
    training_targets = targets[training_indices]
    validation_features = features[validation_indices]
    validation_targets = targets[validation_indices]

    hidden_width = 8
    weight_1 = rng.normal(
        0.0,
        math.sqrt(2.0 / (len(FEATURE_NAMES) + hidden_width)),
        (len(FEATURE_NAMES), hidden_width),
    ).astype(np.float32)
    bias_1 = np.zeros(hidden_width, dtype=np.float32)
    weight_2 = rng.normal(0.0, 0.2, (hidden_width, 1)).astype(np.float32)
    bias_2 = np.zeros(1, dtype=np.float32)
    learning_rate = 0.02
    batch_size = min(128, len(training_indices))

    for _ in range(epochs):
        order = rng.permutation(len(training_indices))
        for start in range(0, len(order), batch_size):
            batch_indices = order[start : start + batch_size]
            batch_x = training_features[batch_indices]
            batch_y = training_targets[batch_indices]

            hidden = np.tanh(batch_x @ weight_1 + bias_1)
            prediction = 1.0 / (
                1.0 + np.exp(-np.clip(hidden @ weight_2 + bias_2, -30.0, 30.0))
            )
            gradient_output = (
                2.0
                * (prediction - batch_y)
                * prediction
                * (1.0 - prediction)
                / len(batch_indices)
            )
            gradient_weight_2 = hidden.T @ gradient_output
            gradient_bias_2 = np.sum(gradient_output, axis=0)
            gradient_hidden = (gradient_output @ weight_2.T) * (1.0 - hidden**2)
            gradient_weight_1 = batch_x.T @ gradient_hidden
            gradient_bias_1 = np.sum(gradient_hidden, axis=0)

            weight_1 -= learning_rate * gradient_weight_1
            bias_1 -= learning_rate * gradient_bias_1
            weight_2 -= learning_rate * gradient_weight_2
            bias_2 -= learning_rate * gradient_bias_2

    model = CongestionForecastModel(
        weight_1=weight_1,
        bias_1=bias_1,
        weight_2=weight_2,
        bias_2=bias_2,
        horizon_seconds=horizon_seconds,
    )
    prediction = model.predict(validation_features)
    errors = prediction - validation_targets
    return PretrainingResult(
        model=model,
        mean_absolute_error=float(np.mean(np.abs(errors))),
        root_mean_squared_error=float(np.sqrt(np.mean(errors**2))),
        training_samples=len(training_indices),
        validation_samples=len(validation_indices),
    )


def save_weights(model: CongestionForecastModel, path: str | Path) -> None:
    """Save model parameters and their synthetic-training provenance."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        destination,
        weight_1=model.weight_1,
        bias_1=model.bias_1,
        weight_2=model.weight_2,
        bias_2=model.bias_2,
        horizon_seconds=np.asarray([model.horizon_seconds], dtype=np.float32),
        feature_names=np.asarray(FEATURE_NAMES),
        training_data=np.asarray(
            "deterministic synthetic congestion telemetry; not measured network data"
        ),
    )


def export_onnx(model: CongestionForecastModel, path: str | Path) -> None:
    """Export the forecaster to an ONNX file for compatible inference providers."""
    try:
        onnx = import_module("onnx")
        helper = import_module("onnx.helper")
        numpy_helper = import_module("onnx.numpy_helper")
    except ImportError as error:
        raise RuntimeError(
            "ONNX export requires the optional dependency. Install with "
            "`pip install -e \".[model-export]\"`."
        ) from error

    inputs = helper.make_tensor_value_info(
        "telemetry",
        onnx.TensorProto.FLOAT,
        [1, len(FEATURE_NAMES)],
    )
    outputs = helper.make_tensor_value_info(
        "forecast_pressure",
        onnx.TensorProto.FLOAT,
        [1, 1],
    )
    initializers = [
        numpy_helper.from_array(model.weight_1, name="weight_1"),
        numpy_helper.from_array(model.bias_1, name="bias_1"),
        numpy_helper.from_array(model.weight_2, name="weight_2"),
        numpy_helper.from_array(model.bias_2, name="bias_2"),
    ]
    nodes = [
        helper.make_node(
            "Gemm",
            ["telemetry", "weight_1", "bias_1"],
            ["hidden_linear"],
        ),
        helper.make_node("Tanh", ["hidden_linear"], ["hidden"]),
        helper.make_node(
            "Gemm",
            ["hidden", "weight_2", "bias_2"],
            ["forecast_logit"],
        ),
        helper.make_node(
            "Sigmoid",
            ["forecast_logit"],
            ["forecast_pressure"],
        ),
    ]
    graph = helper.make_graph(
        nodes,
        "synthetic_congestion_forecaster",
        [inputs],
        [outputs],
        initializer=initializers,
    )
    exported = helper.make_model(
        graph,
        producer_name="7g-backhaul-simulation",
        opset_imports=[helper.make_opsetid("", 17)],
    )
    exported.ir_version = 9
    exported.metadata_props.add(
        key="training_data",
        value="synthetic only; not calibrated on measured network telemetry",
    )
    exported.metadata_props.add(
        key="forecast_horizon_seconds",
        value=str(model.horizon_seconds),
    )
    onnx.checker.check_model(exported)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    onnx.save_model(exported, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--horizon-seconds", type=float, default=5.0)
    parser.add_argument("--output-dir", type=Path, default=Path("models"))
    args = parser.parse_args()

    result = train_synthetic_congestion_model(
        sample_count=args.samples,
        seed=args.seed,
        epochs=args.epochs,
        horizon_seconds=args.horizon_seconds,
    )
    weights_path = args.output_dir / "congestion_forecast.npz"
    model_path = args.output_dir / "congestion_forecast.onnx"
    save_weights(result.model, weights_path)
    export_onnx(result.model, model_path)
    print(f"Training samples: {result.training_samples}")
    print(f"Validation samples: {result.validation_samples}")
    print(f"Synthetic validation MAE: {result.mean_absolute_error:.6f}")
    print(f"Synthetic validation RMSE: {result.root_mean_squared_error:.6f}")
    print(f"Forecast horizon: {result.model.horizon_seconds:g} seconds")
    print(f"Saved weights: {weights_path}")
    print(f"Saved ONNX model: {model_path}")
    print("Training data is synthetic; validate and retrain with measured telemetry.")


if __name__ == "__main__":
    main()
