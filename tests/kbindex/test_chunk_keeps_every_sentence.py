import json
import re
import warnings
from pathlib import Path

from kbindex.chunk import chunk_article, strip_doc_banner
from core.config import PASSAGE_TOKEN_CAP
from encoders.embed import load_embedder

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "kb_ingestion"
FIXTURE = Path(__file__).parent / "fixtures" / "article.md"
FIXTURE_TITLE = "Fixture Article"
FIXTURE_SLUG = "fixture-article"
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$", re.MULTILINE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _encoder_max() -> int:
    limit = load_embedder().tokenizer.model_max_length
    if isinstance(limit, int) and not isinstance(limit, bool) and 0 < limit <= 512:
        return limit
    return 512


def _token_count(text: str) -> int:
    return len(
        load_embedder().tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=True,
            max_length=_encoder_max() + 1,
        )
    )


def _crawl_dir() -> Path:
    return sorted(path for path in ROOT.iterdir() if path.is_dir())[-1]


def _sections(text: str, title: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(text))
    if not matches:
        body = text.strip()
        return [(title, body)] if body else []
    sections = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append((title, preamble))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if body:
            sections.append((match.group(2).strip(), body))
    return sections


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text.strip()) if part.strip()]


def test_chunk_keeps_every_sentence():
    passage_path = _crawl_dir() / "passages.jsonl"
    assert passage_path.is_file()

    crawl_dir = _crawl_dir()
    manifest = json.loads((crawl_dir / "manifest.json").read_text())
    article = manifest["articles"][0]
    raw_path = REPO / article["file_path"]
    raw = raw_path.read_text()
    saved_hash = raw_path.read_bytes()
    expected = chunk_article(raw, article["title"])
    saved = [
        json.loads(line)
        for line in passage_path.read_text().splitlines()
        if line and json.loads(line)["slug"] == article["slug"]
    ]
    assert saved == [{"slug": article["slug"], **passage} for passage in expected]
    assert raw_path.read_bytes() == saved_hash
    _assert_fitting_sentences_kept(strip_doc_banner(raw), article["title"], expected)

    fixture = FIXTURE.read_text()
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        fixture_passages = chunk_article(fixture, FIXTURE_TITLE)
    assert fixture_passages
    assert all(_token_count(passage["body"]) <= _encoder_max() for passage in fixture_passages)
    stripped = strip_doc_banner(fixture)
    sections = dict(_sections(stripped, FIXTURE_TITLE))
    within_sentence = _sentences(sections["Within Encoder Maximum"])[0]
    assert PASSAGE_TOKEN_CAP < _token_count(within_sentence) <= _encoder_max()
    within_body = next(
        passage["body"]
        for passage in fixture_passages
        if passage["heading"] == "Within Encoder Maximum"
    )
    assert within_body == within_sentence
    _assert_fitting_sentences_kept(stripped, FIXTURE_TITLE, fixture_passages)
    counts = _sentence_counts(stripped, FIXTURE_TITLE, fixture_passages)
    assert any(count == 2 for count in counts.values())

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warned = chunk_article(fixture, FIXTURE_TITLE, FIXTURE_SLUG)
    within_count = str(_token_count(within_sentence))
    assert any(
        issubclass(item.category, UserWarning)
        and FIXTURE_SLUG in str(item.message)
        and within_count in str(item.message)
        for item in caught
    )
    for passage in warned:
        count = _token_count(passage["body"])
        if count > PASSAGE_TOKEN_CAP:
            assert any(
                FIXTURE_SLUG in str(item.message) and str(count) in str(item.message)
                for item in caught
            )


def _assert_fitting_sentences_kept(text: str, title: str, passages: list) -> None:
    bodies = [passage["body"] for passage in passages]
    limit = _encoder_max()
    for _heading, body in _sections(text, title):
        for sentence in _sentences(body):
            if _token_count(sentence) <= limit:
                assert any(sentence in passage_body for passage_body in bodies)
                continue
            assert all(sentence not in passage_body for passage_body in bodies)
            kept = [passage_body for passage_body in bodies if sentence.startswith(passage_body)]
            assert kept
            assert all(sentence != passage_body for passage_body in kept)


def _sentence_counts(text: str, title: str, passages: list) -> dict[str, int]:
    bodies = [passage["body"] for passage in passages]
    limit = _encoder_max()
    counts = {}
    for _heading, body in _sections(text, title):
        for sentence in _sentences(body):
            if _token_count(sentence) <= limit:
                counts[sentence] = sum(passage_body.count(sentence) for passage_body in bodies)
    return counts
