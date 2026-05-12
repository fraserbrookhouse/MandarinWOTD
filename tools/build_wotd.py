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
    entry = {
        "hanzi": "学习",
        "pinyin": "xuéxí",
        "definition": "to study; to learn",
        "hsk_level": 1,
        "date": today.isoformat(),
    }
else:
    # 2) Choose deterministic "word of the day" (Europe/London)
    idx = int.from_bytes(hashlib.sha256(today.isoformat().encode()).digest()[:4], "big") % len(rows)
    entry = rows[idx]
    entry["date"] = today.isoformat()

# 3) Write the base today.json. The example sentence is added by the
#    Claude Code Action step in the workflow, which reads this file and
#    writes example_cn / example_en / example_source back into it.
with open("today.json", "w", encoding="utf-8") as f:
    json.dump(entry, f, ensure_ascii=False, indent=2)

log(f"Built today.json: {entry}")
