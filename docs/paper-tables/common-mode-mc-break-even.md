### Break-even values under the Monte Carlo engine

Grid: 25 values per constant, 500 replications per point, linear interpolation between adjacent grid points. A break-even is the value at which the named criterion stops passing; `none in range` means it passed at every swept value.

| Constant | Stipulated | Sweep | Primary break-even | Claim that fails there | Margin |
|---|---:|---|---:|---|---:|
| one-way local-policy efficiency | 0.9 fraction | 0.5-1 fraction | 0.847775 | H18: normal-operation cost of the one-way boundary <= 15 points | -0.052225 |
| tested fallback activation probability | 0.98 fraction | 0-1 fraction | 0.367502 | tested fallback beats untested under the backhaul cut (gap > 0) | -0.612498 |
| untested fallback activation probability | 0.6 fraction | 0-1 fraction | none in range | criterion survives the whole swept range |  |
| tested fallback activation delay | 2 s | 0-25 s | none in range | criterion survives the whole swept range |  |
| untested fallback activation delay | 8 s | 0-30 s | none in range | criterion survives the whole swept range |  |
| tested fallback capacity | 0.5 Gbps | 0-1 Gbps | 0.185568 | tested fallback beats untested under the backhaul cut (gap > 0) | -0.314432 |
| untested fallback capacity | 0.3 Gbps | 0-1 Gbps | 0.833202 | tested fallback beats untested under the backhaul cut (gap > 0) | +0.533202 |

Full per-criterion results, including the H18 and H19 sub-criteria, are in `common-mode-mc-break-even.csv`; the full grid is in `common-mode-mc-sensitivity.csv`.

### H19 criteria break-even

| Constant | Stipulated | Criterion | Break-even | Direction |
|---|---:|---|---:|---|
| one_way_efficiency | 0.9 | H19_interaction | 0.688011 | decreasing |
| one_way_efficiency | 0.9 | H19_a6_level | 0.800052 | decreasing |
| fallback_tested_probability | 0.98 | H19_interaction | none in range | none in range |
| fallback_tested_probability | 0.98 | H19_a6_level | none in range | none in range |
| fallback_untested_probability | 0.6 | H19_interaction | none in range | none in range |
| fallback_untested_probability | 0.6 | H19_a6_level | none in range | none in range |
| fallback_tested_delay_s | 2 | H19_interaction | none in range | none in range |
| fallback_tested_delay_s | 2 | H19_a6_level | none in range | none in range |
| fallback_untested_delay_s | 8 | H19_interaction | none in range | none in range |
| fallback_untested_delay_s | 8 | H19_a6_level | none in range | none in range |
| fallback_tested_capacity_gbps | 0.5 | H19_interaction | 0.718615 | increasing |
| fallback_tested_capacity_gbps | 0.5 | H19_a6_level | none in range | none in range |
| fallback_untested_capacity_gbps | 0.3 | H19_interaction | none in range | none in range |
| fallback_untested_capacity_gbps | 0.3 | H19_a6_level | none in range | none in range |

