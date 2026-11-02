"""RSS headlines: title, link, source, time and a short plain-text summary. Nothing else is kept."""
import hashlib
from dataclasses import dataclass, field
import html
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone

log = logging.getLogger("pipeline.news")

FEEDS = {
    "CafeF": "https://cafef.vn/thi-truong-chung-khoan.rss",
    "Vietstock": "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
    "VnExpress Kinh doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
}
SUMMARY_MAX = 200
TITLE_MAX = 200
MAX_AGE = timedelta(days=3)
# Three-letter words that read like tickers but are not (a real ticker "CEO" exists; it is skipped on purpose).
NOT_SYMBOLS = frozenset({"USD", "GDP", "CEO", "CFO", "CPI", "PMI", "IPO", "ETF", "VND", "EUR", "FED", "OPEC",
                         "EPS", "ROE", "ROA", "FDI", "WTO", "IMF", "NHNN", "TTCK", "UBCK", "AI", "OTC", "ESG"})
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
_BLOCK = re.compile(r"</?(br|p|div|li|ul|ol|h\d|tr|td|table)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]*>")
_TICKER = re.compile(r"(?<!\w)[A-Z]{3}(?!\w)")


class NewsError(Exception):
    """A feed could not be read."""


def _strip_tags(text):
    return _TAG.sub("", _BLOCK.sub(" ", _SCRIPT.sub(" ", text)))


def strip_html(text):
    """Plain text: entities are decoded first (so escaped tags are seen), tags removed, then once more in case
    the removal itself joined a new tag together."""
    text = text or ""
    for _ in range(3):  # double-encoded markup
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = _strip_tags(_strip_tags(text))
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
    except ET.ParseError as e:
        raise NewsError(f"{source}: not valid XML ({e})") from e
    out = []
    for item in root.iter("item"):
        title = strip_html(item.findtext("title"))[:TITLE_MAX]
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith("https://"):  # no http:, javascript: or other schemes
            continue
        summary = summarize(strip_html(item.findtext("description")))
        out.append({"id": hashlib.sha1(link.encode()).hexdigest()[:10], "title": title, "link": link,
                    "source": source, "published": _published(item.findtext("pubDate")), "summary": summary,
                    "symbols": extract_symbols(title + " " + summary, known)})
    return out


@dataclass
class FetchResult:
    items: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)  # source -> error text
    empty: list = field(default_factory=list)   # sources that parsed but gave no usable headline


def fetch_all(feeds, known, get_text, now=None):
    """Read every feed. A feed that fails is logged with its traceback and listed in `failed`; if every feed fails
    NewsError is raised. Headlines older than three days are dropped (those without a date are kept); a source
    left with nothing is listed in `empty` and logged. Newest first, no duplicate links."""
    now = now or datetime.now(timezone.utc)
    oldest = (now - MAX_AGE).isoformat()
    result, seen = FetchResult(), set()
    for source, url in feeds.items():
        try:
            parsed = parse_rss(get_text(url), source, known)
        except Exception as e:  # a broken feed must not stop the others
            result.failed[source] = f"{type(e).__name__}: {e}"
            log.exception("feed %s failed", source)
            continue
        kept = 0
        for it in parsed:
            if it["link"] in seen or (it["published"] and it["published"] < oldest):
                continue
            seen.add(it["link"])
            result.items.append(it)
            kept += 1
        if not kept:
            result.empty.append(source)
            log.warning("feed %s parsed but returned no headlines", source)
    log.info("%d of %d feeds failed, %d headlines kept", len(result.failed), len(feeds), len(result.items))
    if feeds and len(result.failed) == len(feeds):
        log.error("no feed could be read")
        raise NewsError("no feed could be read: " + "; ".join(f"{k}: {v}" for k, v in result.failed.items()))
    result.items.sort(key=lambda i: i["published"] or "", reverse=True)
    return result
