# Real Packet and NPU Demonstration

The simulator now has an opt-in packet path that uses real IPv4 UDP sockets on
the local machine. It splits a payload into framed datagrams, receives them on
the loopback interface, checks sequence metadata and a SHA-256 digest, and
reports measured local transfer time and goodput:

```powershell
python -m simulation.packet_demo --payload-size 64000 --max-datagram-bytes 1200
```

The configured datagram limit includes the simulator's 60-byte frame header.
This tests operating-system socket transmission and local UDP delivery; it does
not send across a physical NIC, model a radio/backhaul MTU, or guarantee delivery
on an external network. UDP has no retransmission in this demonstration.

## Synthetic congestion-model pretraining

The repository includes a deterministic pretraining pipeline for a small MLP
that predicts congestion pressure five seconds ahead from six telemetry
features. Its training data is generated from synthetic pressure, velocity,
acceleration, utilization, queue, and loss values; it is not measured network
data and its validation score must not be interpreted as real-network accuracy.
The default model has one hidden layer with eight units and uses a sigmoid
output constrained to `[0, 1]`.
The generated reference files are `models/congestion_forecast.onnx` and
`models/congestion_forecast.npz`.

Install the optional exporter and regenerate the `.npz` weights and ONNX model:

```powershell
pip install -e ".[model-export]"
python -m simulation.pretraining --output-dir models
```

The model's six `float32` inputs are ordered as `pressure`,
`pressure_velocity_x10`, `pressure_acceleration_x50`, `utilization`,
`normalized_queue_delay`, and `loss_rate_x10`. The model output is forecast
pressure in `[0, 1]`. Change the training data and validate against measured
telemetry before using the output for routing or operational decisions.

## Optional ONNX inference

An ONNX model and an installed vendor-compatible ONNX Runtime execution provider
are required to request inference:

```powershell
python -m simulation.packet_demo --model path\to\model.onnx --provider <provider-name>
```

Supply model input values in the model's declared order:

```powershell
python -m simulation.packet_demo --model models\congestion_forecast.onnx `
  --provider <provider-name> --features 0.7,0.2,0.1,0.7,0.7,0.05
```

The input is one `float32` tensor with shape `[1, feature_count]`. For the
included model, input order and scaling are documented above. Output is printed
as forecast pressure. The provider name must be explicit and cannot be
`CPUExecutionProvider`. ONNX Runtime profiling is checked after inference;
missing node-provider events or any profiled CPU/other-provider fallback fails
explicitly.

Provider names, model operator support, and provider options depend on the
hardware, driver, operating system, and vendor runtime. A provider trace alone
does not prove which physical accelerator executed the operation. Configure
the vendor runtime for its NPU device and verify that device using its own
diagnostic tools. No NPU hardware or vendor runtime is bundled with this
repository. Hardware execution cannot be claimed until validated on the target
device.
