### Break-even values for the stipulated constants

Grid: 25 values per constant, 30 paired seeds, linear interpolation between adjacent grid points. A break-even is the value at which the named criterion stops passing; `none in range` means it passed at every swept value.

| Constant | Stipulated | Sweep | Primary break-even | Claim that fails there | Margin |
|---|---:|---|---:|---|---:|
| one-way local-policy efficiency | 0.9 fraction | 0.5-1 fraction | 0.85 | H18: normal-operation cost of the one-way boundary <= 15 points | -0.05 |
| tested fallback activation probability | 0.98 fraction | 0-1 fraction | 0.222334 | tested fallback beats untested under the backhaul cut (gap > 0) | -0.757666 |
| untested fallback activation probability | 0.6 fraction | 0-1 fraction | none in range | criterion survives the whole swept range |  |
| tested fallback activation delay | 2 s | 0-25 s | 18.166 | tested fallback beats untested under the backhaul cut (gap > 0) | +16.166 |
| untested fallback activation delay | 8 s | 0-30 s | none in range | criterion survives the whole swept range |  |
| tested fallback capacity | 0.5 Gbps | 0-1 Gbps | 0.12172 | tested fallback beats untested under the backhaul cut (gap > 0) | -0.37828 |
| untested fallback capacity | 0.3 Gbps | 0-1 Gbps | none in range | criterion survives the whole swept range |  |

For H18, the binding clause is the normal-operation cost (`0.85`), not the absolute 80 % level (`0.8`); the model check fails at the higher of the two values.

Full per-criterion results, including H18 and H19 sub-criteria, are in `common-mode-break-even.csv`; the grid is in `common-mode-sensitivity.csv`.

### H19 criteria break-even

| Constant | Stipulated | Criterion | Break-even | Direction |
|---|---:|---|---:|---|
| one_way_efficiency | 0.9 | H19_interaction | 0.656242 | decreasing |
| one_way_efficiency | 0.9 | H19_a6_level | 0.8 | decreasing |
| fallback_tested_probability | 0.98 | H19_interaction | none in range | none in range |
| fallback_tested_probability | 0.98 | H19_a6_level | none in range | none in range |
| fallback_untested_probability | 0.6 | H19_interaction | none in range | none in range |
| fallback_untested_probability | 0.6 | H19_a6_level | none in range | none in range |
| fallback_tested_delay_s | 2 | H19_interaction | none in range | none in range |
| fallback_tested_delay_s | 2 | H19_a6_level | none in range | none in range |
| fallback_untested_delay_s | 8 | H19_interaction | none in range | none in range |
| fallback_untested_delay_s | 8 | H19_a6_level | none in range | none in range |
| fallback_tested_capacity_gbps | 0.5 | H19_interaction | 0.767137 | increasing |
| fallback_tested_capacity_gbps | 0.5 | H19_a6_level | none in range | none in range |
| fallback_untested_capacity_gbps | 0.3 | H19_interaction | none in range | none in range |
| fallback_untested_capacity_gbps | 0.3 | H19_a6_level | none in range | none in range |

