#!/usr/bin/env python3
"""Wiktionary (kaikki.org / wiktextract) verisinden İngilizce -> Türkçe sözlük parçaları üretir.

Kullanım:  <wiktextract JSONL> | python3 tools/build_dict.py ÇIKTI_KLASÖRÜ [KAYNAK_ADRESİ]

Çıktı: ÇIKTI_KLASÖRÜ/<iki harf>.json dosyaları ve meta.json
Her kayıt (anahtar küçük harf kelime ya da kalıp):
  {"i": "/ɹʌn/",                                   telaffuz (varsa)
   "m": [["verb", [["to move swiftly", ["koşmak"]], ...]], ...],   türüne göre anlamlar
   "f": ["run"]}                                    çekimli halse sözlükteki kök(ler)i
Sözlük içeriği: Wiktionary, CC BY-SA 4.0.
"""
import datetime
import io
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

OUT = sys.argv[1]
SOURCE = sys.argv[2] if len(sys.argv) > 2 else ""

SKIP_POS = {
    "name", "character", "symbol", "suffix", "prefix", "affix", "infix", "interfix",
    "circumfix", "punct", "romanization", "combining_form", "root",
}
POS_ORDER = [
    "verb", "noun", "adj", "adv", "phrase", "prep_phrase", "prep", "pron", "conj",
    "det", "article", "intj", "num", "particle", "contraction", "abbrev", "proverb",
]
BAD_FORM_TAGS = {"table-tags", "inflection-template", "class", "romanization", "canonical", "auxiliary"}
MAX_SENSES = 30
MAX_WORDS = 10


def is_tr(t):
    return isinstance(t, dict) and (
        (t.get("lang_code") or t.get("code")) == "tr" or t.get("lang") == "Turkish"
    )


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


entries = {}                 # anahtar -> {"i": ipa, "m": {pos: {anlam ipucu: [türkçe]}}}
form_of = defaultdict(set)   # çekimli hal -> kök anahtarları
lines = loaded = 0

stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
for line in stdin:
    lines += 1
    # Hızlı ön eleme: Türkçe çevirisi ya da "şunun çekimi" bilgisi olmayan satırları hiç çözme
    if '"Turkish"' not in line and '"tr"' not in line and "form_of" not in line and "alt_of" not in line:
        continue
    try:
        e = json.loads(line)
    except ValueError:
        continue
    if e.get("lang_code") != "en" and e.get("lang") != "English":
        continue
    loaded += 1
    word = clean(e.get("word"), 80)
    if not word:
        continue
    key = word.lower()
    pos = e.get("pos") or ""

    for s in e.get("senses") or []:
        for fo in (s.get("form_of") or []) + (s.get("alt_of") or []):
            base = clean(fo.get("word") if isinstance(fo, dict) else "", 80).lower()
            if base and base != key:
                form_of[key].add(base)

    if pos in SKIP_POS:
        continue
    trs = [t for t in (e.get("translations") or []) if is_tr(t)]
    for s in e.get("senses") or []:
        hint = "; ".join(s.get("glosses") or [])
        for t in s.get("translations") or []:
            if is_tr(t):
                t = dict(t)
                t.setdefault("sense", hint)
                trs.append(t)
    if not trs:
        continue

    ent = entries.setdefault(key, {"i": None, "m": {}})
    ent["i"] = ent["i"] or pick_ipa(e.get("sounds"))
    groups = ent["m"].setdefault(pos, {})
    for t in trs:
        tw = clean(t.get("word"), 60)
        if not tw or tw.startswith(("Thesaurus:", "Wikisaurus:")):
            continue
        hint = clean(t.get("sense"), 110)
        lst = groups.setdefault(hint, [])
        if tw not in lst and len(lst) < MAX_WORDS:
            lst.append(tw)

    for f in e.get("forms") or []:
        fw = clean(f.get("form") if isinstance(f, dict) else "", 80)
        if not fw or set(f.get("tags") or []) & BAD_FORM_TAGS:
            continue
        if " " in fw and " " not in key:  # "more beautiful" gibi çok kelimeli çekimler
            continue
        fl = fw.lower()
        if fl != key:
            form_of[fl].add(key)

if len(entries) < int(os.environ.get("MIN_ENTRIES", "1000")):
    sys.exit(f"Çok az kayıt çıktı ({len(entries)}), veri biçimi beklenenden farklı olabilir. Satır: {lines}, çözülen: {loaded}")

out = defaultdict(dict)
for key, ent in entries.items():
    m = []
    for pos in sorted(ent["m"], key=lambda p: POS_ORDER.index(p) if p in POS_ORDER else len(POS_ORDER)):
        senses = [[hint, words] for hint, words in ent["m"][pos].items() if words][:MAX_SENSES]
        if senses:
            m.append([pos, senses])
    if not m:
        continue
    rec = {"m": m}
    if ent["i"]:
        rec["i"] = ent["i"]
    out[shard_of(key)][key] = rec

n_forms = 0
for form, bases in form_of.items():
    bases = sorted(b for b in bases if b in entries and b != form)
    if not bases:
        continue
    sh = out[shard_of(form)]
    rec = sh.setdefault(form, {})
    rec["f"] = bases[:4]
    n_forms += 1

os.makedirs(OUT, exist_ok=True)
for name in os.listdir(OUT):
    if name.endswith(".json"):
        os.remove(os.path.join(OUT, name))
for sh, data in out.items():
    with open(os.path.join(OUT, sh + ".json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
meta = {
    "words": len(entries),
    "forms": n_forms,
    "shards": len(out),
    "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    "source": SOURCE,
    "license": "Wiktionary, CC BY-SA 4.0 (kaikki.org / wiktextract)",
}
with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as fh:
    json.dump(meta, fh, ensure_ascii=False, indent=1)
print(json.dumps(meta, ensure_ascii=False), f"satır={lines} çözülen={loaded}")
