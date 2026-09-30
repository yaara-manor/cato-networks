from guardrails.normalize import normalize


def test_zero_width_characters_are_removed_and_spans_map_back() -> None:
    norm = normalize("pa\u200bss\ufeffword")
    assert norm.text == "password"
    assert norm.original_span(0, 8) == (0, 10)


def test_fullwidth_letters_fold_to_ascii() -> None:
    norm = normalize("\uff30\uff33\uff2b")
    assert norm.text == "PSK"
    assert norm.original_span(0, 3) == (0, 3)


def test_expanding_character_maps_to_one_source_index() -> None:
    norm = normalize("a\ufb01b")
    assert norm.text == "afib"
    assert norm.original_span(1, 3) == (1, 2)


def test_plain_ascii_is_identity() -> None:
    text = "BGP hold time is 30 seconds"
    norm = normalize(text)
    assert norm.text == text
    assert norm.offsets == tuple(range(len(text)))
