"""The installed server must work from the published database alone: full text and FOI
section text come out of SQLite, the data directory resolves outside site-packages, and the
first-run download is atomic and validated."""

from __future__ import annotations

import json

import httpx
import pytest
from test_foi_table import FOI_ROW

from dog_geroscience_mcp import paths, queries
from dog_geroscience_mcp.build import build_db
from dog_geroscience_mcp.data_fetch import SQLITE_MAGIC, download_file, ensure_db
from dog_geroscience_mcp.foi_store import FoiStore


def test_fulltext_is_stored_in_db_and_filtered_by_licence(raw_dir, corpus_dir, tmp_path):
    db_all = tmp_path / "all.sqlite"
    s = build_db(raw_dir, corpus_dir, db_all)
    assert s["corpus"] == s["corpus"] | {"with_fulltext_md": 1, "fulltext_on_disk": 1, "fulltext_licences": "all"}
    conn = queries.connect(db_all)
    # no corpus directory at all: the text still comes back, from the table
    ft = queries.corpus_fulltext(conn, tmp_path / "nowhere", "PMC0000001", max_chars=25)
    assert ft["chars"] > 25 and ft["truncated"] is True and ft["markdown"].startswith("---\npmcid")
    assert queries.corpus_record(conn, "PMC0000001")["has_fulltext_md"] is True
    conn.close()

    db_cc0 = tmp_path / "cc0.sqlite"
    s = build_db(raw_dir, corpus_dir, db_cc0, fulltext_licences={"CC0 "})  # normalised
    assert s["corpus"]["with_fulltext_md"] == 0 and s["corpus"]["fulltext_licences"] == ["cc0"]
    conn = queries.connect(db_cc0)
    assert queries.corpus_fulltext(conn, None, "PMC0000001") is None
    assert queries.corpus_record(conn, "PMC0000001")["has_fulltext_md"] is False
    # the disk fallback still serves a source checkout
    assert queries.corpus_fulltext(conn, corpus_dir, "PMC0000001")["chars"] > 0
    conn.close()


def test_foi_store_falls_back_to_the_database(raw_dir, corpus_dir, tmp_path):
    foi = tmp_path / "foi_summaries_dog.jsonl"
    row = FOI_ROW | {"parsed": FOI_ROW["parsed"] | {"sections": {"target_animal_safety": "Dogs received 1X, 3X and 5X."}}}
    foi.write_text(json.dumps(row) + "\n", encoding="utf-8")
    db = tmp_path / "db.sqlite"
    build_db(raw_dir, corpus_dir, db, foi_path=foi)

    store = FoiStore(tmp_path / "missing.jsonl", db_path=db)
    assert store.available
    rec = store.get(555, sections=["target_animal_safety"])
    assert rec["sections"] == {"target_animal_safety": "Dogs received 1X, 3X and 5X."}
    assert rec["general_information"]["recommended_dosage"] == "0.5 mg/kg once daily"
    assert FoiStore(tmp_path / "missing.jsonl", db_path=tmp_path / "no.sqlite").available is False


def test_default_data_dir_resolution(monkeypatch, tmp_path):
    assert paths.default_data_dir({}, source_checkout=True) == paths.PROJECT_ROOT / "data"
    assert paths.default_data_dir({"DOG_GERO_DATA": str(tmp_path)}, source_checkout=True) == tmp_path
    cache = paths.default_data_dir({}, source_checkout=False)
    assert cache.name == "dog-geroscience-mcp" and "site-packages" not in str(cache)
    assert paths.IS_SOURCE_CHECKOUT is True  # tests run from the checkout
    assert paths.DB_URL.endswith("/dog_geroscience.sqlite") and "huggingface.co/datasets/" in paths.DB_URL


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_ensure_db_downloads_atomically_and_validates(tmp_path):
    body = SQLITE_MAGIC + b"\x00" * 200

    def ok(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/resolve/main/dog_geroscience.sqlite"):
            return httpx.Response(302, headers={"location": "https://cdn.example/blob"})
        return httpx.Response(200, content=body, headers={"content-length": str(len(body))})

    dest = tmp_path / "cache" / "dog_geroscience.sqlite"
    with _client(ok) as c:
        out = ensure_db(dest, "https://huggingface.co/datasets/x/y/resolve/main/dog_geroscience.sqlite", client=c)
    assert out == dest and dest.read_bytes() == body
    assert [p.name for p in dest.parent.iterdir()] == ["dog_geroscience.sqlite"]  # no .part left behind

    # present: no request is made unless forced
    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unexpected request")

    with _client(boom) as c:
        assert ensure_db(dest, "https://example/x", client=c) == dest
    with _client(ok) as c:
        assert ensure_db(dest, "https://cdn.example/blob", force=True, client=c) == dest

    # a Hub error page is not a database: nothing is kept
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>Repository not found</html>")

    with _client(html) as c, pytest.raises(RuntimeError, match="did not return a SQLite database"):
        ensure_db(dest, "https://example/x", force=True, client=c)
    assert not dest.exists()

    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"nope")

    with _client(missing) as c, pytest.raises(httpx.HTTPStatusError):
        download_file("https://example/x", dest, client=c)
    assert list(dest.parent.iterdir()) == []


def test_serve_without_db_and_without_auto_fetch_is_explicit(tmp_path):
    from mcp import Client

    from dog_geroscience_mcp.server import create_server

    async def run():
        async with Client(create_server(tmp_path / "none.sqlite", tmp_path, auto_fetch=False)):
            pass

    import anyio

    with pytest.raises(BaseException) as exc:
        anyio.run(run)
    assert "fetch-data" in str(exc.value) or "fetch-data" in repr(exc.value.__cause__) or "fetch-data" in repr(getattr(exc.value, "exceptions", ""))
