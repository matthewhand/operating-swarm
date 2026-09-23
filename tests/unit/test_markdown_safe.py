"""#220 — markdown-safe partial rendering (Python helper used by the TUI)."""

from swarm.tui.markdown_safe import markdown_safe_partial, render_markdown_safe

SAMPLES = [
    "",
    "hello",
    "hello **world",
    "hello **world**",
    "a *b",
    "`code",
    "```python\nprint(1)",
    "[docs](https://example.com",
    "plain [not a link]",
    "hello **world *foo",
    "- item **bold\n- still",
]


def test_never_drops_text_visible_plus_held_equals_source():
    for source in SAMPLES:
        visible, held = markdown_safe_partial(source)
        assert visible + held == source
        flushed = markdown_safe_partial(source, complete=True)
        assert flushed == (source, "")


def test_holds_unclosed_bold_italic_and_code():
    assert markdown_safe_partial("hello **wor") == ("hello ", "**wor")
    assert markdown_safe_partial("hello **world**") == ("hello **world**", "")
    assert markdown_safe_partial("hello *wor") == ("hello ", "*wor")
    assert markdown_safe_partial("hello `cod") == ("hello ", "`cod")
    assert markdown_safe_partial("hello `code`") == ("hello `code`", "")


def test_nested_constructs_stop_at_outer_unclosed_opener():
    assert markdown_safe_partial("hello **world *foo") == ("hello ", "**world *foo")
    assert markdown_safe_partial("hello **world *foo* bar**") == (
        "hello **world *foo* bar**",
        "",
    )


def test_metacharacters_inside_inline_code_are_ignored():
    assert markdown_safe_partial("use `**not bold**` please") == (
        "use `**not bold**` please",
        "",
    )
    assert markdown_safe_partial("use `**not") == ("use ", "`**not")


def test_fence_language_tag_held_until_closed():
    open_fence = "```python\nprint(1)"
    assert markdown_safe_partial(open_fence) == ("", open_fence)
    closed = "```python\nprint(1)\n```"
    assert markdown_safe_partial(closed) == (closed, "")
    assert markdown_safe_partial("intro\n```js\nconst x = 1") == (
        "intro\n",
        "```js\nconst x = 1",
    )


def test_constructs_spanning_list_items():
    partial = "- item **bold\n- still"
    assert markdown_safe_partial(partial) == ("- item ", "**bold\n- still")
    balanced = "- item **bold\n- still** done"
    assert markdown_safe_partial(balanced) == (balanced, "")


def test_incomplete_link_held_until_dest_closes():
    assert markdown_safe_partial("See [docs](https://example.com") == (
        "See ",
        "[docs](https://example.com",
    )
    assert markdown_safe_partial("plain [not a link]") == ("plain [not a link]", "")


def test_stream_end_flushes_unclosed_constructs():
    assert render_markdown_safe("hello **world", complete=True) == "hello **world"
    assert render_markdown_safe("```python\nprint(1)", complete=True) == (
        "```python\nprint(1)"
    )
    assert render_markdown_safe("See [docs](https://x", complete=True) == (
        "See [docs](https://x"
    )


def test_list_marker_star_is_not_italic():
    assert markdown_safe_partial("* item one") == ("* item one", "")
