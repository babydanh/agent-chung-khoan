"""RSS headlines: title, link, source, time and a short plain-text summary. Nothing else is kept."""
import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import timezone

log = logging.getLogger("pipeline.news")

FEEDS = {
    "CafeF": "https://cafef.vn/thi-truong-chung-khoan.rss",
    "Vietstock": "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
    "VnExpress Kinh doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
}
SUMMARY_MAX = 200
# Three-letter words that read like tickers but are not (a real ticker "CEO" exists; it is skipped on purpose).
NOT_SYMBOLS = frozenset({"USD", "GDP", "CEO", "CFO", "CPI", "PMI", "IPO", "ETF", "VND", "EUR", "FED", "OPEC",
                         "EPS", "ROE", "ROA", "FDI", "WTO", "IMF", "NHNN", "TTCK", "UBCK", "AI", "OTC", "ESG"})
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
_BLOCK = re.compile(r"</?(br|p|div|li|ul|ol|h\d|tr|td|table)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]*>")
_TICKER = re.compile(r"(?<!\w)[A-Z]{3}(?!\w)")


def strip_html(text):
    text = _TAG.sub("", _BLOCK.sub(" ", _SCRIPT.sub(" ", text or "")))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def summarize(text, limit=SUMMARY_MAX):
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def extract_symbols(text, known):
    """Tickers from `known` that appear as whole upper-case words; common acronyms never count."""
    return sorted({t for t in _TICKER.findall(text) if t in known and t not in NOT_SYMBOLS})


def _published(raw):
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_rss(xml_text, source, known):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = strip_html(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        summary = summarize(strip_html(item.findtext("description")))
        out.append({"id": hashlib.sha1(link.encode()).hexdigest()[:10], "title": title, "link": link,
                    "source": source, "published": _published(item.findtext("pubDate")), "summary": summary,
                    "symbols": extract_symbols(title + " " + summary, known)})
    return out


def fetch_all(feeds, known, get_text):
    """Read every feed; one that fails is logged and skipped. Newest first, no duplicate links."""
    seen, items = set(), []
    for source, url in feeds.items():
        try:
            parsed = parse_rss(get_text(url), source, known)
        except Exception as e:  # a broken feed must not stop the others
            log.warning("feed %s failed: %s", source, e)
            continue
        for it in parsed:
            if it["link"] not in seen:
                seen.add(it["link"])
                items.append(it)
    return sorted(items, key=lambda i: i["published"] or "", reverse=True)
