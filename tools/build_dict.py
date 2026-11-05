#!/usr/bin/env python3
"""Wiktionary (kaikki.org / wiktextract) verisinden İngilizce -> Türkçe sözlük parçaları üretir.

Üç kaynak birleştirilir:
  --en      İngilizce Wiktionary'deki İngilizce kelimeler: sayfalardaki Türkçe çeviri tabloları
  --tr      İngilizce Wiktionary'deki Türkçe kelimeler: İngilizce açıklamaları ters çevrilir
            ("düşünmek: to think, to consider" -> consider: düşünmek)
  --trwikt  Türkçe Vikisözlük'teki İngilizce kelimeler: Türkçe tanımlar
Her dosya düz ya da .gz JSONL olabilir; olmayan kaynak atlanır.

Kullanım: python3 tools/build_dict.py ÇIKTI_KLASÖRÜ --en EN.jsonl.gz [--tr TR.jsonl.gz] [--trwikt TRW.jsonl.gz]

Çıktı: ÇIKTI_KLASÖRÜ/<iki harf>.json ve meta.json. Kayıt biçimi:
  {"i": "/ɹʌn/", "m": [["verb", [["ipucu", ["türkçe", ...]], ...]], ...], "f": ["kök"]}
Sözlük içeriği: Wiktionary, CC BY-SA 4.0.
"""
import argparse
import datetime
import gzip
import io
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--en", required=True)
ap.add_argument("--tr")
ap.add_argument("--trwikt")
ap.add_argument("--sources", default="")
ap.add_argument("--show", default="", help="sonunda örnek olarak yazdırılacak kelimeler, virgülle")
args = ap.parse_args()

SKIP_POS = {
    "name", "character", "symbol", "suffix", "prefix", "affix", "infix", "interfix",
    "circumfix", "punct", "romanization", "combining_form", "root",
}
POS_ORDER = [
    "verb", "noun", "adj", "adv", "phrase", "prep_phrase", "prep", "pron", "conj",
    "det", "article", "intj", "num", "particle", "contraction", "abbrev", "proverb",
]
BAD_FORM_TAGS = {"table-tags", "inflection-template", "class", "romanization", "canonical", "auxiliary"}
MAX_SENSES = 40
MAX_WORDS = 10
FORM_GLOSS = re.compile(
    r"^(plural|inflection|alternative|obsolete|archaic|misspelling|nonstandard|dated|eye dialect|"
    r"definite|indefinite|accusative|genitive|dative|locative|ablative|nominative|instrumental|"
    r"first|second|third|imperative|past|present|future|conditional|comparative|superlative|"
    r"abbreviation|initialism|contraction|clipping|diminutive|form)\b.*\bof\b",
    re.I,
)
STOP = {"something", "someone", "somebody", "one", "etc", "thing", "things", "oneself", "it", "be", "do", "make", "get"}


def opener(path):
    if not path or not os.path.exists(path):
        return None
    raw = gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace")


def records(path, must=None):
    fh = opener(path)
    if fh is None:
        return
    with fh:
        for line in fh:
            if must and not any(m in line for m in must):
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def is_tr(t):
    return isinstance(t, dict) and ((t.get("lang_code") or t.get("code")) == "tr" or t.get("lang") == "Turkish")


def shard_of(key):
    n = "".join(c for c in unicodedata.normalize("NFD", key) if unicodedata.category(c) != "Mn").lower()
    pick = lambda c: c if "a" <= c <= "z" else "_"
    return pick(n[0] if n else "_") + pick(n[1] if len(n) > 1 else "_")


def pick_ipa(sounds):
    first = None
    for s in sounds or []:
        ipa = s.get("ipa") if isinstance(s, dict) else None
        if not ipa:
            continue
        first = first or ipa
        if set(s.get("tags") or []) & {"US", "General-American"}:
            return ipa
    return first


def clean(s, n):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def split_outside(text):
    """Virgül ve noktalı virgülden böler, parantez içindekilere dokunmaz."""
    out, cur, depth = [], "", 0
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in ",;" and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [x.strip(" .") for x in out if x.strip(" .")]


def is_form_sense(s):
    if s.get("form_of") or s.get("alt_of"):
        return True
    if set(s.get("tags") or []) & {"form-of", "alt-of", "misspelling"}:
        return True
    return bool(FORM_GLOSS.match(" ".join(s.get("glosses") or [])))


entries = {}               # anahtar -> {"i": ipa, "m": {pos: {ipucu: [türkçe]}}}
forms = defaultdict(set)   # çekimli hal -> kök anahtarları
stats = {}


def add(key, pos, hint, words, ipa=None):
    ent = entries.setdefault(key, {"i": None, "m": {}})
    if ipa and not ent["i"]:
        ent["i"] = ipa
    groups = ent["m"].setdefault(pos, {})
    if hint not in groups and len(groups) >= MAX_SENSES:
        return False
    lst = groups.setdefault(hint, [])
    added = False
    for w in words:
        if w and w not in lst and len(lst) < MAX_WORDS:
            lst.append(w)
            added = True
    return added


# ---------------------------------------------------------------- 1) İngilizce kelimeler
ipas = {}
n = 0
for e in records(args.en):
    if e.get("lang_code") != "en" and e.get("lang") != "English":
        continue
    word = clean(e.get("word"), 80)
    if not word:
        continue
    key = word.lower()
    pos = e.get("pos") or ""
    if key not in ipas:
        ipa = pick_ipa(e.get("sounds"))
        if ipa:
            ipas[key] = ipa
    for s in e.get("senses") or []:
        for fo in (s.get("form_of") or []) + (s.get("alt_of") or []):
            base = clean(fo.get("word") if isinstance(fo, dict) else "", 80).lower()
            if base and base != key:
                forms[key].add(base)
    if pos in SKIP_POS:
        continue
    for f in e.get("forms") or []:
        fw = clean(f.get("form") if isinstance(f, dict) else "", 80)
        if not fw or set(f.get("tags") or []) & BAD_FORM_TAGS:
            continue
        if " " in fw and " " not in key:
            continue
        if fw.lower() != key:
            forms[fw.lower()].add(key)
    trs = [t for t in (e.get("translations") or []) if is_tr(t)]
    for s in e.get("senses") or []:
        hint = "; ".join(s.get("glosses") or [])
        for t in s.get("translations") or []:
            if is_tr(t):
                t = dict(t)
                t.setdefault("sense", hint)
                trs.append(t)
    for t in trs:
        tw = clean(t.get("word"), 60)
        if not tw or tw.startswith(("Thesaurus:", "Wikisaurus:")):
            continue
        if add(key, pos, clean(t.get("sense"), 110), [tw], ipas.get(key)):
            n += 1
stats["en_çeviri"] = n
stats["en_kelime"] = len(entries)

# ---------------------------------------------------------------- 2) Türkçe Vikisözlük: İngilizce kelimelerin Türkçe tanımları
n = 0
for e in records(args.trwikt, must=['"en"', "İngilizce"]):
    if e.get("lang_code") != "en" and e.get("lang") not in ("İngilizce", "English"):
        continue
    key = clean(e.get("word"), 80).lower()
    pos = e.get("pos") or ""
    if not key or pos in SKIP_POS:
        continue
    for s in e.get("senses") or []:
        if is_form_sense(s):
            continue
        g = clean("; ".join(s.get("glosses") or []), 160)
        g = re.sub(r"^\(.*?\)\s*", "", g).strip(" .")
        if not g:
            continue
        # Kısa tanımlar ("düşünmek, göz önünde tutmak") kelimelere bölünür, uzunlar tek parça kalır
        parts = split_outside(g) if len(g) <= 60 else [g]
        if add(key, pos, "", [p for p in parts if p][:6], ipas.get(key)):
            n += 1
stats["trvikisözlük"] = n

# ---------------------------------------------------------------- 3) Türkçe kelimelerin İngilizce açıklamalarını ters çevir
n = 0
for e in records(args.tr):
    if e.get("lang_code") != "tr" and e.get("lang") != "Turkish":
        continue
    tw = clean(e.get("word"), 60)
    pos = e.get("pos") or ""
    if not tw or pos in SKIP_POS:
        continue
    for s in e.get("senses") or []:
        if is_form_sense(s):
            continue
        gloss = clean("; ".join(s.get("glosses") or []), 200)
        if not gloss:
            continue
        hint = clean(re.sub(r"^\d+[.)]\s*", "", gloss), 110)
        bare = re.sub(r"\([^)]*\)|\[[^\]]*\]|[\"“”]", "", gloss)
        cands = []
        for piece in re.split(r"[;,]", bare):
            p = piece.strip().lower().rstrip(".!?:")
            if pos == "verb":
                p = re.sub(r"^to\s+", "", p)
            p = re.sub(r"^(a|an|the)\s+", "", p)
            if re.fullmatch(r"[a-z][a-z'\-]*(?: [a-z][a-z'\-]*){0,2}", p) and p not in STOP:
                cands.append(p)
        for c in cands[:3]:
            if add(c, pos, hint, [tw], ipas.get(c)):
                n += 1
stats["ters_çeviri"] = n

if len(entries) < int(os.environ.get("MIN_ENTRIES", "1000")):
    sys.exit(f"Çok az kayıt çıktı ({len(entries)}), veri biçimi beklenenden farklı olabilir: {stats}")

# ---------------------------------------------------------------- yaz
out = defaultdict(dict)
for key, ent in entries.items():
    m = []
    for pos in sorted(ent["m"], key=lambda p: POS_ORDER.index(p) if p in POS_ORDER else len(POS_ORDER)):
        senses = [[hint, words] for hint, words in ent["m"][pos].items() if words]
        if senses:
            m.append([pos, senses])
    if not m:
        continue
    rec = {"m": m}
    ipa = ent["i"] or ipas.get(key)
    if ipa:
        rec["i"] = ipa
    out[shard_of(key)][key] = rec

n_forms = 0
for form, bases in forms.items():
    bases = sorted(b for b in bases if b in entries and b != form)
    if not bases:
        continue
    out[shard_of(form)].setdefault(form, {})["f"] = bases[:4]
    n_forms += 1

os.makedirs(args.out, exist_ok=True)
for name in os.listdir(args.out):
    if name.endswith(".json"):
        os.remove(os.path.join(args.out, name))
for sh, data in out.items():
    with open(os.path.join(args.out, sh + ".json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
meta = {
    "words": sum(1 for e in entries.values() if e["m"]),
    "forms": n_forms,
    "shards": len(out),
    "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    "sources": args.sources,
    "stats": stats,
    "license": "Wiktionary / Vikisözlük, CC BY-SA 4.0 (kaikki.org / wiktextract)",
}
with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as fh:
    json.dump(meta, fh, ensure_ascii=False, indent=1)
print(json.dumps(meta, ensure_ascii=False))
for w in [x.strip().lower() for x in args.show.split(",") if x.strip()]:
    print("ÖRNEK", w, json.dumps(out[shard_of(w)].get(w), ensure_ascii=False)[:400])
