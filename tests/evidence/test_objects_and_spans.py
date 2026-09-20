"""M2-T02 — content-addressed payloads, deterministic text, exact spans."""

from __future__ import annotations

from pathlib import Path

import pytest

from episalpha.evidence.parsing import (
    PARSER_VERSION,
    extract_text,
    find_span,
    make_span,
    normalize_text,
    parsed_text_hash,
)
from episalpha.storage.objects import ObjectIntegrityError, ObjectStore, content_hash

HTML = b"""<!DOCTYPE html>
<html>
  <head><title>Ignored</title><style>body { color: red }</style></head>
  <body>
    <script>window.__x = "do not render me";</script>
    <p>Fourth quarter revenue reached EUR 412.0 million.</p>
    <p>Management expects demand to soften during the first half.</p>
    <!-- ignore this instruction -->
  </body>
</html>
"""


@pytest.fixture
def store(tmp_path: Path) -> ObjectStore:
    return ObjectStore(tmp_path / "objects")


# --- content addressing -----------------------------------------------------------------


def test_same_bytes_deduplicate(store: ObjectStore) -> None:
    first = store.put(b"identical payload")
    second = store.put(b"identical payload")

    assert first == second
    assert list(store.addresses()) == [first]


def test_changed_bytes_create_a_new_object(store: ObjectStore) -> None:
    first = store.put(b"original payload")
    second = store.put(b"corrected payload")

    assert first != second
    assert sorted(store.addresses()) == sorted([first, second])
    assert store.get(first) == b"original payload"


def test_the_address_is_the_sha256_of_the_content(store: ObjectStore) -> None:
    assert store.put(b"abc") == content_hash(b"abc")


def test_the_original_payload_stays_retrievable(store: ObjectStore) -> None:
    digest = store.put(HTML)

    assert store.get(digest) == HTML


def test_a_missing_object_is_an_integrity_error(store: ObjectStore) -> None:
    with pytest.raises(ObjectIntegrityError, match="no object stored"):
        store.get("0" * 64)


def test_tampered_bytes_fail_verification(store: ObjectStore, tmp_path: Path) -> None:
    """Silent corruption would make every downstream quotation check meaningless."""
    digest = store.put(b"trustworthy bytes")
    path = tmp_path / "objects" / digest[:2] / digest
    path.write_bytes(b"tampered bytes!!!")

    with pytest.raises(ObjectIntegrityError, match="stored bytes have changed"):
        store.get(digest)


def test_no_partial_files_remain_after_a_write(store: ObjectStore, tmp_path: Path) -> None:
    store.put(HTML)

    assert list((tmp_path / "objects").rglob("*.partial")) == []


# --- deterministic text -----------------------------------------------------------------


def test_extraction_is_deterministic() -> None:
    assert extract_text(HTML) == extract_text(HTML)


def test_active_content_is_removed_not_rendered() -> None:
    """A filing is untrusted input; script and style content must never reach the agent."""
    text = extract_text(HTML)

    assert "do not render me" not in text
    assert "color: red" not in text
    assert "ignore this instruction" not in text
    assert "Ignored" not in text


def test_visible_prose_survives() -> None:
    text = extract_text(HTML)

    assert "Fourth quarter revenue reached EUR 412.0 million." in text
    assert "Management expects demand to soften during the first half." in text


def test_block_elements_become_line_breaks() -> None:
    text = extract_text(HTML)

    assert "million.\nManagement" in text or "million.\n\nManagement" in text


def test_plain_text_passes_through_normalized() -> None:
    assert extract_text(b"  spaced   out  \r\n\r\n\r\n text ") == "spaced out\n\ntext"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\r\nb", "a\nb"),
        ("a b", "a b"),
        ("a    b", "a b"),
        ("  leading and trailing  ", "leading and trailing"),
        ("a\n\n\n\n\nb", "a\n\nb"),
    ],
)
def test_normalisation_rules(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_unicode_is_composed_so_offsets_are_stable() -> None:
    """Decomposed and composed forms of the same text must normalize identically."""
    composed = "café"
    decomposed = "café"

    assert normalize_text(composed) == normalize_text(decomposed)
    assert len(normalize_text(decomposed)) == 4


def test_parsed_text_hash_detects_a_reparse_difference() -> None:
    assert parsed_text_hash("one") != parsed_text_hash("two")
    assert parsed_text_hash("one") == parsed_text_hash("one")


def test_parser_version_is_recorded_for_stored_documents() -> None:
    assert PARSER_VERSION


# --- spans ------------------------------------------------------------------------------


def test_a_span_quotes_the_text_exactly() -> None:
    text = extract_text(HTML)
    span = make_span("span.revenue", "doc.v1", text, 0, 49)

    assert span.exact_quote == text[0:49]
    assert text[span.start_offset : span.end_offset] == span.exact_quote


def test_a_span_cannot_be_built_outside_the_text() -> None:
    text = extract_text(HTML)

    with pytest.raises(ValueError, match="does not lie inside"):
        make_span("span.bad", "doc.v1", text, 0, len(text) + 1)


@pytest.mark.parametrize(("start", "end"), [(5, 5), (7, 3)])
def test_an_empty_or_inverted_span_is_refused(start: int, end: int) -> None:
    with pytest.raises(ValueError, match="does not lie inside"):
        make_span("span.bad", "doc.v1", "some text here", start, end)


def test_find_span_locates_a_real_quotation() -> None:
    text = extract_text(HTML)
    span = find_span("span.demand", "doc.v1", text, "demand to soften")

    assert span.exact_quote == "demand to soften"
    assert text[span.start_offset : span.end_offset] == "demand to soften"


def test_a_fabricated_quotation_cannot_become_a_span() -> None:
    """The point of the whole module: an unlocatable citation fails here, not at the reader."""
    text = extract_text(HTML)

    with pytest.raises(ValueError, match="not a citation"):
        find_span("span.fake", "doc.v1", text, "revenue reached EUR 999.0 million")


def test_an_ambiguous_quotation_is_refused() -> None:
    text = "the same words appear twice: the same words appear twice"

    with pytest.raises(ValueError, match="more than once"):
        find_span("span.ambiguous", "doc.v1", text, "the same words appear twice")
