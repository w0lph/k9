"""Download the prebuilt database (from the Hugging Face Hub by default).

The published file is a plain SQLite database, so no Hub client library is needed: a
streaming GET that follows the Hub's CDN redirect, written atomically next to its final
location so an interrupted download never leaves a half file behind.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from pathlib import Path

import httpx

from .paths import DB_URL, USER_AGENT

log = logging.getLogger(__name__)

SQLITE_MAGIC = b"SQLite format 3\x00"


def _client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(60.0, read=600.0),
        headers={"User-Agent": USER_AGENT},
    )


def download_file(url: str, dest: Path, *, client: httpx.Client | None = None, chunk_size: int = 1 << 20) -> int:
    """Stream ``url`` into ``dest`` (temp file in the same directory, then rename).

    Returns the number of bytes written. Raises ``httpx.HTTPStatusError`` on a non-2xx
    response and ``RuntimeError`` on an empty body; in both cases nothing is left on disk.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    client = client or _client()
    fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".part", dir=dest.parent)
    tmp = Path(tmp_name)
    written = 0
    try:
        with os.fdopen(fd, "wb") as fh, client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            next_report = 0
            for chunk in resp.iter_bytes(chunk_size):
                fh.write(chunk)
                written += len(chunk)
                if total and written >= next_report:
                    log.info("downloading %s: %d/%d MB", dest.name, written >> 20, total >> 20)
                    next_report += 50 << 20
        if written == 0:
            raise RuntimeError(f"empty download from {url}")
        os.replace(tmp, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    finally:
        if own_client:
            client.close()
    return written


def ensure_db(db_path: Path, url: str = DB_URL, *, force: bool = False, client: httpx.Client | None = None) -> Path:
    """Make sure the database exists at ``db_path``, downloading it from ``url`` if not.

    The downloaded file must start with the SQLite header; anything else (an HTML error
    page, a Hub "repository not found" body) is deleted and reported.
    """
    if db_path.exists() and not force:
        return db_path
    log.warning("database not found at %s; downloading from %s", db_path, url)
    n = download_file(url, db_path, client=client)
    with db_path.open("rb") as fh:
        head = fh.read(len(SQLITE_MAGIC))
    if head != SQLITE_MAGIC:
        db_path.unlink()
        raise RuntimeError(f"{url} did not return a SQLite database ({n} bytes, header {head!r})")
    log.warning("downloaded %s (%d MB)", db_path, n >> 20)
    return db_path
