import re
from pathlib import Path

from canine_aging_corpus.jats import jats_to_markdown

FIX = Path(__file__).parent / "fixtures" / "sample_jats.xml"


def has_heading(md: str, level: int, text: str) -> bool:
    """Exact heading level on its own line (a substring check would accept deeper levels)."""
    return re.search(rf"^{'#' * level} {re.escape(text)}$", md, flags=re.MULTILINE) is not None


def test_title_abstract_and_ids():
    art = jats_to_markdown(FIX.read_bytes())
    assert art.title == "Weekly *rapamycin* in companion dogs: a test article"
    assert art.meta["pmid"] == "99999999"
    assert art.meta["pmc"] == "PMC0000001"
    assert art.meta["doi"] == "10.1000/example.2026"
    assert art.meta["journal"] == "GeroScience"
    assert art.meta["article_type"] == "research-article"
    assert art.meta["license"].startswith("http://creativecommons.org/licenses/by/4.0")
    assert has_heading(art.abstract, 3, "Background")
    assert has_heading(art.abstract, 3, "Results")
    assert "Dogs age faster than humans1." in art.abstract  # xref reduced to its text
    assert "**12.5**" in art.abstract


def test_heading_levels_are_exact():
    md = jats_to_markdown(FIX.read_bytes()).markdown()
    assert has_heading(md, 1, "Weekly *rapamycin* in companion dogs: a test article")
    assert has_heading(md, 2, "Abstract")
    assert has_heading(md, 3, "Background")  # abstract sub-sections sit under ## Abstract
    assert has_heading(md, 2, "Introduction")  # top-level body sections are H2
    assert has_heading(md, 3, "Prior work")  # nested body sections are H3
    assert has_heading(md, 2, "Methods")
    assert not re.search(r"^####", md, flags=re.MULTILINE)


def test_body_structure_tables_figures_lists():
    md = jats_to_markdown(FIX.read_bytes()).markdown()
    assert md.startswith("# Weekly *rapamycin* in companion dogs")
    assert has_heading(md, 2, "Introduction")
    assert has_heading(md, 3, "Prior work")
    assert "- Cardiac function" in md and "- Activity" in md
    assert "**Table 1 Enrolment by size class.**" in md
    assert "| Size | N |" in md
    assert "| --- | --- |" in md
    assert "| Giant | 180 |" in md
    assert "*Figure: Figure 1 Study design.*" in md
    assert "Should not appear" not in md  # back matter dropped
    assert "*IGF1*" in md


def test_untitled_wrapper_sections_and_abstract_title():
    xml = b"""<article><front><article-meta>
      <title-group><article-title>T</article-title></title-group>
      <abstract><title>Abstract</title><p>Plain abstract.</p></abstract>
    </article-meta></front>
    <body><sec><p>Dear Editor,</p><sec><title>Funding</title><p>None.</p></sec></sec></body></article>"""
    art = jats_to_markdown(xml)
    md = art.markdown()
    assert art.abstract == "Plain abstract."  # abstract's own <title> not duplicated
    assert md.count("## Abstract") == 1
    assert has_heading(md, 2, "Funding")  # untitled wrapper <sec> did not add a level


def test_heading_only_sections_are_dropped():
    xml = b"""<article><body>
      <sec><title>Results</title><p>Some result.</p></sec>
      <sec><title>References</title><ref-list><ref><mixed-citation>X</mixed-citation></ref></ref-list></sec>
      <sec><title>Associated Data</title>
        <sec><title>Supplementary Materials</title><supplementary-material/></sec>
        <sec><title>Data Availability Statement</title><p>On request.</p></sec>
      </sec>
    </body></article>"""
    md = jats_to_markdown(xml).markdown()
    assert has_heading(md, 2, "Results")
    assert "References" not in md
    assert "Supplementary Materials" not in md
    assert has_heading(md, 2, "Associated Data") and has_heading(md, 3, "Data Availability Statement")
    broken = b'<article xmlns="http://jats.nlm.nih.gov"><front><article-meta><title-group><article-title>T</article-title></title-group></article-meta></front><body><sec><title>A</title><p>text</p></sec>'
    art = jats_to_markdown(broken)
    assert art.title == "T"
    assert has_heading(art.markdown(), 2, "A")
    assert "text" in art.markdown()
