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

def _is_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))

def _looks_like_sentence_cn(word: str, cn: str) -> bool:
    if not _is_cjk(cn): 
        return False
    cn = cn.strip()
    if cn == word: 
        return False
    # Length should exceed the word by at least 2 chars
    if len(cn) < max(len(word) + 2, 4):
        return False
    # Encourage sentence punctuation or spacing
    if not re.search(r"[，。？！、；：,.?!]", cn) and " " not in cn:
        # still allow if reasonably long (e.g., phrases)
        if len(cn) < 6:
            return False
    return True

def _looks_like_sentence_en(en: str) -> bool:
    en = (en or "").strip()
    # avoid one-word glosses
    return len(en) >= 8

def _score_pair(word: str, cn: str, en: str) -> float:
    # Heuristic: length balance + punctuation bonus + word position variety
    score = 0.0
    Lc = len(cn)
    Le = len(en)
    score += min(Lc, 40) / 40.0
    score += min(Le, 60) / 60.0
    if re.search(r"[，。？！、；：,.?!]", cn):
        score += 0.3
    # prefer if word is inside, not only at edges
    if 0 < cn.find(word) < len(cn) - len(word):
        score += 0.2
    return score

# ---------------- TATOEBA ----------------
def fetch_example(word: str):
    base = "https://tatoeba.org/eng/api_v0/search"
    params = {
        "from": "cmn", "to": "cmn", "query": word,
        "sort": "relevance", "trans_filter": "limit",
        "trans_link": "direct", "trans_to": "eng", "page": 1,
    }
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MandarinWOTD/1.0 (+github-actions)"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.load(r)
    except Exception as e:
        log(f"Tatoeba lookup failed: {e}")
        return None

    # normalize -> items
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for path in (("results","sentences"), ("Sentences","items"), ("items",), ("data",)):
            cur, ok = data, True
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    ok = False; break
            if ok and isinstance(cur, list):
                items = cur; break

    best = None
    best_score = -1.0

    for s in items:
        if not isinstance(s, dict): 
            continue
        cn = s.get("text") or s.get("sentence") or ""
        if not _looks_like_sentence_cn(word, cn):
            continue

        trans = s.get("translations") or s.get("Translations") or []
        # flatten translations
        flat = []
        if isinstance(trans, dict):
            for v in trans.values():
                if isinstance(v, list): flat.extend(v)
                elif isinstance(v, dict): flat.append(v)
        elif isinstance(trans, list):
            flat = trans

        for t in flat:
            if not isinstance(t, dict): 
                continue
            lang = (t.get("lang") or t.get("language") or "")
            if not str(lang).startswith("eng"):
                continue
            en = t.get("text") or t.get("sentence") or ""
            if not _looks_like_sentence_en(en):
                continue
            sc = _score_pair(word, cn, en)
            if sc > best_score:
                best_score, best = sc, {"example_cn": cn.strip(), "example_en": en.strip(), "example_source": "Tatoeba"}

    return best

# ---------------- MYMEMORY (fallback) ----------------
def fetch_example_mymemory(word: str):
    base = "https://api.mymemory.translated.net/get"
    params = {"q": word, "langpair": "zh-CN|en-GB", "de": "bot@example.com"}
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MandarinWOTD/1.0 (+github-actions)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
    except Exception as e:
        log(f"MyMemory lookup failed: {e}")
        return None

    matches = data.get("matches") or []
    if not isinstance(matches, list):
        return None

    best = None
    best_score = -1.0

    for m in matches:
        cn = (m.get("segment") or "").strip()
        en = (m.get("translation") or "").strip()
        if not (_looks_like_sentence_cn(word, cn) and _looks_like_sentence_en(en)):
            continue
        sc = _score_pair(word, cn, en)
        # small bonus if they say it's human
        created_by = (m.get("created-by") or m.get("createdby") or "").upper()
        mt = (m.get("machine-translation") or m.get("mt") or False)
        if created_by and created_by != "MT" and not mt:
            sc += 0.1
        if sc > best_score:
            best_score, best = sc, {"example_cn": cn, "example_en": en, "example_source": "MyMemory"}

    return best


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
