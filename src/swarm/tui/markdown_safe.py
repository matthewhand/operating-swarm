"""Markdown-safe partial rendering for optional streaming (#220).

Mirrors ``webui/frontend/src/lib/markdownSafe.ts``. Hold unclosed bold,
italic, inline code, fenced blocks, and links until the closer arrives or
the stream ends (``complete=True``). Never drops text.
"""

from __future__ import annotations

from typing import NamedTuple


class MarkdownSafePartial(NamedTuple):
    visible: str
    held: str


_STRONG_STAR = "strong-star"
_EM_STAR = "em-star"
_STRONG_UNDER = "strong-under"
_EM_UNDER = "em-under"
_CODE = "code"
_FENCE = "fence"
_LINK = "link"
_LINKDEST = "linkdest"


def _count_run(src: str, i: int, ch: str) -> int:
    n = 0
    length = len(src)
    while i + n < length and src[i + n] == ch:
        n += 1
    return n


def _is_line_start(src: str, i: int) -> bool:
    return i == 0 or src[i - 1] == "\n"


def _match_fence_close(src: str, i: int, fence_char: str, fence_len: int) -> int:
    j = i
    spaces = 0
    length = len(src)
    while j < length and src[j] == " " and spaces < 3:
        j += 1
        spaces += 1
    if j >= length or src[j] != fence_char:
        return -1
    run = _count_run(src, j, fence_char)
    if run < fence_len:
        return -1
    j += run
    while j < length and src[j] in " \t":
        j += 1
    if j == length or src[j] == "\n":
        return j + 1 if j < length else j
    return -1


def _pop_kind(stack: list[dict], kind: str) -> bool:
    for s in range(len(stack) - 1, -1, -1):
        if stack[s]["kind"] == kind:
            del stack[s]
            return True
    return False


def _odd_trailing_backslash(src: str) -> int:
    n = len(src)
    if n == 0 or src[-1] != "\\":
        return n
    k = n - 1
    while k >= 0 and src[k] == "\\":
        k -= 1
    count = n - 1 - k
    return n - 1 if count % 2 == 1 else n


def _first_held_index(src: str) -> int:
    n = len(src)
    stack: list[dict] = []
    i = 0

    def top() -> dict | None:
        return stack[-1] if stack else None

    while i < n:
        ch = src[i]
        t = top()

        if t is not None and t["kind"] == _FENCE:
            if _is_line_start(src, i):
                close = _match_fence_close(src, i, t["fence_char"], t["fence_len"])
                if close >= 0:
                    stack.pop()
                    i = close
                    continue
            i += 1
            continue

        if t is not None and t["kind"] == _CODE:
            if ch == "`":
                run = _count_run(src, i, "`")
                if run == t["ticks"]:
                    stack.pop()
                    i += run
                    continue
            i += 1
            continue

        if t is not None and t["kind"] == _LINKDEST:
            if ch == ")":
                stack.pop()
                i += 1
                continue
            i += 1
            continue

        if ch == "\\" and i + 1 < n:
            i += 2
            continue

        if _is_line_start(src, i):
            j = i
            spaces = 0
            while j < n and src[j] == " " and spaces < 3:
                j += 1
                spaces += 1
            if j < n and src[j] in "`~":
                fence_char = src[j]
                run = _count_run(src, j, fence_char)
                if run >= 3:
                    k = j + run
                    while k < n and src[k] != "\n":
                        k += 1
                    stack.append(
                        {
                            "kind": _FENCE,
                            "start": i,
                            "fence_char": fence_char,
                            "fence_len": run,
                        }
                    )
                    i = k + 1 if k < n else k
                    continue
                if fence_char == "~" and j + run == n:
                    stack.append(
                        {
                            "kind": _FENCE,
                            "start": i,
                            "fence_char": fence_char,
                            "fence_len": 3,
                        }
                    )
                    break

        if ch == "`":
            run = _count_run(src, i, "`")
            stack.append({"kind": _CODE, "start": i, "ticks": run})
            i += run
            continue

        if ch == "!" and i + 1 < n and src[i + 1] == "[":
            stack.append({"kind": _LINK, "start": i})
            i += 2
            continue
        if ch == "[":
            stack.append({"kind": _LINK, "start": i})
            i += 1
            continue
        if ch == "]" and t is not None and t["kind"] == _LINK:
            if i + 1 < n and src[i + 1] == "(":
                t["kind"] = _LINKDEST
                i += 2
                continue
            stack.pop()
            i += 1
            continue

        if ch in "*_":
            run = _count_run(src, i, ch)
            if (
                _is_line_start(src, i)
                and ch == "*"
                and run == 1
                and (i + 1 >= n or src[i + 1] in " \t")
            ):
                i += 1
                continue
            remaining = run
            pos = i
            strong_kind = _STRONG_STAR if ch == "*" else _STRONG_UNDER
            em_kind = _EM_STAR if ch == "*" else _EM_UNDER
            prev = src[i - 1] if i > 0 else ""
            can_close = prev not in ("", " ", "\t", "\n")
            nxt = src[i + run] if i + run < n else ""
            can_open = nxt not in (" ", "\t", "\n")
            open_at_eos = nxt == ""

            while remaining > 0:
                if remaining >= 2 and can_close and _pop_kind(stack, strong_kind):
                    remaining -= 2
                    pos += 2
                    continue
                if remaining >= 1 and can_close and _pop_kind(stack, em_kind):
                    remaining -= 1
                    pos += 1
                    continue
                if remaining >= 2 and (can_open or open_at_eos):
                    stack.append({"kind": strong_kind, "start": pos})
                    remaining -= 2
                    pos += 2
                    continue
                if remaining >= 1 and (can_open or open_at_eos):
                    stack.append({"kind": em_kind, "start": pos})
                    remaining -= 1
                    pos += 1
                    continue
                remaining -= 1
                pos += 1
            i += run
            continue

        i += 1

    cut = n
    if stack:
        cut = min(cut, stack[0]["start"])
    cut = min(cut, _odd_trailing_backslash(src))
    return cut


def markdown_safe_partial(source: str, *, complete: bool = False) -> MarkdownSafePartial:
    text = "" if source is None else str(source)
    if not text:
        return MarkdownSafePartial("", "")
    if complete:
        return MarkdownSafePartial(text, "")
    cut = _first_held_index(text)
    if cut >= len(text):
        return MarkdownSafePartial(text, "")
    if cut <= 0:
        return MarkdownSafePartial("", text)
    return MarkdownSafePartial(text[:cut], text[cut:])


def render_markdown_safe(source: str, *, complete: bool = False) -> str:
    """Safe prefix of a (possibly incomplete) markdown stream."""
    return markdown_safe_partial(source, complete=complete).visible


__all__ = [
    "MarkdownSafePartial",
    "markdown_safe_partial",
    "render_markdown_safe",
]
