# M4 summary (means and 95% confidence intervals over 30 paired seeds)

Bare numbers.  H5 verdict is mechanical; interpretation in M5.

## exp1

| baseline | Total_Throughput_CBF | Legitimate_Goodput_CMRO2 | OEF_Value | OEF_Change_Speed | OEF_Change_Acceleration | OEF_Limit_Hit | p95_Ratio | Goodput_Base |
|---|---|---|---|---|---|---|---|---|
| oef_surgical | 297541774.6914 +/- 10753156.7647 | 0.8576 +/- 0.0573 | 0.9951 +/- 0.0095 | 0.5000 +/- 0.0000 | 0.4000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0718 +/- 0.0430 | 0.9522 +/- 0.0036 |
| surgical | 0.0000 +/- 0.0000 | 0.8576 +/- 0.0573 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 1.0718 +/- 0.0430 | 0.9522 +/- 0.0036 |

## exp2

| baseline | Legitimate_Goodput | Transit_Drop_Rate | p95_Ratio | OEF_Value |
|---|---|---|---|---|
| oef_max1.5 | 0.8593 +/- 0.0576 | 0.0980 +/- 0.0344 | 1.0552 +/- 0.0345 | 1.0000 +/- 0.0000 |
| oef_max16 | 0.8594 +/- 0.0576 | 0.0965 +/- 0.0347 | 1.0610 +/- 0.0341 | 1.0000 +/- 0.0000 |
| oef_max2 | 0.8590 +/- 0.0576 | 0.0958 +/- 0.0349 | 1.0692 +/- 0.0332 | 1.0000 +/- 0.0000 |
| oef_max4 | 0.8595 +/- 0.0576 | 0.0963 +/- 0.0347 | 1.0612 +/- 0.0340 | 1.0000 +/- 0.0000 |
| oef_max8 | 0.8594 +/- 0.0576 | 0.0965 +/- 0.0347 | 1.0610 +/- 0.0341 | 1.0000 +/- 0.0000 |

## exp3

| baseline | Trigger_Latency_s | False_Positives | Legitimate_Goodput | p95_Ratio | OEF_Limit_Hit |
|---|---|---|---|---|---|
| mkb | 5.1933 +/- 1.8093 | 14.1000 +/- 2.0381 | 0.5090 +/- 0.0363 | 1.3558 +/- 0.0578 | 1.0000 +/- 0.0000 |
| oef_surgical | 0.8640 +/- 0.8753 | 0.0000 +/- 0.0000 | 0.8576 +/- 0.0573 | 1.0718 +/- 0.0430 | 1.0000 +/- 0.0000 |
| surgical | 0.8640 +/- 0.8753 | 0.0000 +/- 0.0000 | 0.8576 +/- 0.0573 | 1.0718 +/- 0.0430 | 0.0000 +/- 0.0000 |

CBF (Total_Throughput) is instrumented by the OEF/MKB
controller; the plain surgical arm carries no CBF monitor and
therefore reports 0.
