# dynamo-burst guardrails

Read this before dispatching any burst. These are hard rules, not suggestions.

## 1. Public-safe data ONLY

Everything in a burst — job prompts, model outputs, workflow logs, uploaded
artifacts — lives on public infrastructure:

- This repo is public, so committed shard files are world-readable.
- GitHub Actions logs are visible; avoid printing prompt contents in logs.
- Result artifacts are downloadable; treat them as published.
- Runners are shared, ephemeral VMs you do not control.

Therefore a burst must NEVER contain:

- Private notes, journals, messages, or anything from a private chat.
- Details about any real person, living or dead. Family research (names,
  dates, places, relationships, biographies) NEVER rides a burst.
- Credentials, API keys, tokens, passwords, or any secret.
- Personal identifiers: addresses, phone numbers, emails, account numbers.

The splitter (`tools/split.py`) hard-refuses any job flagged
`sensitive=true`. That is a backstop, not a substitute for judgment:
when in doubt, keep the job on a private lane instead.

## 2. Repo-shaped batch work only

A burst is one workflow run over a fixed set of shard files: fan out, run,
collect, done. It is for occasional large batches (tens to hundreds of
small jobs). It is NOT for:

- Daemons, watchers, queues, or anything long-lived.
- Interactive work or jobs needing secrets at runtime.
- Anything that must finish by a deadline (runners are best-effort).

## 3. GitHub terms gray area

GitHub Actions is intended for CI/CD and automation tied to the repository.
Using it as a general-purpose compute farm is outside that intended use.
Public repos get generous minutes, but abnormal usage patterns can get a
repository or account flagged. Keep bursts occasional, keep them plausibly
tied to this repo's purpose (batch text processing), and never use bursts
to mine, spam, attack, or evade rate limits elsewhere.

## 4. Data handling after a burst

- Download result artifacts promptly; they expire after 7 days.
- Delete the run's artifacts from GitHub once collected.
- Do not commit result outputs back to the repo unless they are
  independently public-safe (assume they are not, by default).
