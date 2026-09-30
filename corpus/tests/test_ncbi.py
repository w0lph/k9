"""NCBI E-utilities fallback: batched fetch, restricted/front-only handling, provenance."""

import json

import httpx

from canine_aging_corpus.config import DataPaths
from canine_aging_corpus.ncbi import NCBIClient
from canine_aging_corpus.pipeline import convert_fulltext, fetch_fulltext_ncbi, read_sources
from canine_aging_corpus.records import write_jsonl

ARTICLESET = b"""<?xml version="1.0"?>
<pmc-articleset>
 <article article-type="research-article"><front><article-meta>
   <article-id pub-id-type="pmc">1111</article-id>
   <title-group><article-title>Open one</article-title></title-group></article-meta></front>
   <body><sec><title>Methods</title><p>We enrolled 17 dogs.</p></sec></body></article>
 <article article-type="research-article"><!--The publisher of this article does not allow downloading of the full text in XML form.-->
   <front><article-meta><article-id pub-id-type="pmc">2222</article-id>
   <title-group><article-title>Closed one</article-title></title-group></article-meta></front></article>
 <article article-type="abstract"><front><article-meta><article-id pub-id-type="pmcid">PMC3333</article-id>
   <title-group><article-title>Abstract only</article-title></title-group>
   <abstract><p>Just an abstract.</p></abstract></article-meta></front></article>
</pmc-articleset>"""


def _client(calls):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(dict(httpx.QueryParams(req.content.decode())))
        return httpx.Response(200, content=ARTICLESET, headers={"content-type": "text/xml"})
    c = NCBIClient(transport=httpx.MockTransport(handler))
    c._min_interval = 0
    return c


def test_fetch_articles_classifies_each_id():
    calls = []
    with _client(calls) as c:
        out = {p: (xml is not None, st) for p, xml, st in c.fetch_articles(["PMC1111", "PMC2222", "PMC3333", "PMC4444"])}
    assert out == {"PMC1111": (True, "ok"), "PMC2222": (False, "restricted"), "PMC3333": (True, "front_only"), "PMC4444": (False, "missing")}
    assert calls[0]["db"] == "pmc" and calls[0]["id"] == "PMC1111,PMC2222,PMC3333,PMC4444"


def test_pipeline_ncbi_fetch_then_convert_with_provenance(tmp_path):
    paths = DataPaths(root=tmp_path)
    write_jsonl(paths.records, [
        {"key": f"MED:{i}", "id": str(i), "source": "MED", "pmcid": p, "title": t, "year": 2026, "tiers": ["core"]}
        for i, (p, t) in enumerate([("PMC1111", "Open one"), ("PMC2222", "Closed one"), ("PMC3333", "Abstract only"), ("PMC4444", "Missing")], 1)
    ])
    calls = []
    res = fetch_fulltext_ncbi(paths, batch_size=2, client_factory=lambda: _client(calls))
    assert res["saved_with_body"] == 1 and res["saved_front_only"] == 1 and res["restricted"] == 1 and res["missing"] == 1
    assert res["remaining"] == 0 and len(calls) == 2  # two batches of two
    assert (paths.fulltext_xml / "PMC1111.xml").exists() and not (paths.fulltext_xml / "PMC2222.xml").exists()
    assert read_sources(paths) == {"PMC1111": "ncbi", "PMC3333": "ncbi"}
    log = [json.loads(line) for line in paths.fulltext_log.read_text(encoding="utf-8").splitlines()]
    assert {e["pmcid"]: e["status"] for e in log} == {"PMC1111": 200, "PMC2222": 403, "PMC3333": 200, "PMC4444": 404}
    # second run has nothing new to do for saved files; restricted/missing are retried (not on disk)
    res2 = fetch_fulltext_ncbi(paths, batch_size=10, client_factory=lambda: _client(calls))
    assert res2["to_fetch"] == 2 and res2["saved_with_body"] == 0

    cv = convert_fulltext(paths)
    assert cv["converted"] == 2 and cv["failed"] == 0
    md = (paths.fulltext_md / "PMC1111.md").read_text(encoding="utf-8")
    assert 'source: "NCBI E-utilities efetch (db=pmc)"' in md and "## Methods" in md and "We enrolled 17 dogs." in md
