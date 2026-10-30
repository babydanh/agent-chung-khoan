"""Market data sources. fetch_vn tries KBS first and falls back to VCI."""
import logging

from pipeline.sources import kbs, vci
from pipeline.sources.http import SourceError

log = logging.getLogger("pipeline.sources")


def fetch_vn(symbols, kbs_url=kbs.URL, vci_url=vci.URL, **http):
    try:
        rows = kbs.fetch(symbols, url=kbs_url, **http)
        log.info("source=KBS rows=%d", len(rows))
        return rows
    except SourceError as e:
        log.warning("KBS failed (%s)", e)
    rows = vci.fetch(symbols, url=vci_url, **http)
    log.info("source=VCI rows=%d", len(rows))
    return rows
