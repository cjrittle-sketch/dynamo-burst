#!/usr/bin/env python3
"""dynamo-burst shard worker.

Runs one shard file (a JSON list of Dynamo-shaped jobs) against a local
Ollama server and writes one result JSON per job into the output dir.

Dependency-light: stdlib only (json, urllib). No API keys, no network
beyond localhost.

Each job dict must have:
  job_id       - string, Dynamo job-id charset
  prompt_text  - string, the full prompt (split.py inlines prompt_file)
Optional:
  max_output_tokens - int, default 4000, capped at 32000

Result record per job (<out>/<job_id>.json):
  {"job_id": ..., "ok": true, "output": ...,
   "prompt_eval_count": N, "eval_count": M, "duration_ms": T}
or on failure:
  {"job_id": ..., "ok": false, "error": "..."}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MAX_TOKENS = 4000
MAX_TOKENS_CAP = 32000
RETRIES = 6


def ollama_generate(prompt: str, model: str, max_tokens: int) -> dict:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    last_err: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - retry transient runner faults
            last_err = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"ollama generate failed after {RETRIES} retries: {last_err}")


def run_job(job: dict, model: str) -> dict:
    job_id = job["job_id"]
    prompt = job["prompt_text"]
    max_tokens = int(job.get("max_output_tokens", DEFAULT_MAX_TOKENS))
    max_tokens = max(1, min(max_tokens, MAX_TOKENS_CAP))
    t0 = time.time()
    try:
        resp = ollama_generate(prompt, model, max_tokens)
        return {
            "job_id": job_id,
            "ok": True,
            "output": resp.get("response", ""),
            "prompt_eval_count": resp.get("prompt_eval_count"),
            "eval_count": resp.get("eval_count"),
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as exc:  # noqa: BLE001 - record failure, keep shard going
        return {
            "job_id": job_id,
            "ok": False,
            "error": str(exc)[:500],
            "duration_ms": int((time.time() - t0) * 1000),
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run one dynamo-burst shard.")
    ap.add_argument("--shard", required=True, help="Path to shard JSON file")
    ap.add_argument("--out", required=True, help="Output directory for results")
    ap.add_argument("--model", required=True, help="Ollama model tag")
    args = ap.parse_args()

    with open(args.shard, "r", encoding="utf-8") as fh:
        jobs = json.load(fh)
    if not isinstance(jobs, list):
        print("shard file must contain a JSON list of jobs", file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)

    ok = failed = 0
    for job in jobs:
        if not isinstance(job, dict) or "job_id" not in job or "prompt_text" not in job:
            print(f"skipping malformed job entry: {str(job)[:120]}", file=sys.stderr)
            failed += 1
            continue
        rec = run_job(job, args.model)
        out_path = os.path.join(args.out, f"{rec['job_id']}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=2)
        if rec["ok"]:
            ok += 1
        else:
            failed += 1
            print(f"job {rec['job_id']} FAILED: {rec['error']}", file=sys.stderr)

    print(f"shard done: {ok} ok, {failed} failed, {len(jobs)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
