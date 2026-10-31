"""Checks on model-written bulletin text. The model may only write words and {PLACEHOLDERS}; every number
and name is filled in by code afterwards, so a paragraph with its own figures, links or advice is dropped."""
import re
import unicodedata

from pipeline.banned import find_banned

MAX_LEN = 300
_PLACEHOLDER = re.compile(r"\{([A-Z]+[0-9]*)\}")
_UNITS = re.compile(r"\b(ty|trieu|nghin|ngan|phan tram|percent)\b")
_PERCENT_SIGNS = set("%\uff05\u066a\ufe6a\u2030\u2031")
# Number words (one..nine, ten, tens, hundred, thousand, million, billion, half, times) with their accents ...
_WORDS = frozenset("một mốt hai ba bốn năm sáu bảy tám chín mười mươi chục trăm nghìn ngàn triệu tỷ tỉ nửa rưỡi lần".split())
# ... and the forms typed without accents. "sau", "nam", "tam", "bay" are left out: they are everyday words.
_WORDS_PLAIN = frozenset("mot hai ba bon chin muoi chuc tram nghin ngan trieu ty ti nua ruoi".split())
_TOKEN = re.compile(r"[^\W\d_]+")
_BARE_TICKER = re.compile(r"(?<!\w)[A-Z]{3,5}(?!\w)")
_LINK = re.compile(r"https?:|www\.|\.(com|vn|net|org)\b", re.I)


def _normalise(text):
    """NFKC (full-width digits and percent signs, odd spaces) and one single space between words."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text))


def _plain(text):
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) not in ("Mn", "Cf"))
    return text.replace("đ", "d")


def check_paragraph(text, allowed, valid_ids, news_ids=()):
    """(ok, reason)."""
    if not isinstance(text, str) or not text.strip():
        return False, "empty"
    if len(text) > MAX_LEN:
        return False, "too long"
    names = _PLACEHOLDER.findall(text)
    if any(n not in allowed for n in names):
        return False, "unknown placeholder"
    bare = _normalise(_PLACEHOLDER.sub(" ", text))
    if "{" in bare or "}" in bare:
        return False, "malformed placeholder"
    if any(c.isdigit() for c in bare):
        return False, "digit outside placeholder"
    if _PERCENT_SIGNS & set(bare) or _UNITS.search(_plain(bare)):
        return False, "number word or unit"
    words = set(_TOKEN.findall(bare.lower()))
    if words & _WORDS or words & _WORDS_PLAIN:
        return False, "number word or unit"
    if _BARE_TICKER.search(bare):
        return False, "ticker outside placeholder"
    if _LINK.search(bare):
        return False, "link"
    if find_banned(bare):
        return False, "banned wording"
    if any(i not in valid_ids for i in news_ids):
        return False, "unknown news id"
    return True, ""


def render(text, table):
    return _PLACEHOLDER.sub(lambda m: str(table[m.group(1)]), text)


def clean(paragraphs, table, valid_ids):
    """Keep paragraphs that pass; return (rendered paragraphs, reasons for the dropped ones)."""
    good, dropped = [], []
    for p in paragraphs:
        if not isinstance(p, dict):
            dropped.append("not an object")
            continue
        refs = p.get("news_ids") or []
        ok, why = check_paragraph(p.get("text"), set(table), valid_ids, refs)
        if ok:
            rendered = render(p["text"], table)
            if find_banned(rendered):
                ok, why = False, "banned wording after fill-in"
        if ok:
            good.append({"text": rendered, "news_ids": list(refs)})
        else:
            dropped.append(why)
    return good, dropped
