"""Thin Europe PMC REST client with retries and cursor pagination.

Only two endpoints are used:

* ``/search`` with ``cursorMark`` pagination and ``resultType=core`` (abstract, MeSH,
  keywords, grants, full-text availability flags).
* ``/{PMCID}/fullTextXML`` for JATS full text, which Europe PMC serves for the
  open-access subset and for some author manuscripts.

Retries cover connection errors, 429 and 5xx (Europe PMC has been observed returning
503 for the whole API during maintenance windows).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Self

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .config import EUROPEPMC_BASE, USER_AGENT

log = logging.getLogger(__name__)


class TransientHTTPError(Exception):
    """Raised for responses worth retrying (429, 5xx)."""

    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} from {url}")
        self.status = status
        self.url = url


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, (TransientHTTPError, httpx.TransportError))


@dataclass
class SearchPage:
    cursor: str
    next_cursor: str | None
    hit_count: int
    results: list[dict]
    raw: dict


class EuropePMCClient:
    def __init__(
        self,
        base_url: str = EUROPEPMC_BASE,
        timeout: float = 60.0,
        max_attempts: int = 8,
        min_interval: float = 0.2,
        transport: httpx.BaseTransport | None = None,
    ):
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        contact = os.environ.get("CAC_CONTACT")
        if contact:
            headers["From"] = contact
        self._client = httpx.Client(
            base_url=base_url, timeout=timeout, headers=headers, transport=transport
        )
        self._max_attempts = max_attempts
        self._min_interval = min_interval
        self._last_call = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- low level -------------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _get(self, path: str, params: dict | None = None, accept: str | None = None) -> httpx.Response:
        @retry(
            retry=retry_if_exception(_is_transient),
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential_jitter(initial=1, max=60),
            reraise=True,
            before_sleep=lambda rs: log.warning(
                "retrying %s (attempt %d): %s", path, rs.attempt_number, rs.outcome.exception()
            ),
        )
        def _do() -> httpx.Response:
            self._throttle()
            headers = {"Accept": accept} if accept else None
            resp = self._client.get(path, params=params, headers=headers)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise TransientHTTPError(resp.status_code, str(resp.url))
            return resp

        return _do()

    # -- search ----------------------------------------------------------------------

    def search_page(self, query: str, cursor: str = "*", page_size: int = 200) -> SearchPage:
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": page_size,
            "cursorMark": cursor,
            "sort": "P_PDATE_D desc",
        }
        resp = self._get("/search", params=params)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("resultList", {}).get("result", []) or []
        return SearchPage(
            cursor=cursor,
            next_cursor=data.get("nextCursorMark"),
            hit_count=int(data.get("hitCount", 0)),
            results=results,
            raw=data,
        )

    def search_iter(self, query: str, page_size: int = 200) -> Iterator[SearchPage]:
        """Yield pages until Europe PMC stops advancing the cursor."""
        cursor = "*"
        seen: set[str] = set()
        while True:
            page = self.search_page(query, cursor=cursor, page_size=page_size)
            yield page
            nxt = page.next_cursor
            if not page.results or not nxt or nxt == cursor or nxt in seen:
                return
            seen.add(cursor)
            cursor = nxt

    # -- full text -------------------------------------------------------------------

    def fulltext_xml(self, pmcid: str) -> tuple[int, bytes]:
        """Return (status_code, body). 404 means no full text is served for this PMCID."""
        resp = self._get(f"/{pmcid}/fullTextXML", accept="application/xml")
        return resp.status_code, resp.content
