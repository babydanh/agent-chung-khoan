"""Rank headlines without a model: classify the event by keywords, group the same story across sources, and score
how hot it is. Pure functions; every number the notification shows comes from here or from the signals."""
import hashlib
import re
import unicodedata
from datetime import datetime, timezone

# Keywords per event (accent-folded, whole words or phrases). Order matters: the first event with a matching
# keyword wins, so "lai suat" (macro) is checked before the earnings words.
_RULES = (
    ("macro", "Vĩ mô", 0.5, ("lai suat", "ty gia", "gdp", "cpi", "nhnn", "ngan hang nha nuoc", "fed", "trai phieu chinh phu")),
    ("legal", "Pháp lý", 1.0, ("thanh tra", "khoi to", "xu phat", "vi pham", "dinh chi", "dieu tra", "bat tam giam", "huy niem yet")),
    ("deal", "Thâu tóm, sáp nhập", 1.0, ("thau tom", "sap nhap", "mua lai doanh nghiep", "m&a", "chuyen nhuong von", "chao mua cong khai")),
    ("earnings", "Kết quả kinh doanh", 1.0, ("loi nhuan", "lai quy", "bao lai", "bao lo", "doanh thu", "ket qua kinh doanh")),
    ("dividend", "Cổ tức", 0.8, ("co tuc", "chia thuong", "co phieu thuong", "ngay giao dich khong huong quyen")),
    ("issuance", "Phát hành", 0.8, ("phat hanh them", "tang von", "chao ban", "phat hanh co phieu", "phat hanh trai phieu")),
    ("insider", "Giao dịch cổ đông lớn", 0.6, ("co dong lon", "giao dich noi bo", "nguoi noi bo", "dang ky giao dich", "lanh dao dang ky")),
    ("contract", "Hợp đồng, dự án", 0.6, ("hop dong", "du an", "ky ket", "trung thau")),
    ("liquidity", "Thanh khoản", 0.5, ("margin", "von ngoai", "etf", "thanh khoan", "khoi ngoai")),
    ("other", "Tin khác", 0.2, ()),
)
# (key, label shown in notifications, weight 0..1)
EVENTS = tuple((k, label, w) for k, label, w, _ in _RULES)
_BY_KEY = {k: (k, label, w) for k, label, w in EVENTS}
_KEYWORDS = [(k, kws) for k, _, _, kws in _RULES]

FRESH_FULL_MIN, FRESH_ZERO_MIN = 60, 12 * 60
UNKNOWN_FRESH = 0.3
SAME_STORY = 0.6
_WORD = re.compile(r"[a-z0-9&]+")


def fold(text):
    """Lower case without accents (đ becomes d), for matching."""
    s = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _padded(text):
    return " " + " ".join(_WORD.findall(fold(text))) + " "


def classify(text):
    """(key, label, weight) of the first event whose keyword appears as a whole phrase in `text`."""
    t = _padded(text)
    for key, kws in _KEYWORDS:
        if any(" " + k + " " in t for k in kws):
            return _BY_KEY[key]
    return _BY_KEY["other"]


def _tokens(title):
    return set(_WORD.findall(fold(title)))


def _similar(a, b):
    ta, tb = _tokens(a["title"]), _tokens(b["title"])
    if not ta or not tb or (a["symbols"] and b["symbols"] and set(a["symbols"]) != set(b["symbols"])):
        return False
    return len(ta & tb) / len(ta | tb) >= SAME_STORY


def cluster(items):
    """Group headlines that tell the same story. The newest headline of a group represents it; `sources` counts the
    distinct sources; `cluster` is a stable id (the same story gets the same id whatever the order)."""
    newest_first = sorted(items, key=lambda i: i["published"] or "", reverse=True)
    groups = []
    for it in newest_first:
        for g in groups:
            if _similar(g[0], it):
                g.append(it)
                break
        else:
            groups.append([it])
    out = []
    for g in groups:
        head = dict(g[0])
        head["sources"] = len({m["source"] for m in g})
        head["cluster"] = hashlib.sha1(min(m["link"] for m in g).encode()).hexdigest()[:10]
        out.append(head)
    return out


def _freshness(published, now):
    if not published:
        return UNKNOWN_FRESH
    age = (now - datetime.fromisoformat(published)).total_seconds() / 60
    if age <= FRESH_FULL_MIN:
        return 1.0
    if age >= FRESH_ZERO_MIN:
        return 0.0
    return 1 - (age - FRESH_FULL_MIN) / (FRESH_ZERO_MIN - FRESH_FULL_MIN)


def hot_score(story, now, watch, flows):
    """0..100: 30 freshness + 20 sources (3 or more is full) + 20 event weight + 15 watched + 15 money-flow match."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    syms = set(story.get("symbols") or ())
    score = (30 * _freshness(story.get("published"), now)
             + 20 * min(story.get("sources", 1), 3) / 3
             + 20 * _BY_KEY.get(story.get("event"), _BY_KEY["other"])[2]
             + (15 if syms & set(watch) else 0)
             + (15 if syms & set(flows) else 0))
    return int(round(score))
