#!/usr/bin/env python3
"""Split Dynamo job JSONs into K self-contained shard files for dynamo-burst.

Reads *.json job files (Dynamo shape) from --jobs-dir, validates each one,
inlines prompt_file content into prompt_text (runners have no access to the
origin machine's files), and writes K shard files as
<out-dir>/shard-0000.json ... shard-(K-1).json (round-robin assignment).

PRIVACY INTERLOCK: any job with sensitive=true is REFUSED outright and the
split aborts. The burst pattern is public-safe data only (see GUARDRAILS.md);
this check exists so a sensitive job can never accidentally ride a burst.

Usage:
  python3 tools/split.py --jobs-dir /path/to/jobs --shards 32 --out-dir shards/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_TOKENS_CAP = 32000


def fail(msg: str) -> None:
    print(f"split.py ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def load_job(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        job = json.load(fh)
    if not isinstance(job, dict):
        fail(f"{path}: job must be a JSON object")

    job_id = job.get("job_id")
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        fail(f"{path}: bad job_id {job_id!r}")

    # --- privacy interlock: sensitive jobs may never ride a burst ---
    if job.get("sensitive", False):
        fail(
            f"{path}: job {job_id} is flagged sensitive=true -- "
            "REFUSED. Bursts are public-safe data only (see GUARDRAILS.md)."
        )

    has_text = job.get("prompt_text") is not None
    has_file = job.get("prompt_file") is not None
    if not has_text and not has_file:
        fail(f"{path}: job {job_id} needs prompt_text or prompt_file")
    if has_file:
        pf = job["prompt_file"]
        if not isinstance(pf, str) or not os.path.isfile(pf):
            fail(f"{path}: job {job_id} prompt_file missing: {pf!r}")
        with open(pf, "r", encoding="utf-8") as fh:
            job["prompt_text"] = fh.read()
        del job["prompt_file"]

    mot = job.get("max_output_tokens", 4000)
    try:
        mot = int(mot)
    except (TypeError, ValueError):
        fail(f"{path}: job {job_id} bad max_output_tokens {mot!r}")
    job["max_output_tokens"] = max(1, min(mot, MAX_TOKENS_CAP))

    lane = job.get("lane", "ollama")
    if lane != "ollama":
        print(
            f"note: job {job_id} lane={lane} ignored; "
            "burst runners only serve the local ollama lane",
            file=sys.stderr,
        )
    return {"job_id": job_id, "prompt_text": job["prompt_text"],
            "max_output_tokens": job["max_output_tokens"]}


def main() -> None:
    ap = argparse.ArgumentParser(description="Split Dynamo jobs into burst shards.")
    ap.add_argument("--jobs-dir", required=True)
    ap.add_argument("--shards", required=True, type=int)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    if not 1 <= args.shards <= 256:
        fail("--shards must be 1..256")
    if not os.path.isdir(args.jobs_dir):
        fail(f"--jobs-dir not a directory: {args.jobs_dir}")

    paths = sorted(
        p for p in os.listdir(args.jobs_dir) if p.endswith(".json")
    )
    if not paths:
        fail(f"no job JSON files in {args.jobs_dir}")

    jobs = [load_job(os.path.join(args.jobs_dir, p)) for p in paths]
    ids = [j["job_id"] for j in jobs]
    if len(set(ids)) != len(ids):
        fail("duplicate job_id values in input jobs")

    os.makedirs(args.out_dir, exist_ok=True)
    buckets: list[list[dict]] = [[] for _ in range(args.shards)]
    for i, job in enumerate(jobs):
        buckets[i % args.shards].append(job)

    for i, bucket in enumerate(buckets):
        out_path = os.path.join(args.out_dir, f"shard-{i:04d}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(bucket, fh, ensure_ascii=False, indent=2)

    sizes = [len(b) for b in buckets]
    print(f"split {len(jobs)} jobs into {args.shards} shards "
          f"(sizes {min(sizes)}..{max(sizes)}) -> {args.out_dir}")


if __name__ == "__main__":
    main()
