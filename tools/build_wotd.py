import csv, io, os, json, hashlib, datetime, zoneinfo, urllib.request, urllib.parse, sys

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
    print("ERROR: No HSK rows loaded.", file=sys.stderr)
    # Write a minimal JSON so the workflow still succeeds
    with open("today.json", "w", encoding="utf-8") as f:
        json.dump({"hanzi": "学习", "pinyin": "xuéxí", "definition": "to study; to learn"}, f, ensure_ascii=False, indent=2)
    sys.exit(0)

# 2) Choose deterministic “word of the day” (Europe/London)
today = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/London")).date()
idx = int.from_bytes(hashlib.sha256(today.isoformat().encode()).digest()[:4], "big") % len(rows)
entry = rows[idx]

# 3) Try to fetch Chinese + English example from Tatoeba — SHAPE-AGNOSTIC
def fetch_example(word: str):
    base = "https://tatoeba.org/eng/api_v0/search"
    params = {
        "from": "cmn",          # Mandarin Chinese sentences
        "to": "cmn",            # same language (we want Chinese sentences)
        "query": word,          # search term
        "sort": "relevance",
        "trans_filter": "limit",
        "trans_link": "direct", # only directly linked translations
        "trans_to": "eng",      # ask for English translations
        "page": 1,
    }
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MandarinWOTD/1.0 (+github-actions)"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.load(r)
    except Exception as e:
        print(f"Example lookup failed: {e}", file=sys.stderr)
        return None

    # --- Normalize the response into a list of sentence items ---
    items = []
    if isinstance(data, list):
        # Some responses are just a list of sentence items
        items = data
    elif isinstance(data, dict):
        # Try several known shapes
        for path in (
            ("results", "sentences"),
            ("Sentences", "items"),
            ("items",),
            ("data",),  # just in case
        ):
            cur = data
            ok = True
            for key in path:
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    ok = False
                    break
            if ok and isinstance(cur, list):
                items = cur
                break

    if not isinstance(items, list):
        return None

    # --- Pick the first item that has an English translation ---
    for s in items:
        if not isinstance(s, dict):
            continue
        cn = s.get("text") or s.get("sentence") or ""
        if not cn:
            continue

        trans = s.get("translations") or s.get("Translations") or []
        # Normalize translations into a flat list of dicts
        flat = []
        if isinstance(trans, dict):
            for v in trans.values():
                if isinstance(v, list):
                    flat.extend(v)
                elif isinstance(v, dict):
                    flat.append(v)
        elif isinstance(trans, list):
            flat = trans

        for t in flat:
            if not isinstance(t, dict):
                continue
            lang = (t.get("lang") or t.get("language") or "")
            if str(lang).startswith("eng"):
                en = t.get("text") or t.get("sentence") or ""
                if en:
                    return {"example_cn": cn, "example_en": en}

    return None

# 4) Don’t let example lookup failures kill the build
try:
    ex = fetch_example(entry["hanzi"])
    if ex:
        entry.update(ex)
except Exception as e:
    print(f"Non-fatal example error: {e}", file=sys.stderr)

# 5) Write today.json
with open("today.json", "w", encoding="utf-8") as f:
    json.dump(entry, f, ensure_ascii=False, indent=2)

print("Built today.json:", entry)
