# dsbench summary

Label: `row13-metrics`. Accepted cells: 13; invalid attempts: 0; blocked cells: 0.

Benchmark requests use bounded `max_tokens` only for measurement; production omp remains uncapped.

## Requirement table

| context | C | aggregate (95% CI) / target | median stream (95% CI) / target | p10 | result |
|---:|---:|---:|---:|---:|:---:|
| 0 | 1 | 60.08 [60.08, 60.08] / 68.00 | 60.08 [60.08, 60.08] / 68.00 | 43.064493716492635 | FAIL |
| 0 | 4 | 87.91 [87.91, 87.91] / 150.00 | 29.94 [29.94, 29.94] / 37.50 | 18.2687297327112 | FAIL |
| 0 | 8 | 99.71 [99.71, 99.71] / 190.00 | 21.04 [21.04, 21.04] / 23.75 | 15.361981094993848 | FAIL |
| 32k | 1 | 63.06 [63.06, 63.06] / 65.00 | 63.06 [63.06, 63.06] / 65.00 | 48.98694906726274 | FAIL |
| 32k | 4 | 47.29 [47.29, 47.29] / 145.00 | 19.19 [19.19, 19.19] / 36.25 | 14.914705468566284 | FAIL |
| 32k | 8 | 60.05 [60.05, 60.05] / 185.00 | 14.03 [14.03, 14.03] / 23.10 | 8.213343656308837 | FAIL |
| 128k | 1 | missing / 62.00 | missing / 62.00 | — | FAIL |
| 128k | 4 | missing / 138.00 | missing / 34.50 | — | FAIL |
| 128k | 8 | missing / 175.00 | missing / 21.90 | — | FAIL |
| 400k | 1 | missing / 58.00 | missing / 58.00 | — | FAIL |
| 400k | 4 | missing / 130.00 | missing / 32.50 | — | FAIL |
| 400k | 8 | missing / 165.00 | missing / 20.60 | — | FAIL |
| equal-context-gm | 1 | missing / 63.00 | missing / 63.00 | — | FAIL |
| equal-context-gm | 4 | missing / 140.00 | missing / 35.00 | — | FAIL |
| equal-context-gm | 8 | missing / 180.00 | missing / 22.50 | — | FAIL |

## Speculative decode decomposition

| profile | context | C | steps/s | committed/step | accept rate | server tok/s |
|---|---:|---:|---:|---:|---:|---:|
| S0 | 0 | 1 | 15.746 | 2.326 | 0.245 | 36.625 |
| S0 | 0 | 4 | 29.432 | 2.517 | 0.317 | 74.078 |
| S0 | 0 | 8 | 39.491 | 2.353 | 0.272 | 92.925 |
| S0 | 32k | 1 | 12.024 | 2.805 | 0.362 | 33.732 |
| S0 | 32k | 4 | 16.074 | 2.394 | 0.281 | 38.483 |
| S0 | 32k | 8 | 18.011 | 2.346 | 0.280 | 42.245 |
| S1-omp | 0 | 1 | 15.500 | 4.545 | 0.695 | 70.453 |
| S1-omp | 0 | 4 | 32.948 | 2.918 | 0.384 | 96.139 |
| S1-omp | 0 | 8 | 37.243 | 2.845 | 0.363 | 105.938 |
| S1-omp | 128k | 1 | 1.165 | 4.460 | 0.692 | 5.197 |
| S1-omp | 32k | 1 | 4.110 | 4.549 | 0.720 | 18.698 |
| S1-omp | 32k | 4 | 20.352 | 2.819 | 0.362 | 57.368 |
| S1-omp | 32k | 8 | 24.223 | 2.797 | 0.364 | 67.759 |

## Correctness and category guardrails

Prompt output qualification: FAIL.

| context | category group | score | floor | result |
|---:|---|---:|---:|:---:|
| 0 | agentic_code | 61.47 | 72.00 | FAIL |
| 0 | prose | — | 40.00 | FAIL |
| 400k | agentic_code | — | 62.00 | FAIL |
| 400k | prose | — | 34.00 | FAIL |

Invalid attempts remain in the raw receipts and never enter accepted-score calculations. A failed/blocked requirement is not converted into a best-of-retries result.
