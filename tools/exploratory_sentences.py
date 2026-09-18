"""Frozen copy of the repository sentence counter for isolated exploratory runs."""

import re

_SENTENCE_TERMINATORS = frozenset(".?!\u3002\uff01\uff1f")
_TRAILING_CLOSERS = frozenset("\"'\u2019\u201d\u00bb)]}`*_~")
_ALWAYS_NONTERMINAL_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "e.g",
        "i.e",
        "\u0433",
        "\u0438\u043c",
        "\u0442.\u0435",
        "\u0442.\u043a",
        "\u0442.\u0434",
        "\u0442.\u043f",
        "\u0443\u043b",
    }
)
_CONDITIONAL_ABBREVIATIONS = frozenset(
    {
        "etc",
        "vs",
        "no",
        "fig",
        "inc",
        "ltd",
        "\u0434\u0440",
        "\u0440\u0438\u0441",
        "\u0441\u0442\u0440",
    }
)
_URL = re.compile(r"https?://[^\s<>`]+", flags=re.IGNORECASE)


def _next_significant_index(text: str, start: int) -> int | None:
    index = start
    while index < len(text) and (text[index].isspace() or text[index] in _TRAILING_CLOSERS):
        index += 1
    return index if index < len(text) else None


def _preceding_dot_token(text: str, dot_index: int) -> tuple[int, str]:
    start = dot_index - 1
    while start >= 0 and (text[start].isalpha() or text[start] == "."):
        start -= 1
    return start + 1, text[start + 1 : dot_index].strip(".").casefold()


def _is_initialism(token: str) -> bool:
    parts = token.split(".")
    return len(parts) >= 2 and all(len(part) == 1 and part.isalpha() for part in parts)


def _is_list_marker(text: str, dot_index: int) -> bool:
    if dot_index + 1 >= len(text) or not text[dot_index + 1].isspace():
        return False
    end = dot_index
    start = end - 1
    while start >= 0 and text[start].isalnum():
        start -= 1
    token = text[start + 1 : end]
    if not (token.isdigit() or (len(token) == 1 and token.isascii() and token.isalpha())):
        return False
    previous = start
    while previous >= 0 and text[previous] in " \t":
        previous -= 1
    at_item_boundary = (
        previous < 0 or text[previous] in "\r\n:;([{" or text[previous] in _SENTENCE_TERMINATORS
    )
    return at_item_boundary and _next_significant_index(text, dot_index + 1) is not None


def _is_nonterminal_dot(text: str, dot_index: int) -> bool:
    previous = text[dot_index - 1] if dot_index > 0 else ""
    following = text[dot_index + 1] if dot_index + 1 < len(text) else ""
    if previous.isalnum() and following.isalnum():
        return True
    if _is_list_marker(text, dot_index):
        return True

    _, token = _preceding_dot_token(text, dot_index)
    next_index = _next_significant_index(text, dot_index + 1)
    if next_index is None:
        return False
    if token in _ALWAYS_NONTERMINAL_ABBREVIATIONS or _is_initialism(token):
        return True
    if len(token) == 1 and token.isalpha():
        return True
    return token in _CONDITIONAL_ABBREVIATIONS and not text[next_index].isupper()


def _protect_code_punctuation(text: str, protected: set[int]) -> None:
    index = 0
    while index < len(text):
        if text[index] != "`":
            index += 1
            continue
        marker_end = index + 1
        while marker_end < len(text) and text[marker_end] == "`":
            marker_end += 1
        marker = text[index:marker_end]
        closing = text.find(marker, marker_end)
        span_end = len(text) if closing < 0 else closing + len(marker)
        protected.update(
            position
            for position in range(index, span_end)
            if text[position] in _SENTENCE_TERMINATORS
        )
        index = span_end


def _protected_punctuation(text: str) -> frozenset[int]:
    protected: set[int] = set()
    _protect_code_punctuation(text, protected)
    for match in _URL.finditer(text):
        end = match.end()
        while end > match.start() and text[end - 1] in _SENTENCE_TERMINATORS:
            end -= 1
        protected.update(
            position
            for position in range(match.start(), end)
            if text[position] in _SENTENCE_TERMINATORS
        )
    return frozenset(protected)


def _consume_boundary_cluster(text: str, start: int) -> int:
    index = start
    while True:
        while index < len(text) and text[index] in _SENTENCE_TERMINATORS:
            index += 1
        while index < len(text) and text[index] in _TRAILING_CLOSERS:
            index += 1
        if index >= len(text) or text[index] not in _SENTENCE_TERMINATORS:
            return index


def count_sentences(text: str) -> int:
    if not text.strip():
        return 0

    count = 0
    segment_has_content = False
    protected = _protected_punctuation(text)
    index = 0
    while index < len(text):
        character = text[index]
        if character not in _SENTENCE_TERMINATORS:
            if not character.isspace() and character not in _TRAILING_CLOSERS:
                segment_has_content = True
            index += 1
            continue

        if index in protected:
            segment_has_content = True
            index += 1
            continue

        run_end = index + 1
        while run_end < len(text) and text[run_end] in _SENTENCE_TERMINATORS:
            run_end += 1
        run = text[index:run_end]
        if run == "." and _is_nonterminal_dot(text, index):
            segment_has_content = True
            index = run_end
            continue

        if segment_has_content or count == 0:
            count += 1
        segment_has_content = False
        index = _consume_boundary_cluster(text, run_end)

    return max(1, count + int(segment_has_content))
