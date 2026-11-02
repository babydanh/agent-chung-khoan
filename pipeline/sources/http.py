"""JSON over HTTP with retries (urllib only). Waits 2, 4 and 8 seconds between the four attempts."""
import json
import urllib.error
import urllib.request
import zlib

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
DELAYS = (2, 4, 8)
MAX_BYTES = 20_000_000  # a full KBS board is a few hundred KB; anything near this is wrong
ERROR_BODY_BYTES = 200


class SourceError(Exception):
    """A data source could not deliver usable data. `status` is the HTTP status when there was one."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def request_json(url, payload=None, headers=None, retries=3, sleep=None, timeout=30, method=None, text=False,
                 max_bytes=MAX_BYTES):
    """POST payload as JSON (GET when payload is None) and return the decoded body (None when it is empty)."""
    import time
    sleep = sleep or time.sleep
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"User-Agent": UA, "Accept-Encoding": "gzip", **(headers or {})}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    last, status = None, None
    for attempt in range(retries + 1):
        if attempt:
            sleep(DELAYS[min(attempt - 1, len(DELAYS) - 1)])
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method or ("POST" if data is not None else "GET"))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise SourceError(f"response is larger than {max_bytes} bytes")
            if raw[:2] == b"\x1f\x8b":
                raw = zlib.decompressobj(zlib.MAX_WBITS | 16).decompress(raw, max_bytes + 1)
                if len(raw) > max_bytes:
                    raise SourceError(f"decompressed response is larger than {max_bytes} bytes")
            if text:
                return raw.decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            snippet = e.read(ERROR_BODY_BYTES).decode("utf-8", errors="replace").strip()
            status = e.code
            last = f"HTTPError: HTTP Error {e.code}: {e.reason}" + (f" - {snippet}" if snippet else "")
            e.close()
            if e.code < 500 and e.code != 429:
                break  # a client error will not fix itself
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            status, last = None, f"{type(e).__name__}: {e}"
    raise SourceError(last, status=status)
