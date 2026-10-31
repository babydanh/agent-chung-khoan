"""Scanner for wording that reads as investment advice. Used on app strings and AI-written text.

Text is lower-cased and stripped of accents and invisible characters first, so one pattern covers
"Nên mua", "nen mua" and "n<zero-width>ên mua". Stripping accents can also flag innocent text
(for example "bạn ngày" reads as "ban ngay"); a false alarm only drops one sentence.
"""
import re
import unicodedata

# Disclaimers the app must show next to every signal; they contain a banned word on purpose.
ALLOWED_PHRASES = (
    "không phải khuyến nghị đầu tư",
    "không phải tư vấn đầu tư, khuyến nghị mua/bán hay lời mời giao dịch",
)

_PATTERNS = [re.compile(p) for p in (
    r"\bnen\s+(mua|ban|giu|gom|chot loi|cat lo|bat day|nam giu)\b",
    r"khuyen\s*nghi",
    r"khuyen cao\s+(mua|ban|nam giu)",
    r"\b(mua|ban)\s+ngay\b",
    r"chac\s*chan",
    r"cam\s*ket",
    r"dam bao loi nhuan",
    r"loi nhuan dam bao",
    r"chac an",
    r"ma vang",
    r"sieu co phieu",
    r"ca map",
    r"sap\s+(keo|tang manh|bay)",
    r"\b(diem|vung|tin hieu)\s+(mua|ban)\b",
    r"gia muc tieu",
    r"tat tay",
    r"\ball\s*in\b",
    r"phim hang",
    # advice in headlines; "khoi ngoai mua vao / ban ra" (plain flow reporting) must stay allowed.
    # "dang mua" also catches "đang mua" once accents are gone: a rare false alarm, one headline dropped.
    r"\bdang\s+(mua|ban)\b",
    r"\bnen\b(\s+\w+){0,3}\s+(mua vao|ban ra)\b",
    r"\bse\s+(tang|giam)\b",
    r"\bgap\s+(doi|ba)\b",
    # direct calls to act, vi and en (accents are gone by the time these run)
    r"\bhay\s+(mua|ban)\b",
    r"\bnen\s+can\s+nhac\s+(mua|ban)\b",
    r"\bnen\s+(xuong\s+tien|giai\s+ngan|chot\s+loi|cat\s+lo|gom|canh\s+mua|canh\s+ban)\b",
    r"\bco\s+hoi\s+(mua|ban)\b",
    r"\bgood\s+time\s+to\s+(buy|sell)\b",
    r"\bconsider\s+(buying|selling)\b",
    r"\btime\s+to\s+(buy|sell)\b",
    # forecasts of direction
    r"\b(du\s+kien|ky\s+vong|nhieu\s+kha\s+nang|co\s+the)\s+(se\s+)?(tang|giam)\b",
    r"\b(should|strong)\s+(buy|sell)\b",
    r"price target",
    r"\brecommend",
    r"\bguarantee",
)]


def _norm(text):
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) not in ("Mn", "Cf"))
    return re.sub(r"\s+", " ", text.replace("đ", "d"))


_ALLOWED = tuple(_norm(p) for p in ALLOWED_PHRASES)


def find_banned(text):
    """Return the patterns that match; an empty list means the text is clean."""
    text = _norm(text)
    for phrase in _ALLOWED:
        text = text.replace(phrase, " ")
    return [p.pattern for p in _PATTERNS if p.search(text)]
