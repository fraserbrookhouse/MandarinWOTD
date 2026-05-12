import csv, io, os, json, hashlib, datetime, re, zoneinfo, urllib.request, sys

def log(msg):
    print(msg, file=sys.stderr)

# 1) Load and combine HSK lists. Each row keeps its HSK level (1-6), parsed
#    from the source URL — plaktos/hsk_csv exposes hskN.csv files.
rows = []
for url in os.environ["HSK_URLS"].split():
    m = re.search(r"hsk(\d+)\.csv", url)
    level = int(m.group(1)) if m else None
    with urllib.request.urlopen(url) as r:
        data = r.read().decode("utf-8")
    reader = csv.reader(io.StringIO(data))
    for hanzi, pinyin, english in reader:
        hanzi, pinyin, english = hanzi.strip(), pinyin.strip(), english.strip()
        if hanzi and pinyin and english:
            rows.append({"hanzi": hanzi, "pinyin": pinyin, "definition": english, "hsk_level": level})

today = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/London")).date()

if not rows:
    log("ERROR: No HSK rows loaded.")
    # Write a minimal JSON so the workflow still succeeds
    with open("today.json", "w", encoding="utf-8") as f:
        json.dump({
            "hanzi": "学习",
            "pinyin": "xuéxí",
            "definition": "to study; to learn",
            "hsk_level": 1,
            "date": today.isoformat(),
        }, f, ensure_ascii=False, indent=2)
    sys.exit(0)

# 2) Choose deterministic "word of the day" (Europe/London)
idx = int.from_bytes(hashlib.sha256(today.isoformat().encode()).digest()[:4], "big") % len(rows)
entry = rows[idx]
entry["date"] = today.isoformat()

# 3) Generate an example sentence with Claude Haiku 4.5. Uses structured
#    output so the response is guaranteed-parseable JSON. The build never
#    fails on example lookup — if the key is missing, the SDK is unavailable,
#    or the API errors, today.json just ships without example_cn/example_en.
def fetch_example_claude(word, pinyin, definition, hsk_level):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log("ANTHROPIC_API_KEY not set; skipping example generation.")
        return None
    try:
        import anthropic
    except ImportError as e:
        log(f"anthropic SDK unavailable: {e}")
        return None

    level_str = f"HSK {hsk_level}" if hsk_level else "an unspecified HSK level"
    user_prompt = (
        f'Write one example sentence for: {word} ({pinyin}) — "{definition}" ({level_str}).\n'
        f'The sentence MUST contain the exact word "{word}". '
        f"Vocabulary and grammar should sit at or below this HSK level so a "
        f"learner studying this word can read it. Keep the sentence short "
        f"(roughly 8–18 Chinese characters). The English translation should "
        f"be natural, not word-for-word."
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=(
            "You write example sentences for Mandarin learners. Given a "
            "Chinese word, return one natural-sounding Chinese sentence that "
            "uses the exact word, plus a faithful English translation. Keep "
            "vocabulary and grammar at or below the learner's HSK level."
        ),
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "example_cn": {"type": "string"},
                        "example_en": {"type": "string"},
                    },
                    "required": ["example_cn", "example_en"],
                    "additionalProperties": False,
                },
            }
        },
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        log("Claude response had no text block.")
        return None
    data = json.loads(text)
    return {
        "example_cn": data["example_cn"],
        "example_en": data["example_en"],
        "example_source": "Claude Haiku 4.5",
    }

try:
    ex = fetch_example_claude(entry["hanzi"], entry["pinyin"], entry["definition"], entry.get("hsk_level"))
    if ex:
        entry.update(ex)
except Exception as e:
    log(f"Non-fatal example error: {e}")

# 4) Write today.json
with open("today.json", "w", encoding="utf-8") as f:
    json.dump(entry, f, ensure_ascii=False, indent=2)

log(f"Built today.json: {entry}")
