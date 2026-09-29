import json
import re
from pathlib import Path

from kbindex.config import PASSAGE_TOKEN_CAP
from kbindex.embed import load_embedder

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "kb_ingestion"
FIXTURE = Path(__file__).parent / "fixtures" / "article.md"
FIXTURE_TITLE = "Fixture Article"
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$", re.MULTILINE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _token_count(text: str) -> int:
    return len(
        load_embedder().tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=True,
            max_length=PASSAGE_TOKEN_CAP + 1,
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
    from kbindex.chunk import chunk_article, strip_doc_banner

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
    fixture_passages = chunk_article(fixture, FIXTURE_TITLE)
    assert fixture_passages
    assert all(_token_count(passage["body"]) <= PASSAGE_TOKEN_CAP for passage in fixture_passages)
    _assert_fitting_sentences_kept(strip_doc_banner(fixture), FIXTURE_TITLE, fixture_passages)
    counts = _sentence_counts(strip_doc_banner(fixture), FIXTURE_TITLE, fixture_passages)
    assert any(count == 2 for count in counts.values())


def _assert_fitting_sentences_kept(text: str, title: str, passages: list) -> None:
    bodies = [passage["body"] for passage in passages]
    for _heading, body in _sections(text, title):
        for sentence in _sentences(body):
            if _token_count(sentence) <= PASSAGE_TOKEN_CAP:
                assert any(sentence in passage_body for passage_body in bodies)
                continue
            assert all(sentence not in passage_body for passage_body in bodies)
            kept = [passage_body for passage_body in bodies if sentence.startswith(passage_body)]
            assert kept
            assert all(sentence != passage_body for passage_body in kept)


def _sentence_counts(text: str, title: str, passages: list) -> dict[str, int]:
    bodies = [passage["body"] for passage in passages]
    counts = {}
    for _heading, body in _sections(text, title):
        for sentence in _sentences(body):
            if _token_count(sentence) <= PASSAGE_TOKEN_CAP:
                counts[sentence] = sum(passage_body.count(sentence) for passage_body in bodies)
    return counts
