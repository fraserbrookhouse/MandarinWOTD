import csv, io, os, json, hashlib, datetime, zoneinfo, urllib.request, urllib.parse

# 1) Load and combine HSK lists
rows = []
for url in os.environ["HSK_URLS"].split():
    with urllib.request.urlopen(url) as r:
        data = r.read().decode("utf-8")
    reader = csv.reader(io.StringIO(data))
    for hanzi, pinyin, english in reader:
        hanzi, pinyin, english = hanzi.strip(), pinyin.strip(), english.strip()
        if hanzi and pinyin and english:
            rows.append({"hanzi": hanzi, "pinyin": pinyin, "definition": english})

if not rows:
    raise SystemExit("No HSK rows loaded.")

# 2) Choose deterministic “word of the day”
today = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/London")).date()
idx = int.from_bytes(hashlib.sha256(today.isoformat().encode()).digest()[:4], "big") % len(rows)
entry = rows[idx]

# 3) Try to fetch Chinese + English example from Tatoeba
def fetch_example(word: str):
    base = "https://tatoeba.org/eng/api_v0/search"
    params = {
        "from": "cmn",
        "to": "cmn",
        "query": word,
        "sort": "relevance",
        "trans_filter": "limit",
        "trans_link": "direct",
        "trans_to": "eng",
        "page": 1,
    }
    url = base + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.load(r)
    except Exception:
        return None

    items = (
        data.get("results", {}).get("sentences")
        or data.get("Sentences", {}).get("items")
        or []
    )
    for s in items:
        cn = s.get("text") or s.get("sentence") or ""
        if not cn:
            continue
        trans = s.get("translations") or s.get("Translations") or []
        for t in trans:
            lang = (t.get("lang") or t.get("language") or "")
            if lang.startswith("eng"):
                en = t.get("text") or t.get("sentence") or ""
                if en:
                    return {"example_cn": cn, "example_en": en}
    return None

ex = fetch_example(entry["hanzi"])
if ex:
    entry.update(ex)

# 4) Write today.json
with open("today.json", "w", encoding="utf-8") as f:
    json.dump(entry, f, ensure_ascii=False, indent=2)

print("Built today.json:", entry)
