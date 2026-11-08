"""Weekend bulletin, written by code only: it can say nothing that is not in the database or in a headline.

Parts: the signals of the last session, the news of the last three days by topic with the notable headlines word for
word, and "watch points" built from fixed sentences (a symbol with both news and a signal, a topic with weight). No
model, no price direction, no advice (every line also passes pipeline.banned).
"""
import re
from collections import Counter

from pipeline.banned import _norm, find_banned

# (key, label, weight, keywords): the same list as app/lib/news/rank.dart; tests keep the two equal.
RULES = (
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
WATCH_MIN_WEIGHT = 0.8  # topics at or above this weight get a watch line of their own
MAX_SYMBOLS = 5
MAX_HEADLINES = 5
MAX_WATCH = 8
DISCLAIMER = "Tham khảo, không phải khuyến nghị đầu tư."
_WORD = re.compile(r"[a-z0-9&]+")


def classify(text):
    """The first rule whose keyword is a whole word or phrase of the text; the last rule ('other') when none is."""
    padded = " " + " ".join(_WORD.findall(_norm(text))) + " "
    for rule in RULES:
        if any(f" {k} " in padded for k in rule[3]):
            return rule
    return RULES[-1]


def _signals_line(ranked):
    if not ranked:
        return "Phiên gần nhất: chưa ghi nhận mã nào có dấu hiệu dòng tiền lớn."  # true whether none fired or no data yet
    top = ", ".join(f"{i['symbol']} (mức {i['level']})" for i in ranked[:MAX_SYMBOLS])
    return f"Phiên gần nhất: {len(ranked)} mã có dấu hiệu dòng tiền lớn. Mạnh nhất: {top}."


def _topics_line(tagged):
    if not tagged:
        return "Tin 3 ngày qua: chưa đọc được tin nào."
    counts = Counter(rule[0] for rule, _ in tagged)
    parts = ", ".join(f"{r[1]} ({counts[r[0]]})" for r in RULES if counts[r[0]])
    return f"Tin 3 ngày qua: {len(tagged)} tin. Theo chủ đề: {parts}."


def _notable(tagged):
    ranked = sorted((t for t in tagged if t[0][0] != "other"), key=lambda t: t[1]["published"] or "", reverse=True)
    ranked.sort(key=lambda t: -t[0][2])  # stable: newest first within the same weight
    return [f"- [{rule[1]}] {h['title']} ({h['source']})" for rule, h in ranked[:MAX_HEADLINES]]


def _watch_lines(ranked, tagged):
    lines = []
    for item in ranked:
        hits = [rule for rule, h in tagged if item["symbol"] in h["symbols"] and rule[0] != "other"]
        if hits:
            best = max(hits, key=lambda r: r[2])
            lines.append(f"- {item['symbol']}: có tin về {best[1].lower()} và có dấu hiệu dòng tiền mức {item['level']} ở phiên gần nhất.")
    counts = Counter(rule[0] for rule, _ in tagged)
    for r in RULES:
        if r[2] >= WATCH_MIN_WEIGHT and counts[r[0]]:
            lines.append(f"- Có {counts[r[0]]} tin về {r[1].lower()}: xem các mã được nhắc tên khi thị trường mở cửa lại.")
    return lines[:MAX_WATCH] or ["- Chưa có điểm đặc biệt từ tin và tín hiệu của phiên gần nhất."]


def build(items, headlines):
    """Paragraphs for the weekend digest. `items`: [{"symbol", "level", ...}] of the last session; `headlines`: news dicts."""
    ranked = sorted(items, key=lambda i: (-i["level"], i["symbol"]))
    tagged = [(classify(f"{h['title']} {h.get('summary', '')}"), h) for h in headlines if not find_banned(h["title"])]
    lines = [_signals_line(ranked), _topics_line(tagged), *_notable(tagged),
             "Điểm cần theo dõi khi thị trường mở cửa lại:", *_watch_lines(ranked, tagged), DISCLAIMER]
    return [line for line in lines if not find_banned(line)]
