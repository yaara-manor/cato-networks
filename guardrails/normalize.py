from dataclasses import dataclass
import unicodedata

_ZERO_WIDTH: frozenset[str] = frozenset("\u200b\u200c\u200d\u2060\ufeff")


@dataclass(frozen=True)
class NormalizedText:
    text: str
    offsets: tuple[int, ...]

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        return self.offsets[start], self.offsets[end - 1] + 1


# ponytail: per-character NFKC skips cross-character composition (e + combining accent). Secrets are ASCII-dominant; upgrade path: normalize grapheme clusters.
def normalize(text: str) -> NormalizedText:
    chars: list[str] = []
    offsets: list[int] = []
    for index, ch in enumerate(text):
        if ch in _ZERO_WIDTH:
            continue
        folded = unicodedata.normalize("NFKC", ch)
        chars.append(folded)
        offsets.extend([index] * len(folded))
    return NormalizedText("".join(chars), tuple(offsets))
