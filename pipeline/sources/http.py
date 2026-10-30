"""JSON over HTTP with retries (urllib only). Waits 2, 4 and 8 seconds between the four attempts."""
import gzip
import json
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
DELAYS = (2, 4, 8)


class SourceError(Exception):
    """A data source could not deliver usable data."""


def request_json(url, payload=None, headers=None, retries=3, sleep=None, timeout=30, method=None):
    """POST payload as JSON (GET when payload is None) and return the decoded body (None when it is empty)."""
    import time
    sleep = sleep or time.sleep
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"User-Agent": UA, "Accept-Encoding": "gzip", **(headers or {})}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    last = None
    for attempt in range(retries + 1):
        if attempt:
            sleep(DELAYS[min(attempt - 1, len(DELAYS) - 1)])
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method or ("POST" if data is not None else "GET"))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500 and e.code != 429:
                break  # a client error will not fix itself
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = e
    raise SourceError(f"{type(last).__name__}: {last}")
