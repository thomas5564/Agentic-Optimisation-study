# Three-arm add-on: stateless vs memory vs memory + LRU

A separate test that compares three Planner memory arms. It does not modify any existing file:

| Arm | Planner history |
|---|---|
| `stateless` | none |
| `memory` | every prior attempt entry (unchanged existing protocol) |
| `memory_lru` | at most K entries, kept by least-recently-used eviction |

## LRU rule
The Planner's output gains `used_memory`: the iteration numbers of the shown entries it
relied on. After each attempt, the runner:
1. moves cited entries that were actually shown to the most-recent end (other citations are
   ignored and logged);
2. inserts the new attempt's entry (failed attempts included);
3. evicts least-recently-used entries until K remain.

The cache is replayed from the attempt records every time, so resume is deterministic and
never duplicates entries. `memory.json` still holds the complete log. `lru-state.json` and
`lru/NNN.json` record exactly what each Planner was shown, cited and evicted.

## How it plugs in
- An LRU run is stored by the existing controller as condition `memory`. The sidecar `lru.json`,
  written before the manifest, marks it as LRU and archives this package's source.
- `LruEngine` subclasses `controller.engine.Engine`. During an LRU run only, it swaps
  `agents.schemas.OUTPUTS["planner"]` for `LruPlan` and adds a `memory_policy` note to the
  Planner's evidence. `planner.txt` is unchanged, so all arms share the same base prompt.
- Nothing is added under `controller/`, `agents/` or `benchmarks/`, so `implementation_hashes()`
  and all existing runs and configs are unaffected.

## Commands
```bash
python -m lru_memory.run --backend mock --condition memory_lru --capacity 2 --iterations 5 --config configs/smoke.yaml --output /path/outside/repo/lru
python -m lru_memory.batch --backend mock --capacity 3 --iterations 3 --config configs/mock-paired.yaml --output /path/outside/repo/three-arm
python -m lru_memory.resume --run-dir /path/outside/repo/three-arm/rep-00-memory_lru
python -m lru_memory.report --runs-dir /path/outside/repo/three-arm --output /path/outside/repo/three-arm-report
python -m pytest tests/test_lru_memory.py -q
```

## Live runs (SOCLAAS)
`agents.credentials` only runs `controller.*` modules, so use `lru_memory.credentials` instead.
It reads the same `soclaas.env` as data, never executing it.

1. Create `soclaas.env` in the repo root (it is gitignored), then `chmod 600 soclaas.env`:
   ```
   SOCLAAS_BASE_URL=https://soclaas-api.comp.nus.edu.sg/v1
   SOCLAAS_API_KEY=<your key>
   SOCLAAS_MODEL=default
   ```
2. Start Docker. The configured image must exist locally:
   `docker image inspect sha256:b5ab7123fadb36abfa68da75d1e7c6e6edc789a9370dcf24f4c8411b327fbe2e`.
   If it doesn't, build one with the main README's `docker build` command and put its ID in your config.
3. Run the unpaid preflight:
   `python -m lru_memory.credentials --file soclaas.env --module agents.preflight -- --config configs/lru-soclaas-smoke.yaml`
4. Smoke (3 arms × 2 iterations, small benchmark):
   ```bash
   python -m lru_memory.credentials --file soclaas.env --module lru_memory.batch -- --backend chat --capacity 3 --iterations 2 --config configs/lru-soclaas-smoke.yaml --output ~/comp690-runs/lru-smoke
   ```
5. Pilot, comparable to the recorded pilot: the same command with
   `--iterations 10 --config configs/lru-soclaas-pilot.yaml` and a new output directory.
   Both LRU configs use the local `notes-experiment:dev` image (`sha256:b5ab7123…`), not the
   recorded study's `385b5ef…`, so absolute latencies are not directly comparable to the old runs.

Each replicate runs all three arms with the same seed. The order rotates per replicate
(S,M,L → M,L,S → L,S,M). The report labels runs that have `lru.json` as `memory_lru`. It
compares final latency for each pair of arms within a replicate, and also reports tokens,
acceptance, correctness, repeats and LRU citation use. Figures need `requirements-analysis.lock`
(matplotlib); otherwise pass `--no-figures`.

## Caveats
- **Resume LRU runs only with `lru_memory.resume`.** `controller.resume` would continue
  them with complete memory.
- `memory_lru` relaxes the main protocol's "complete memory, no filtering" invariant on purpose.
- Citations are self-reported by the model. A Planner that cites nothing turns the cache into a
  sliding window of the last K attempts; `lru.csv` shows how often citations happened.
- The frozen `configs/final.yaml` covers two arms, so this tool refuses `phase: final`.
  Choose K and freeze a new three-arm config before running a final study.
- Mock results are smoke checks only. The mock Planner always cites the earliest shown entry.
