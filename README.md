# Mandarin WOTD

A daily Mandarin word-of-the-day, published as a tiny JSON file for a
[TRMNL](https://usetrmnl.com/) e-ink screen to poll.

The word is picked deterministically from the HSK 1–6 vocabulary lists, so the
choice is stable for any given date in Europe/London regardless of when the
workflow runs.

## What you get

`today.json` lives at the root of `main` and looks like:

```json
{
  "hanzi": "衬衫",
  "pinyin": "chèn shān",
  "definition": "shirt",
  "hsk_level": 3,
  "date": "2026-05-12",
  "example_cn": "我喜欢这件衬衫。",
  "example_en": "I like this shirt.",
  "example_source": "Claude Code (OAuth)"
}
```

| Field            | Always present | Notes                                                   |
|------------------|----------------|---------------------------------------------------------|
| `hanzi`          | yes            | Simplified Chinese.                                     |
| `pinyin`         | yes            | With tone marks.                                        |
| `definition`     | yes            | English gloss from the HSK list.                        |
| `hsk_level`      | yes            | 1–6.                                                    |
| `date`           | yes            | ISO date in Europe/London used to pick the word.        |
| `example_cn`     | best-effort    | Example sentence in Chinese, level-appropriate.         |
| `example_en`     | best-effort    | Natural English translation of the example.             |
| `example_source` | best-effort    | `Claude Code (OAuth)`.                                  |

Example fields are absent if `CLAUDE_CODE_OAUTH_TOKEN` is unset or the
Claude Code Action step errors — the workflow continues and commits
whatever `today.json` it has.

## TRMNL setup

Point a TRMNL plugin at the raw URL of `today.json`:

```
https://raw.githubusercontent.com/fraserbrookhouse/MandarinWOTD/main/today.json
```

GitHub serves `raw.githubusercontent.com` with a short cache TTL, which is fine
since the file only changes once per day.

## How the word is chosen

`tools/build_wotd.py`:

1. Downloads HSK 1–6 CSVs from
   [`plaktos/hsk_csv`](https://github.com/plaktos/hsk_csv) and stamps each row
   with its HSK level (parsed from the filename).
2. Takes today's date in Europe/London, SHA-256s the ISO string, takes the
   first 4 bytes as a `uint32`, and indexes modulo the combined corpus. Same
   date → same word, every time.
3. Writes the base `today.json` (no example fields yet).

A second workflow step then runs
[`anthropics/claude-code-base-action@beta`](https://github.com/anthropics/claude-code-base-action),
authenticated with a `CLAUDE_CODE_OAUTH_TOKEN` so usage bills against the
repo owner's Claude Pro/Max subscription rather than a separately-billed
API key. Claude reads `today.json`, generates one HSK-appropriate example
sentence using the chosen word, and edits the file to add `example_cn`,
`example_en`, and `example_source` in place. The existing commit step
then pushes the populated file.

## Schedule

`.github/workflows/main.yml` runs daily at `00:05 UTC` (00:05 GMT in winter,
01:05 BST in summer) and on `workflow_dispatch`. It commits the new
`today.json` back to `main`, so the raw URL above always reflects the latest
build. Because the word is keyed off the Europe/London date inside the script,
a single UTC cron is enough — no DST gymnastics needed.

## Required secret

Add `CLAUDE_CODE_OAUTH_TOKEN` under **Settings → Secrets and variables →
Actions**. Generate it locally with:

```bash
claude setup-token
```

(Requires Claude Pro or Max — see
[the Claude Code Action setup docs](https://github.com/anthropics/claude-code-action/blob/main/docs/setup.md).)
Daily generation usage bills against your subscription quota, not a
separate API account.

If the secret is missing, the workflow still succeeds — the example
generation step is set to `continue-on-error: true`, so `today.json`
just ships without the `example_*` fields.

## Run it locally

```bash
HSK_URLS="https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk1.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk2.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk3.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk4.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk5.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk6.csv" \
python3 tools/build_wotd.py

cat today.json
```

This produces the base file with `hanzi`, `pinyin`, `definition`,
`hsk_level`, and `date` — the example fields are added by the Claude Code
Action step in CI. To populate them locally, use the Claude Code CLI
yourself, e.g.:

```bash
claude --print "Read ./today.json, add example_cn, example_en, and \
example_source='Claude Code (OAuth)' fields with one HSK-appropriate \
example sentence using the hanzi, then write the file back."
```

Requires Python 3.9+ (for `zoneinfo`). The Python script itself has no
third-party dependencies — example generation lives in the Claude Code
Action, not in `build_wotd.py`.

## Attribution

- HSK vocabulary lists: [plaktos/hsk_csv](https://github.com/plaktos/hsk_csv).
- Example sentences: generated by
  [Claude Code](https://github.com/anthropics/claude-code-action) at
  workflow run time.

## License

MIT — see [`LICENSE`](LICENSE).
