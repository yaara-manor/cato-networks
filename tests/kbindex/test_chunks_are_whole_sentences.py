import re
from pathlib import Path

from kbindex.chunk import chunk_article, heading_anchor, strip_doc_banner
from kbindex.config import PASSAGE_TOKEN_CAP
from kbindex.embed import load_embedder

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "kb_ingestion"
FIXTURE = Path(__file__).parent / "fixtures" / "article.md"
FIXTURE_TITLE = "Fixture Article"
NEXT_HEADING = "Sentinel Heading After Long Section"
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$", re.MULTILINE)
_SENTENCE_END = ".!?"


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


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sections(text: str, title: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(text))
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


def test_chunks_are_whole_sentences():
    assert (_crawl_dir() / "passages.jsonl").is_file()

    fixture = FIXTURE.read_text()
    assert "> ## Documentation Index" in fixture
    passages = chunk_article(fixture, FIXTURE_TITLE, "fixture-article")
    assert passages[0]["heading"] == FIXTURE_TITLE
    assert passages[0]["position"] == 0
    assert all(passage["heading"] != "Empty Heading" for passage in passages)
    assert all("Documentation Index" not in passage["body"] for passage in passages)
    assert [passage["position"] for passage in passages] == list(range(len(passages)))

    within = next(passage for passage in passages if passage["heading"] == "Within Encoder Maximum")
    assert within["body"].rstrip()[-1] in _SENTENCE_END
    assert PASSAGE_TOKEN_CAP < _token_count(within["body"]) <= _encoder_max()

    stripped = strip_doc_banner(fixture)
    sections = {heading: body for heading, body in _sections(stripped, FIXTURE_TITLE)}
    hard_cuts = []
    for passage in passages:
        body = passage["body"]
        assert _token_count(body) <= _encoder_max()
        assert NEXT_HEADING not in body
        section = _norm(sections[passage["heading"]])
        normal_body = _norm(body)
        start = section.find(normal_body)
        assert start >= 0
        assert start == 0 or (
            section[start - 1] == " " and section[start - 2] in _SENTENCE_END
        )
        if body.rstrip()[-1:] not in _SENTENCE_END:
            hard_cuts.append(passage)
            continue
        assert body.rstrip()[-1] in _SENTENCE_END

    assert len(hard_cuts) == 1
    hard = hard_cuts[0]
    assert hard["heading"] == "Over Cap Sentence"
    source = _norm(sections["Over Cap Sentence"])
    words = source.split()
    kept = hard["body"].split()
    assert hard["body"] == " ".join(words[: len(kept)])
    assert _token_count(hard["body"]) <= _encoder_max()
    assert _token_count(" ".join(words[: len(kept) + 1])) > _encoder_max()

    long_slices = [passage for passage in passages if passage["heading"] == "Long Section"]
    assert len(long_slices) >= 2
    assert len({passage["heading_anchor"] for passage in long_slices}) == 1
    overlapped = False
    for previous, current in zip(long_slices, long_slices[1:]):
        assert NEXT_HEADING not in current["body"]
        for match in re.finditer(r"(?<=[.!?])\s+", current["body"]):
            copied = current["body"][: match.start()]
            if previous["body"].endswith(copied):
                overlapped = True
                break
    assert overlapped

    used = set()
    assert heading_anchor("Foo Bar", 0, used) == "foo-bar"
    assert heading_anchor("Foo Bar!", 1, used) == "foo-bar-1"


def _crawl_dir() -> Path:
    return sorted(path for path in ROOT.iterdir() if path.is_dir())[-1]
