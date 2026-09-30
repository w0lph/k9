"""Convert JATS (PMC) XML into Markdown suitable for indexing.

Kept: title, abstract, body sections (with heading depth), paragraphs, lists, table
captions plus a plain-text rendering of table cells, figure captions. Dropped: the
``<back>`` matter (references, acknowledgements), footnotes, and inline citation markup
(``<xref>`` is reduced to its text so sentences stay readable).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


@dataclass
class ConvertedArticle:
    title: str | None
    abstract: str | None
    body_markdown: str
    meta: dict = field(default_factory=dict)

    def markdown(self) -> str:
        parts: list[str] = []
        if self.title:
            parts.append(f"# {self.title}")
        if self.abstract:
            parts.append("## Abstract\n\n" + self.abstract)
        if self.body_markdown:
            parts.append(self.body_markdown)
        return _NL.sub("\n\n", "\n\n".join(parts)).strip() + "\n"


def _text(el: etree._Element | None) -> str:
    """All descendant text, whitespace-normalised."""
    if el is None:
        return ""
    return _WS.sub(" ", "".join(el.itertext())).strip()


def _inline(el: etree._Element) -> str:
    """Render an inline-bearing element (p, title, td...) to a single line of Markdown."""
    out: list[str] = []
    if el.text:
        out.append(el.text)
    for child in el:
        tag = etree.QName(child).localname if isinstance(child.tag, str) else None
        if tag in ("italic",):
            out.append(f"*{_inline(child)}*")
        elif tag in ("bold",):
            out.append(f"**{_inline(child)}**")
        elif tag in ("sup",):
            out.append(f"^{_inline(child)}^")
        elif tag in ("sub",):
            out.append(f"~{_inline(child)}~")
        elif tag in ("xref", "ext-link", "uri", "named-content", "sc", "underline", "monospace"):
            out.append(_inline(child))
        elif tag in ("fn", "table-wrap-foot", "private-char") or tag is None:
            pass
        else:
            out.append(_inline(child))
        if child.tail:
            out.append(child.tail)
    return _WS.sub(" ", "".join(out)).strip()


def _table(tw: etree._Element) -> str:
    label = _inline(tw.find("label")) if tw.find("label") is not None else ""
    caption = tw.find("caption")
    cap = _inline(caption) if caption is not None else ""
    head = " ".join(x for x in (label, cap) if x)
    rows: list[str] = []
    for tr in tw.iter("tr"):
        cells = [_inline(c) for c in tr if isinstance(c.tag, str) and etree.QName(c).localname in ("td", "th")]
        if cells:
            rows.append("| " + " | ".join(cells) + " |")
    parts = []
    if head:
        parts.append(f"**{head}**")
    if rows:
        if len(rows) > 1:
            ncol = rows[0].count("|") - 1
            rows.insert(1, "|" + " --- |" * max(ncol, 1))
        parts.append("\n".join(rows))
    return "\n\n".join(parts)


def _figure(fig: etree._Element) -> str:
    label = _inline(fig.find("label")) if fig.find("label") is not None else ""
    caption = fig.find("caption")
    cap = _inline(caption) if caption is not None else ""
    text = " ".join(x for x in (label, cap) if x)
    return f"*Figure: {text}*" if text else ""


def _list(lst: etree._Element, depth: int = 0) -> str:
    items = []
    for li in lst.findall("list-item"):
        chunks = []
        for child in li:
            tag = etree.QName(child).localname if isinstance(child.tag, str) else None
            if tag == "p":
                chunks.append(_inline(child))
            elif tag == "list":
                chunks.append(_list(child, depth + 1))
            elif tag == "label":
                continue
            else:
                chunks.append(_inline(child))
        items.append("  " * depth + "- " + " ".join(c for c in chunks if c))
    return "\n".join(items)


def _section(sec: etree._Element, level: int, skip_title: bool = False) -> list[str]:
    """Render the children of a section-like element.

    ``level`` is the heading level for this element's own <title>; child <sec> elements
    render one level deeper, except untitled wrapper sections, which render at the same
    level so a stray wrapper never consumes a heading level.
    """
    out: list[str] = []
    for child in sec:
        if not isinstance(child.tag, str):
            continue
        tag = etree.QName(child).localname
        if tag == "title":
            if skip_title:
                continue
            t = _inline(child)
            if t:
                out.append("#" * min(level, 6) + " " + t)
        elif tag == "p":
            t = _inline(child)
            if t:
                out.append(t)
        elif tag == "sec":
            titled = child.find("title") is not None
            rendered = _section(child, level + 1 if titled else level)
            # Drop sections that are nothing but headings (e.g. "References" whose
            # <ref-list> was skipped, or an empty "Supplementary Materials").
            if any(not line.startswith("#") for line in rendered):
                out.extend(rendered)
        elif tag == "table-wrap":
            out.append(_table(child))
        elif tag == "fig":
            f = _figure(child)
            if f:
                out.append(f)
        elif tag == "list":
            out.append(_list(child))
        elif tag in ("disp-quote", "boxed-text", "statement"):
            out.extend(_section(child, level + 1))
        elif tag in ("disp-formula", "code", "preformat"):
            t = _text(child)
            if t:
                out.append("```\n" + t + "\n```")
        elif tag in ("supplementary-material", "fn-group", "ref-list", "graphic", "media"):
            continue
        else:
            t = _inline(child)
            if t:
                out.append(t)
    return out


def jats_to_markdown(xml: bytes | str) -> ConvertedArticle:
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    parser = etree.XMLParser(recover=True, huge_tree=True, remove_comments=True)
    root = etree.fromstring(xml, parser=parser)
    if root is None:
        raise ValueError("could not parse JATS XML")
    # Strip namespaces so tag matching is by local name.
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]

    article = root if root.tag == "article" else root.find(".//article")
    if article is None:
        article = root

    front = article.find("front")
    meta: dict = {}
    if article.get("article-type"):
        meta["article_type"] = article.get("article-type")
    title = None
    abstract = None
    if front is not None:
        am = front.find("article-meta")
        if am is not None:
            tg = am.find("title-group/article-title")
            title = _inline(tg) if tg is not None else None
            for aid in am.findall("article-id"):
                kind = aid.get("pub-id-type")
                if kind:
                    meta[kind] = _text(aid)
            abs_el = am.find("abstract")
            if abs_el is not None:
                # Rendered under a "## Abstract" heading by ConvertedArticle.markdown(),
                # so its own <title> is skipped and its sub-sections become H3.
                abstract = "\n\n".join(x for x in _section(abs_el, 2, skip_title=True) if x)
            lic = am.find(".//license")
            if lic is not None:
                href = lic.get("{http://www.w3.org/1999/xlink}href") or lic.get("href")
                meta["license"] = href or _text(lic)[:200]
        jm = front.find("journal-meta")
        if jm is not None:
            jt = jm.find(".//journal-title")
            if jt is not None:
                meta["journal"] = _text(jt)

    body = article.find("body")
    # <body> has no title; its direct <sec> children become H2, nested ones H3, ...
    body_md = "\n\n".join(x for x in _section(body, 1) if x) if body is not None else ""
    return ConvertedArticle(title=title, abstract=abstract, body_markdown=body_md, meta=meta)
