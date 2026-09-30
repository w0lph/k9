"""NCBI E-utilities as a second source of PMC full-text XML.

``efetch.fcgi?db=pmc&id=PMC1,PMC2,...&retmode=xml`` returns a ``<pmc-articleset>`` with one
``<article>`` per id. Open-access articles carry a ``<body>``; for the rest NCBI returns
front matter plus the comment "The publisher of this article does not allow downloading of
the full text in XML form", which we record as *not available* rather than saving a stub.

Rate limit: 3 requests/second without an API key (10 with ``NCBI_API_KEY``). Batching
100 ids per request keeps a 1,000-file backlog to about ten calls.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Iterator

import httpx
from lxml import etree

from .config import USER_AGENT

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
RESTRICTED_RE = re.compile(r"does not allow downloading of the full text", re.IGNORECASE)

log = logging.getLogger(__name__)


class NCBIClient:
    def __init__(self, timeout: float = 120.0, max_attempts: int = 5, transport: httpx.BaseTransport | None = None):
        self._c = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": USER_AGENT})
        self._max_attempts = max_attempts
        self._api_key = os.environ.get("NCBI_API_KEY")
        self._min_interval = 0.11 if self._api_key else 0.34
        self._last = 0.0

    def close(self) -> None:
        self._c.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _post(self, data: dict) -> httpx.Response:
        last: Exception | None = None
        for i in range(self._max_attempts):
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                self._last = time.monotonic()
                r = self._c.post(EFETCH, data=data)
            except httpx.TransportError as exc:
                last = exc
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    last = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                else:
                    return r
            if i < self._max_attempts - 1:
                time.sleep(2.0 * (i + 1))
        assert last is not None
        raise last

    def fetch_articles(self, pmcids: list[str]) -> Iterator[tuple[str, bytes | None, str]]:
        """Yield (pmcid, article_xml_bytes_or_None, status) for each requested id.

        status is ``ok`` (body present), ``front_only`` (no body, no restriction notice),
        ``restricted`` (publisher does not allow XML), or ``missing`` (not in the response).
        """
        data = {"db": "pmc", "retmode": "xml", "id": ",".join(pmcids)}
        if self._api_key:
            data["api_key"] = self._api_key
        r = self._post(data)
        r.raise_for_status()
        root = etree.fromstring(r.content, etree.XMLParser(recover=True, huge_tree=True))
        found: dict[str, tuple[bytes | None, str]] = {}
        if root is not None:
            for art in root.iter("article"):
                pmcid = _article_pmcid(art)
                if not pmcid:
                    continue
                restricted = any(RESTRICTED_RE.search(c.text or "") for c in art.iter(etree.Comment))
                has_body = art.find("body") is not None
                if has_body:
                    found[pmcid] = (etree.tostring(art, xml_declaration=True, encoding="UTF-8"), "ok")
                elif restricted:
                    found[pmcid] = (None, "restricted")
                else:
                    found[pmcid] = (etree.tostring(art, xml_declaration=True, encoding="UTF-8"), "front_only")
        for pmcid in pmcids:
            xml, status = found.get(pmcid, (None, "missing"))
            yield pmcid, xml, status


def _article_pmcid(art: etree._Element) -> str | None:
    for aid in art.iter("article-id"):
        kind = (aid.get("pub-id-type") or "").lower()
        if kind in ("pmc", "pmcid", "pmc-uid"):
            val = (aid.text or "").strip()
            if val:
                return val if val.upper().startswith("PMC") else f"PMC{val}"
    return None
