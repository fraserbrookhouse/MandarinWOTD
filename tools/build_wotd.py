import csv, io, os, json, hashlib, datetime, re, zoneinfo, urllib.request, urllib.parse, sys

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

def fetch_example_mymemory(word: str):
    """
    Fallback: use MyMemory Translation Memory to get a CN sentence with an EN translation.
    Prefers human translations and high match scores.
    Docs: https://mymemory.translated.net/doc/spec.php
    """
    base = "https://api.mymemory.translated.net/get"
    # Ask for Chinese->English; q must be urlencoded
    params = {
        "q": word,
        "langpair": "zh-CN|en-GB",   # or en-US if you prefer
        "de": "bot@example.com",     # contact email per API etiquette (optional but nice)
    }
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MandarinWOTD/1.0 (+github-actions)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
    except Exception:
        return None

    # MyMemory returns { responseData: {...}, matches: [ ... ] }
    matches = data.get("matches") or []
    if not isinstance(matches, list):
        return None

    # Heuristics:
    # - Chinese side contains the exact word
    # - Prefer non-machine (if possible): created-by != "MT"
    # - Prefer higher "quality"/"match" score
    def is_chinese(s):  # quick check for any CJK char
        return bool(re.search(r"[\u4e00-\u9fff]", s or ""))

    scored = []
    for m in matches:
        src = (m.get("segment") or "").strip()
        tgt = (m.get("translation") or "").strip()
        created_by = (m.get("created-by") or m.get("createdby") or "").upper()
        mt = (m.get("machine-translation") or m.get("mt") or False)
        match_score = float(m.get("match", 0))  # 0..1
        quality = float(m.get("quality", 0))    # 0..100

        # MyMemory sometimes flips direction; ensure src is Chinese and contains the word
        if not (is_chinese(src) and word in src):
            continue
        if not tgt:
            continue

        # Score: prefer human and high quality/match
        human_bonus = 0.1 if (created_by and created_by != "MT" and not mt) else 0.0
        score = match_score + (quality / 100.0) * 0.5 + human_bonus
        scored.append((score, src, tgt, created_by))

    if not scored:
        return None

    scored.sort(reverse=True)
    _, cn, en, created_by = scored[0]
    # Light cleanup (trim multiple spaces and odd punctuation)
    cn = re.sub(r"\s+", " ", cn).strip()
    en = re.sub(r"\s+", " ", en).strip()
    return {"example_cn": cn, "example_en": en, "example_source": "MyMemory"}

# 4) Don’t let example lookup failures kill the build
try:
    ex = fetch_example(entry["hanzi"])
    if not ex:
        ex = fetch_example_mymemory(entry["hanzi"])
    if ex:
        entry.update(ex)
except Exception as e:
    print(f"Non-fatal example error: {e}", file=sys.stderr)

# 5) Write today.json
with open("today.json", "w", encoding="utf-8") as f:
    json.dump(entry, f, ensure_ascii=False, indent=2)

print("Built today.json:", entry)
