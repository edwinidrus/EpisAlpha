"""Deterministic text extraction and span creation (plan M2-T02).

Two properties matter more than extraction quality here:

1. **Determinism.** The same bytes and the same parser version must produce byte-identical
   normalized text, or every stored span offset silently rots.
2. **Inertness.** Script, style and other active content is removed, not rendered. A filing is
   untrusted input: it may contain text engineered to steer an agent that later reads it
   (threat model, plan section 14). Stripping it here means the agent sees prose, not payload.

Scope is HTML and plain text, which covers the selected demo corpus. PDF and OCR are out.
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

from episalpha.contracts.knowledge import EvidenceSpan
from episalpha.storage.objects import content_hash

PARSER_VERSION = "episalpha-html-1"
"""Bump whenever normalization changes. Stored on every document so old spans stay explicable."""

# Elements whose *content* is code or metadata, never prose a reader would see.
_DROPPED_CONTENT = frozenset({"script", "style", "template", "noscript", "head", "title"})

# Elements that imply a visible break between the text around them.
_BLOCK_ELEMENTS = frozenset(
    {
        "p",
        "div",
        "br",
        "tr",
        "td",
        "th",
        "li",
        "ul",
        "ol",
        "table",
        "section",
        "article",
        "header",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
    }
)

_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class _TextExtractor(HTMLParser):
    """Collects visible text, dropping active content entirely."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._suppress_depth = 0
        self._suppressing: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROPPED_CONTENT:
            self._suppressing.append(tag)
            self._suppress_depth += 1
            return
        if tag in _BLOCK_ELEMENTS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROPPED_CONTENT and self._suppress_depth:
            if self._suppressing and self._suppressing[-1] == tag:
                self._suppressing.pop()
                self._suppress_depth -= 1
            return
        if tag in _BLOCK_ELEMENTS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._suppress_depth:
            return
        self.parts.append(data)

    # Comments can carry instructions too; they are never visible text.
    def handle_comment(self, data: str) -> None:
        return


def normalize_text(raw: str) -> str:
    """Collapse a document to deterministic, comparable text.

    NFC first, so visually identical text from different sources normalizes to the same
    code points and therefore the same offsets.
    """
    text = unicodedata.normalize("NFC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def looks_like_html(payload: bytes) -> bool:
    head = payload[:4096].lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html", b"<?xml")) or b"<body" in head


def extract_text(payload: bytes, *, encoding: str = "utf-8") -> str:
    """Normalized visible text for a payload. Deterministic for a given ``PARSER_VERSION``."""
    raw = payload.decode(encoding, errors="replace")
    if looks_like_html(payload):
        extractor = _TextExtractor()
        extractor.feed(raw)
        extractor.close()
        raw = "".join(extractor.parts)
    return normalize_text(raw)


def parsed_text_hash(text: str) -> str:
    """Address of the normalized text, so a reparse that changes it is detectable."""
    return content_hash(text.encode("utf-8"))


def make_span(
    span_id: str,
    document_id: str,
    text: str,
    start_offset: int,
    end_offset: int,
    section_locator: str | None = None,
) -> EvidenceSpan:
    """Cut a span out of normalized text, quoting it exactly.

    The quote is taken *from* the text rather than supplied by the caller, so a span can never
    be constructed around a quotation the document does not contain.
    """
    if not 0 <= start_offset < end_offset <= len(text):
        raise ValueError(
            f"span {start_offset}:{end_offset} does not lie inside {len(text)} characters "
            f"of document {document_id!r}"
        )
    return EvidenceSpan(
        span_id=span_id,
        document_id=document_id,
        start_offset=start_offset,
        end_offset=end_offset,
        exact_quote=text[start_offset:end_offset],
        section_locator=section_locator,
    )


def find_span(
    span_id: str,
    document_id: str,
    text: str,
    quote: str,
    section_locator: str | None = None,
) -> EvidenceSpan:
    """Locate a quotation in normalized text and build the span for it.

    Raises when the quotation is absent — which is the whole point. A citation that cannot be
    located is a fabricated citation, and it fails here rather than reaching a reader.
    """
    start = text.find(quote)
    if start < 0:
        raise ValueError(
            f"quotation not found in document {document_id!r}: {quote[:80]!r}. A citation that "
            "cannot be located in the stored text is not a citation"
        )
    if text.find(quote, start + 1) >= 0:
        raise ValueError(
            f"quotation appears more than once in document {document_id!r}; supply explicit "
            "offsets with make_span() so the span is unambiguous"
        )
    return make_span(span_id, document_id, text, start, start + len(quote), section_locator)
