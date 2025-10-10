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

# 2) Choose deterministic “word of the day” (Europe/London)
today = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/London")).date()
idx = int.from_bytes(hashlib.sha256(today.isoformat().encode()).digest()[:4], "big") % len(rows)
entry = rows[idx]

# 3) Try to fetch Chinese + English example from Tatoeba
def fetch_example(word: str):
    base = "https://tatoeba.org/eng/api_v0/search"
    params = {
        "from": "cmn",          # Mandarin Chinese
        "to": "cmn",            # sentence language (Chinese)
        "query": word,          # search term
        "sort": "relevance",
        "trans_filter": "limit",
        "trans_link": "direct", # only directly linked translations
        "trans_to": "eng",      # ask for English translations
        "page": 1,
    }
    url = base + "?" + urllib.parse.urlencode(params)

    # Friendly UA (some endpoints dislike default Python UA)
    req = urllib.request.Request(url, headers={"User-Agent": "MandarinWOTD/1.0 (+github-actions)"})

    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.load(r)
    except Exception:
        return None

    # Normalize to a list of sentence items, no matter the shape
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = (
            data.get("results", {}).get("sentences")
            or data.get("Sentences", {}).get("items")
            or data.get("items")
            or []
        )

    for s in items:
        cn = s.get("text") or s.get("sentence") or ""
        if not cn:
            continue
        trans = s.get("translations") or s.get("Translations") or []
        # Some shapes store translations as dicts or nested lists; flatten gently
        if isinstance(trans, dict):
            # e.g. {"eng":[{...}, {...}], "deu":[...]}
            flat = []
            for v in trans.values():
                if isinstance(v, list):
                    flat.extend(v)
                elif isinstance(v, dict):
                    flat.append(v)
            trans = flat
        elif not isinstance(trans, list):
            trans = [trans]

        for t in trans:
            if not isinstance(t, dict):
                continue
            lang = (t.get("lang") or t.get("language") or "")
            if str(lang).startswith("eng"):
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
