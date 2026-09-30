"""Client for the Animal Drugs @ FDA public search API.

The site is an AngularJS app; these are the JSON endpoints it calls (read from its own
``searchResultService.js`` and ``foiDrugSummariesService.js``). No authentication.

* ``POST /advancedSearch`` — flat JSON body (not a nested ``paging`` object), paged.
* ``GET  /foiDrugSummaries/foiApplicationNumbers`` — application-number ranges that partition
  the FOI summary catalogue.
* ``GET  /foiDrugSummaries/foiApplicationsInfo/{start}/{end}/`` — FOI documents in a range.
* ``GET  /retrievePreviewBean/{applicationId}`` — application detail incl. documents.
* ``GET  /document/downloadFoi/{foiId}`` — the FOI summary PDF.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

BASE = "https://animaldrugsatfda.fda.gov/adafda/app/search/public"
USER_AGENT = "foi-summaries/0.1 (research tooling; public-domain FDA documents)"

log = logging.getLogger(__name__)


def _blank_criteria() -> dict[str, Any]:
    return {
        "basicSearchTerm": None,
        "applicationNumber": None,
        "sponsorName": None,
        "activeIngredientName": None,
        "applicationStatusCode": None,
        "applicationStatusValue": None,
        "indication": None,
        "proprietaryName": None,
        "doseFormName": None,
        "routeName": None,
        "speciesName": None,
        "isExact": False,
        "sortField": "applicationNumber",
        "sortDirection": "false",
        "pageSize": None,
        "pageNumber": None,
    }


class ADAFDAClient:
    def __init__(self, base_url: str = BASE, timeout: float = 60.0, max_attempts: int = 4,
                 min_interval: float = 0.25, transport: httpx.BaseTransport | None = None):
        self._c = httpx.Client(base_url=base_url, timeout=timeout, transport=transport,
                               headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        self._max_attempts = max_attempts
        self._min_interval = min_interval
        self._last = 0.0

    def close(self) -> None:
        self._c.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        last: Exception | None = None
        for i in range(self._max_attempts):
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                self._last = time.monotonic()
                r = self._c.request(method, path, **kw)
            except httpx.TransportError as exc:
                last = exc
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    last = httpx.HTTPStatusError(f"HTTP {r.status_code} {path}", request=r.request, response=r)
                else:
                    return r
            if i < self._max_attempts - 1:
                time.sleep(2.0 * (i + 1))
        assert last is not None
        raise last

    # -- search -------------------------------------------------------------------------

    def advanced_search(self, page: int = 1, page_size: int = 100, **criteria) -> dict:
        body = _blank_criteria() | criteria | {"pageSize": page_size, "pageNumber": page}
        r = self._request("POST", "/advancedSearch", json=body, headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()

    def iter_applications(self, page_size: int = 100, max_pages: int = 200, **criteria) -> Iterator[dict]:
        """Yield application rows for the criteria, following pages until one comes back empty.

        The response's paging metadata is unreliable (``last`` is always true, ``totalPages``
        always 1, ``number``/``size`` always 0) but ``pageNumber`` is honoured, so the only
        trustworthy stop signals are an empty page or a page with nothing new.
        """
        seen: set[Any] = set()
        for page in range(1, max_pages + 1):
            data = self.advanced_search(page=page, page_size=page_size, **criteria)
            rows = data.get("content") or []
            if not rows:
                return
            new = 0
            for row in rows:
                key = row.get("applicationId") or row.get("applicationNumber")
                if key in seen:
                    continue
                seen.add(key)
                new += 1
                yield row
            if new == 0:
                return

    # -- FOI catalogue -------------------------------------------------------------------

    def foi_ranges(self) -> list[dict]:
        r = self._request("GET", "/foiDrugSummaries/foiApplicationNumbers")
        r.raise_for_status()
        return r.json()

    def foi_info(self, start: str, end: str) -> list[dict]:
        r = self._request("GET", f"/foiDrugSummaries/foiApplicationsInfo/{start}/{end}/")
        r.raise_for_status()
        return r.json()

    def iter_foi_documents(self) -> Iterator[dict]:
        for rng in self.foi_ranges():
            yield from self.foi_info(rng["foiApplicationNumStart"], rng["foiApplicationNumEnd"])

    # -- detail + documents --------------------------------------------------------------

    def preview_bean(self, application_id: int) -> dict:
        r = self._request("GET", f"/retrievePreviewBean/{application_id}")
        r.raise_for_status()
        return r.json()

    def download_foi(self, foi_id: int) -> tuple[int, bytes, str]:
        r = self._request("GET", f"/document/downloadFoi/{foi_id}", headers={"Accept": "*/*"})
        return r.status_code, r.content, r.headers.get("content-type", "")
