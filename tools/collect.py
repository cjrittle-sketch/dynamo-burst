#!/usr/bin/env python3
"""Merge dynamo-burst shard results into one manifest.

Reads per-shard result directories (each containing <job_id>.json files, as
produced by worker/worker.py and downloaded via `gh run download`), checks
every job_id expected by the shard files, and writes:
  <out>/manifest.json  - counts, missing/failed job lists
  <out>/results.jsonl   - one result record per job

Usage:
  python3 tools/collect.py --results-dir burst-out/ \
      --shards-dir shards/ --out merged/
  # where burst-out/ contains one subdir per shard
  # (e.g. burst-results-0000/, burst-results-0001/, ...)

Exit code 0 only when every expected job has an ok result.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone


def fail(msg: str) -> None:
    print(f"collect.py ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge burst shard results.")
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--shards-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    for d, name in ((args.results_dir, "--results-dir"),
                    (args.shards_dir, "--shards-dir")):
        if not os.path.isdir(d):
            fail(f"{name} not a directory: {d}")

    # Expected job ids from the shard files we dispatched.
    expected: dict[str, str] = {}
    for fn in sorted(os.listdir(args.shards_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(args.shards_dir, fn), encoding="utf-8") as fh:
            for job in json.load(fh):
                expected[job["job_id"]] = fn

    # Gather result records from every per-shard results subdir.
    found: dict[str, dict] = {}
    for sub in sorted(os.listdir(args.results_dir)):
        subdir = os.path.join(args.results_dir, sub)
        if not os.path.isdir(subdir):
            continue
        for fn in os.listdir(subdir):
            if not fn.endswith(".json"):
                continue
            with open(os.path.join(subdir, fn), encoding="utf-8") as fh:
                rec = json.load(fh)
            jid = rec.get("job_id")
            if jid:
                found[jid] = rec

    ok_recs, failed, missing = [], [], []
    for jid in sorted(expected):
        rec = found.get(jid)
        if rec is None:
            missing.append(jid)
        elif rec.get("ok"):
            ok_recs.append(rec)
        else:
            failed.append({"job_id": jid, "error": rec.get("error")})

    os.makedirs(args.out, exist_ok=True)
    manifest = {
        "burst": "dynamo-burst",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "total_jobs": len(expected),
        "ok": len(ok_recs),
        "failed": len(failed),
        "missing": missing,
        "failed_jobs": failed,
    }
    with open(os.path.join(args.out, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "results.jsonl"), "w",
              encoding="utf-8") as fh:
        for rec in ok_recs:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"collected {len(ok_recs)}/{len(expected)} ok, "
          f"{len(failed)} failed, {len(missing)} missing -> {args.out}")
    if failed or missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
