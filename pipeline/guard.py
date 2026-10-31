"""Checks on model-written bulletin text. The model may only write words and {PLACEHOLDERS}; every number
and name is filled in by code afterwards, so a paragraph with its own figures, links, tickers or advice is dropped.

The checks run on a normalised copy (NFKC, invisible characters removed, one space between words) so that
full-width forms, zero-width characters and odd spaces cannot hide a word."""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from pipeline.banned import find_banned

MAX_LEN = 300
ROOT = Path(__file__).resolve().parent.parent
_PLACEHOLDER = re.compile(r"\{([A-Z]+[0-9]*)\}")
_NUMERIC_VAR = r"(?:LVL\d+|COUNT|TIME)"
_ADJACENT_NUMERIC = re.compile(r"\{" + _NUMERIC_VAR + r"\}[^\w{]*\{" + _NUMERIC_VAR + r"\}")
# A numeric variable must come right after its fixed label word.
_LABELS = (("LVL", {"mức"}), ("COUNT", {"có"}), ("TIME", {"lúc", "tin"}))
_PERCENT_SIGNS = set("%\uff05\u066a\ufe6a\u2030\u2031")
_TOKEN = re.compile(r"[^\W\d_]+")
_PUNCTUATION = set(",.;:!?-\u2013\u2014\u2026()\"'\u201c\u201d\u2018\u2019")
_UNITS = re.compile(r"\b(percent)\b")
# Number words with their accents (checked on the accented text) ...
_VI_WORDS = frozenset("không một mốt hai ba bốn năm sáu bảy tám chín mười mươi chục trăm nghìn ngàn triệu tỷ tỉ nửa rưỡi lần".split())
# ... and without accents (checked on the accent-free text). "sau", "nam", "tam", "bay" stay out: everyday words.
_VI_PLAIN = frozenset("khong mot hai ba bon chin muoi chuc tram nghin ngan trieu ty ti nua ruoi".split())
_EN_WORDS = frozenset(("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                       "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
                       "hundred thousand million billion trillion double doubled triple tripled twice thrice half "
                       "halved dozen percent").split())
_LINK = re.compile(r"https?:|www\.|\w\.\w|[/@\\]", re.I)
ALLOWED_CAPS = frozenset({"VN", "US"})


@lru_cache(maxsize=1)
def known_symbols():
    """Every ticker in config/symbols.json, upper case."""
    with open(ROOT / "config" / "symbols.json", encoding="utf-8") as f:
        data = json.load(f)
    return frozenset(s.upper() for syms in data.values() for s in syms)


def _normalise(text):
    t = unicodedata.normalize("NFKC", text)
    t = "".join(c for c in t if unicodedata.category(c) != "Cf")  # zero-width, soft hyphen, BOM, joiners
    return re.sub(r"\s+", " ", t)


def _plain(text):
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) not in ("Mn", "Cf"))
    return text.replace("đ", "d")


def _labelled(text):
    """Every numeric variable follows its label word; none sits next to another."""
    if _ADJACENT_NUMERIC.search(text):
        return False
    for m in re.finditer(r"\{(" + _NUMERIC_VAR + r")\}", text):
        found = re.search(r"([^\W\d_]+)\W*$", text[:m.start()])
        kind = next(k for k, _ in _LABELS if m.group(1).startswith(k))
        if not found or found.group(1).lower() not in dict(_LABELS)[kind]:
            return False
    return True


def check_paragraph(text, allowed, valid_ids, news_ids=(), symbols=None):
    """(ok, reason)."""
    if not isinstance(text, str) or not text.strip():
        return False, "empty"
    if len(text) > MAX_LEN:
        return False, "too long"
    norm = _normalise(text)
    if any(n not in allowed for n in _PLACEHOLDER.findall(norm)):
        return False, "unknown placeholder"
    if not _labelled(norm):
        return False, "numeric variable without its label"
    bare = _PLACEHOLDER.sub(" ", norm)
    if "{" in bare or "}" in bare:
        return False, "malformed placeholder"
    if any(c.isnumeric() for c in bare):  # digits of any script, CJK numerals, fractions
        return False, "digit outside placeholder"
    if _PERCENT_SIGNS & set(bare):
        return False, "number word or unit"
    if _LINK.search(bare):
        return False, "link"
    for c in bare:
        if c.isalpha():
            if "LATIN" not in unicodedata.name(c, ""):
                return False, "letter outside Latin script"
        elif not (c.isspace() or c in _PUNCTUATION):
            return False, "character outside the allowed set"
    lower = bare.lower()
    if set(_TOKEN.findall(lower)) & _VI_WORDS:
        return False, "number word or unit"
    plain = _plain(bare)
    if set(_TOKEN.findall(plain)) & (_VI_PLAIN | _EN_WORDS):
        return False, "number word or unit"
    known = known_symbols() if symbols is None else frozenset(s.upper() for s in symbols)
    for tok in _TOKEN.findall(bare):
        if tok.upper() in known or (tok.isupper() and 2 <= len(tok) <= 5 and tok not in ALLOWED_CAPS):
            return False, "ticker outside placeholder"
    if find_banned(bare):
        return False, "banned wording"
    if any(i not in valid_ids for i in news_ids):
        return False, "unknown news id"
    return True, ""


def render(text, table):
    return _PLACEHOLDER.sub(lambda m: str(table[m.group(1)]), text)


def clean(paragraphs, table, valid_ids, symbols=None):
    """Keep paragraphs that pass; return (rendered paragraphs, reasons for the dropped ones)."""
    good, dropped = [], []
    for p in paragraphs:
        if not isinstance(p, dict):
            dropped.append("not an object")
            continue
        refs = p.get("news_ids", [])
        if refs is None:
            refs = []
        if not isinstance(refs, (list, tuple)) or not all(isinstance(i, str) for i in refs):
            dropped.append("news_ids is not a list of strings")
            continue
        ok, why = check_paragraph(p.get("text"), set(table), valid_ids, refs, symbols)
        if ok:
            rendered = render(p["text"], table)
            if find_banned(rendered):
                ok, why = False, "banned wording after fill-in"
        if ok:
            good.append({"text": rendered, "news_ids": list(refs)})
        else:
            dropped.append(why)
    return good, dropped
