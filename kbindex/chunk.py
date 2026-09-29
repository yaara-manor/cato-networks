import json
import re
import warnings
from pathlib import Path

from kbindex.config import PASSAGE_TOKEN_CAP, SLICE_NEW_TOKENS, SLICE_OVERLAP_TOKENS
from kbindex.embed import load_embedder

# ponytail: ATX headings only; a hash inside a code fence is treated as a heading. Upgrade path: skip fenced blocks.
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$", re.MULTILINE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_BANNER = re.compile(r"(?m)^> ## Documentation Index[^\n]*\n(?:>[^\n]*\n)*")


def strip_doc_banner(markdown) -> str:
    # Remove the documentation-index banner from passage text only.
    return _BANNER.sub("", markdown)


def heading_anchor(heading, position, used) -> str:
    # Build a unique heading anchor for one article.
    slug = "".join(
        char for char in re.sub(r"\s", "-", heading.lower()) if char.isalnum() or char == "-"
    )
    if slug in used:
        slug = f"{slug}-{position}"
    used.add(slug)
    return slug


def chunk_article(markdown, title, slug="") -> list:
    # Split one article into citable passages using the pinned bge-small tokenizer.
    passages = []
    used: set[str] = set()
    limit = _encoder_max()
    for heading, body in _sections(strip_doc_banner(markdown), title):
        slices = _slice_bodies(_sentences(body))
        if not slices:
            continue
        anchor = heading_anchor(heading, len(passages), used)
        for body_slice in slices:
            count = _tokens(body_slice)
            if count > limit:
                raise ValueError(f"{slug} passage is {count} tokens")
            if count > PASSAGE_TOKEN_CAP:
                warnings.warn(f"{slug} passage is {count} tokens", stacklevel=2)
            passages.append(
                {
                    "heading": heading,
                    "heading_anchor": anchor,
                    "position": len(passages),
                    "body": body_slice,
                }
            )
    return passages


def write_passages(crawl_dir) -> None:
    # Write one passage record per line for the saved crawl.
    crawl_dir = Path(crawl_dir)
    manifest = json.loads((crawl_dir / "manifest.json").read_text())
    repo = Path(__file__).resolve().parents[1]
    lines = []
    for article in manifest["articles"]:
        raw = (repo / article["file_path"]).read_text()
        for passage in chunk_article(raw, article["title"], article["slug"]):
            lines.append(
                json.dumps(
                    {
                        "slug": article["slug"],
                        "heading": passage["heading"],
                        "heading_anchor": passage["heading_anchor"],
                        "position": passage["position"],
                        "body": passage["body"],
                    },
                    ensure_ascii=False,
                )
            )
    (crawl_dir / "passages.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""))


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


def _join(parts: list[str]) -> str:
    return " ".join(part for part in parts if part)


def _encoder_max() -> int:
    limit = load_embedder().tokenizer.model_max_length
    if isinstance(limit, int) and not isinstance(limit, bool) and 0 < limit <= 512:
        return limit
    return 512


def _tokens(text: str) -> int:
    if not text:
        return 0
    return len(
        load_embedder().tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=True,
            max_length=_encoder_max() + 1,
        )
    )


def _hard_cut(sentence: str) -> str:
    words = sentence.split()
    low = 0
    high = len(words)
    best = ""
    limit = _encoder_max()
    while low < high:
        mid = (low + high + 1) // 2
        candidate = " ".join(words[:mid])
        if _tokens(candidate) <= limit:
            best = candidate
            low = mid
        else:
            high = mid - 1
    return best


def _within(parts: list[str], sentence: str, budget: int) -> bool:
    return _tokens(_join(parts + [sentence])) <= budget


def _tail_overlap(previous: str) -> str:
    if not previous.rstrip().endswith((".", "?", "!")):
        return ""
    chosen: list[str] = []
    for sentence in reversed(_sentences(previous)):
        trial = _join([sentence, *chosen])
        if _tokens(trial) > SLICE_OVERLAP_TOKENS:
            break
        chosen.insert(0, sentence)
    return _join(chosen)


def _with_overlap(previous: str, new_body: str) -> str:
    overlap = _tail_overlap(previous)
    while overlap and _tokens(f"{overlap} {new_body}") > PASSAGE_TOKEN_CAP:
        parts = _sentences(overlap)
        overlap = _join(parts[1:]) if len(parts) > 1 else ""
    if overlap:
        return f"{overlap} {new_body}"
    return new_body


def _slice_bodies(sentences: list[str]) -> list[str]:
    slices: list[str] = []
    index = 0
    limit = _encoder_max()
    while index < len(sentences):
        if _tokens(sentences[index]) > limit:
            kept = _hard_cut(sentences[index])
            if kept:
                slices.append(kept)
            index += 1
            continue
        budget = PASSAGE_TOKEN_CAP if not slices else SLICE_NEW_TOKENS
        parts: list[str] = []
        alone = False
        while index < len(sentences) and _tokens(sentences[index]) <= limit:
            if not _within(parts, sentences[index], budget):
                if not parts:
                    parts.append(sentences[index])
                    index += 1
                    alone = True
                break
            parts.append(sentences[index])
            index += 1
        body = _join(parts) if alone or not slices else _with_overlap(slices[-1], _join(parts))
        if body:
            slices.append(body)
    return slices
