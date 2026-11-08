# Measured complete workloads

## Current numeric11 capacity qualification

Kernel `0.2.0-numeric-11` includes age aggregation, switching state and claim skepticism. A cold fictional game/campaign workload completed100000individuals over30days,3candidates+3price-matched controls,1exploration+1validation seed: **12complete replicas,36million agent-days in136.810s**, **120.66MiB peak engine-process RSS**,4,256,337retained cache/checkpoint bytes and **0APIcalls**. All12results were computed from an empty directory. [Raw evidence](benchmarks-numeric11.json).

This capacity workload uses campaign mode; market-switching routes are exercised separately in targeted tests and the installed worker smoke. It is not the archived120-replica qualification below, not100000LLM conversations, and not evidence of real-market representativeness. Other development services may be active.

## Archived numeric10 capacity qualification

The earlier kernel was `0.2.0-numeric-10` (claim skepticism and resilient atomic writes). A fresh 100,000-person workload completed all three candidates and three price-matched controls over30days with1exploration+1validation seed per scenario: **12complete replicas,36million agent-days**, **129.296seconds**, **117.31MiB peak engine-process RSS**,4,228,687retained checkpoint/cache bytes and **zero external API calls**. No replica results existed beforehand; all12were computed and committed. [Raw evidence](benchmarks-numeric10.json).

```sh
uv run python scripts/benchmark.py --sizes 100000 --days 30 --repetitions 1
```

This is a capacity/smoke workload with complete calendars, not a20-seed strategy qualification. It must not be compared directly with the120-replica timings below. Ordinary numeric outcomes also retain exact numeric9 regression projections for baseline and mixed social/search cases; new claim-response coefficients remain unvalidated assumptions. Source tests separately exercise unsupported claims, repeated exposure and checkpoint resumption.

## Archived numeric9 full-repeat workload

Release kernel: `0.1.0-numeric-9`, measured on AMD Ryzen 7 7435HS (16 logical CPUs),63.7 GiB RAM,Windows build 26300,CPython 3.11.15.

Every population ran three price/media candidates plus three price-matched no-campaign controls,30 days,10 exploration and10 validation seeds: **120 complete scenario replicas**. Distinct unweighted numerical individuals, social propagation, fatigue, integer acquisition/cost gates, checkpoints and committed replica result writes were enabled.

| Individuals | Computed agent-days | Wall seconds | Peak process RSS (MiB) | Retained checkpoint/cache bytes | External API calls |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 3,600,000 | 72.843 | 65.54 | 36,538,424 | 0 |
| 10,000 | 36,000,000 | 185.780 | 70.58 | 36,435,935 | 0 |
| 100,000 | 360,000,000 | 1052.859 | 123.66 | 35,722,390 | 0 |

The 100,000-person case completed **360 million agent-days in 17 min 32.859 s**, with 123.66 MiB peak process RSS and zero inference/search calls in this numeric workload. This measures the Python engine process, not the browser/whole-machine memory or a population of 100,000 independent LLM conversations.

## Reproduce

```sh
uv run python scripts/benchmark.py --sizes 1000,10000,100000 --days 30 --repetitions 10
```

Every measurement uses a unique empty directory. The [raw evidence](benchmarks-numeric9.json) records cold mode, zero preexisting results and 120 actually committed replicas per population. A repeated invocation cannot silently substitute cache reloads for computed agent-days.

Wall time includes checkpoint/cache work; peak RSS is sampled for this process. Other development services may be active, so these are observed local results, not a guarantee for another machine. The tested workload uses the fictional game preset's placements, not every possible 15-channel custom plan. Historical development kernels are not substituted for this release's numbers.

Population size and repeated seeds do not establish empirical market representativeness, proprietary-platform fidelity or forecast accuracy. See [methodology](METHODOLOGY.md).
