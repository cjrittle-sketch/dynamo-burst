# dynamo-burst

Occasional "monster batch" bursts for Dynamo: fan a batch of small,
public-safe LLM jobs across N ephemeral GitHub Actions runners, then merge
the results. Not a daily driver. Not for private data.

**Read GUARDRAILS.md first.** Bursts are public-safe data only, always.

## Layout

- `.github/workflows/burst.yml` — matrix workflow (workflow_dispatch).
  Inputs: `shard_count`, `model` (default `qwen2.5:0.5b`).
- `worker/worker.py` — runs one shard against local Ollama (stdlib only).
- `tools/split.py` — Dynamo job JSONs -> K shard files. Refuses
  `sensitive=true` jobs outright.
- `tools/collect.py` — merges per-shard results into one manifest.
- `shards/` — committed shard files for the next burst (public-safe only).

## Running a burst

```bash
# 1. Split Dynamo-shaped job JSONs into K shards (K <= 256)
python3 tools/split.py --jobs-dir /path/to/jobs --shards 32 --out-dir shards/

# 2. Commit + push the shards
git add shards/ && git commit -m "burst: <name> <K> shards" && git push

# 3. Dispatch (needs gh auth)
gh workflow run burst.yml -f shard_count=32 -f model=qwen2.5:0.5b

# 4. When the run finishes, download + merge
RUN=<run-id>
gh run download "$RUN" -D burst-out/
python3 tools/collect.py --results-dir burst-out/ --shards-dir shards/ --out merged/
```

Each runner installs Ollama, pulls the model, runs
`worker/worker.py --shard shards/shard-<i>.json`, and uploads its
`results/` dir as artifact `burst-results-<i>` (7-day retention).

## Job shape

Same as Dynamo (`~/workspace/free-stack/dispatch`): `job_id`, plus
`prompt_text` (split.py inlines `prompt_file` for you) and optional
`max_output_tokens` (default 4000, cap 32000). The `lane` field is
ignored — burst runners only serve the local ollama lane.
