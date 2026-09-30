"""REQ-127: Codeblock copy/paste keeps newlines; user fences render (Fixes #517).

Split by what kind of property each half is.

The stylesheet half
-------------------
``white-space: pre-wrap`` and ``resize: none`` genuinely are stylesheet facts —
no render can observe them, because jsdom does not load ``index.css``. But the
old check was ``assert "white-space: pre-wrap" in css``, which is satisfied by
*any* of the four ``white-space: pre-wrap`` declarations in the 6,400-line
sheet, including a routine dry-run card's. It is now read off the rule that
owns the composer's input, so a reformat or an unrelated new ``pre-wrap`` cannot
satisfy it and a regression in the composer's own rule still fails.

The component half
------------------
``assert 'aria-label="Chat message"' in page`` was checking a *spelling*. The
same string is emitted as ``'aria-label': 'Chat message',`` inside the props
object in ``ChatBottomDock.tsx`` — an object key is not an attribute, so the
pin went red the moment the composer moved out of ``ChatPage`` and started
receiving its props as an object. The behaviour is now asserted by querying the
rendered composer by its accessible name, which is what a screen reader does:
fifteen render suites already do exactly that
(``getByRole('textbox', { name: 'Chat message' })``), and
``components/__tests__/ChatMessageInput.test.tsx`` asserts it is a
``<textarea>`` that forwards its props.

The keyboard contract
---------------------
The old ``assert "Shift+Enter" in page or "shiftKey" in page`` was the worst
form of the family: an ``or`` of two spellings, satisfiable by the substring
``shiftKey`` appearing anywhere in six thousand lines. Shift+Enter must insert
a newline and must *not* send. That is now asserted by firing the key:

``webui/frontend/src/pages/__tests__/ChatComposerEnterShift127.test.tsx``
renders ``ChatPage``, types a draft, presses Shift+Enter, and asserts the
handler did not ``preventDefault`` (so the browser inserts the newline) and no
send frame reached the socket — then presses Enter and asserts the send *does*
happen and *does* preventDefault. A handler that sent on Shift+Enter, or one
that swallowed the newline, fails both halves.

Markdown and clipboard
----------------------
``renderSafeMarkdown``, ``<pre``, ``navigator.clipboard?.writeText`` and
``code-copy`` were four more spelling pins. The behaviour is asserted by
calling the functions: ``lib/__tests__/markdown.test.ts`` renders a fenced
Python block and asserts the ``pre``/``code`` output with the newlines intact,
and ``lib/__tests__/clipboard.test.ts`` asserts a fenced block reaches
``navigator.clipboard.writeText`` with its real newlines, plus the
``execCommand`` fallbacks.
"""

from pathlib import Path

from helpers.css_rules import declaration, read_css

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
MARKDOWN = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "markdown.ts"
CLIPBOARD = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "clipboard.ts"

COMPOSER_INPUT = ".os-composer__input"


def test_composer_input_keeps_newlines_and_is_not_user_resizable():
    """Newlines survive in the composer; the user cannot drag a resize grip.

    Scoped to the composer's own rule. The old check was a whole-file substring,
    which four unrelated ``white-space: pre-wrap`` declarations could satisfy.
    """
    css = read_css(CSS)
    white_space = declaration(css, COMPOSER_INPUT, "white-space")
    assert white_space == "pre-wrap", (
        f"{COMPOSER_INPUT} sets white-space: {white_space!r}; a pasted "
        "multi-line block would collapse onto one line"
    )
    assert declaration(css, COMPOSER_INPUT, "resize") == "none", (
        "the composer grew a resize grip, which re-flows the rail when dragged"
    )
    # The ghost overlay that mirrors the draft must wrap identically, or the
    # autocomplete suggestion drifts out of alignment with the real text.
    assert declaration(css, ".os-composer-ghost", "white-space") == "pre-wrap", (
        "the autocomplete ghost does not wrap like the input it mirrors"
    )


def test_markdown_renders_fences_and_the_clipboard_keeps_their_newlines():
    """Both modules still exist and still export the seam the bubble uses.

    This is deliberately the weakest form left in the file: an export-name
    check. It is here only because the *behaviour* — a fenced block rendering
    as ``pre``/``code`` with its newlines intact, and reaching the clipboard
    unchanged — is asserted by importing and calling the functions in
    ``lib/__tests__/markdown.test.ts`` and ``lib/__tests__/clipboard.test.ts``,
    which is strictly stronger than reading their source. Re-deriving it here
    would be the same defect one layer down.
    """
    markdown = MARKDOWN.read_text(encoding="utf-8")
    assert "export function renderSafeMarkdown" in markdown, (
        "markdown.ts no longer exports renderSafeMarkdown; the bubble has no render seam"
    )
    clipboard = CLIPBOARD.read_text(encoding="utf-8")
    assert "export async function" in clipboard or "export function" in clipboard, (
        "clipboard.ts no longer exports a copy function"
    )
