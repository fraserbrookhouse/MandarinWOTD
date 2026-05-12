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
  "example_source": "Claude Haiku 4.5"
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
| `example_source` | best-effort    | `Claude Haiku 4.5`.                                     |

Example fields are absent if `ANTHROPIC_API_KEY` is unset or the API errors —
the build never fails on this.

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
3. Asks **Claude Haiku 4.5** for one example sentence using the chosen word,
   prompted with the entry's HSK level so vocabulary and grammar stay readable
   for a learner studying that word. The API call uses structured output
   (`output_config.format` with a JSON schema), so the response is
   guaranteed-parseable JSON.
4. Writes `today.json`.

## Schedule

`.github/workflows/main.yml` runs daily at `00:05 UTC` (00:05 GMT in winter,
01:05 BST in summer) and on `workflow_dispatch`. It commits the new
`today.json` back to `main`, so the raw URL above always reflects the latest
build. Because the word is keyed off the Europe/London date inside the script,
a single UTC cron is enough — no DST gymnastics needed.

## Required secret

Add `ANTHROPIC_API_KEY` under **Settings → Secrets and variables → Actions**.
The workflow passes it to `tools/build_wotd.py` for the example-sentence call.
If the secret is missing, the build still succeeds — `today.json` just ships
without the `example_*` fields.

## Run it locally

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...   # optional; skipped gracefully if unset
HSK_URLS="https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk1.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk2.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk3.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk4.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk5.csv \
https://raw.githubusercontent.com/plaktos/hsk_csv/master/hsk6.csv" \
python3 tools/build_wotd.py

cat today.json
```

Requires Python 3.9+ (for `zoneinfo`) and the `anthropic` SDK
(`pip install anthropic`). Set `ANTHROPIC_API_KEY` in your environment to
generate example sentences locally; without it, the script still produces
`today.json` with everything except the `example_*` fields.

## Attribution

- HSK vocabulary lists: [plaktos/hsk_csv](https://github.com/plaktos/hsk_csv).
- Example sentences: [Claude Haiku 4.5](https://www.anthropic.com/) via the
  Anthropic API.

## License

MIT — see [`LICENSE`](LICENSE).
