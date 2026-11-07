# Measured workloads

Performance evidence is measured on a local Windows machine, not extrapolated from the OASIS paper or a GPU cluster.

Current release kernel: `0.1.0-numeric-9`. The complete cold benchmark is being qualified before the v0.1 release; final measurements will replace this note.

## Protocol

- Fictional game, three price/media candidates and three price-matched no-campaign controls.
- Thirty daily rounds, ten exploration and ten validation seeds: **120 complete scenario replicas** per population.
- Distinct unweighted numerical individuals, actual social propagation, fatigue, costs, first-purchase gates and checkpoint/result persistence enabled.
- No external model/search calls in the numeric workload.
- A new empty measurement directory for every population. Output records zero preexisting results and the actual number of committed replicas. Warm cache reloads are never reported as cold simulated agent-days.
- Peak RSS is sampled for the benchmark Python process, not the whole machine; reported wall time includes checkpoint/cache work. Other development services may be running, so these are observed local results, not a hardware guarantee.

```sh
uv run python scripts/benchmark.py --sizes 1000,10000,100000 --days 30 --repetitions 10
```

Hardware: AMD Ryzen 7 7435HS, 16 logical CPUs, 63.7 GiB RAM; CPython 3.11.15, Windows build 26300.

First current-kernel result: 1,000 people, 3.6 million agent-days, 120 committed replicas, **72.843 seconds**, **65.54 MiB peak process RSS**, zero external calls. Larger current-kernel runs are still in progress at this document stage.

Earlier development kernels were measured separately. Their numbers are not substituted for the current release's final qualification. Numerical population size does not demonstrate empirical market representativeness or prediction quality.
