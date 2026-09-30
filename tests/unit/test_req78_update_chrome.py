"""REQ-78 (#423) chrome contracts: XOR update/info right of system name.

The XOR decision itself is no longer pinned here. It used to be four
independent substring checks against ``UpdateChrome.tsx`` and ``spaUpdate.ts``
(``"kind === 'local'"``, ``"kind === 'upstream'"``, ``"if (localMismatch)"``,
``"if (upstreamNewer)"``) — all of which keep passing if the branch logic is
inverted, because each one only proves a token exists somewhere in the file.
The behaviour is asserted by rendering and by calling:

* ``webui/frontend/src/lib/__tests__/spaUpdate.test.ts`` calls the decision
  function for every combination — match, SPA mismatch only, GitHub newer
  only, both, and GitHub unreachable — and asserts the resulting kind and the
  ``alsoUpstream`` flag, which is the XOR itself.
* ``webui/frontend/src/components/__tests__/UpdateChrome.test.tsx`` renders
  the chrome for each state and asserts the rendered label, class, and which
  target a click opens.

What was here and was worse than nothing
-----------------------------------------
``assert "No tokens" in src`` pinned a phrase that lives in the module's
*docstring*. The test was green because the prose describing the rule survived,
not because anything enforced it. A developer could add a credential and leave
the docstring alone and the test would pass; a developer could reword the
docstring and the test would fail. It is now a negative check on the things
that would actually leak a credential, and the positive direction lives in the
render tests above.
"""

from pathlib import Path

from helpers.css_rules import read_css, rule_bodies
from helpers.py_ast import await_sites, defined_names, parse_module, string_constants

REPO = Path(__file__).resolve().parents[2]
SIDEBAR = REPO / "webui/frontend/src/components/AgentSidebar.tsx"
CSS = REPO / "webui/frontend/src/index.css"
CONSUMERS = REPO / "src/swarm/consumers.py"
CHAT_WS = REPO / "webui/frontend/src/lib/chatWs.ts"


def test_update_chrome_sits_right_of_system_name_not_on_server_icon():
    """Placement: server icon → hostname → update chrome, left to right.

    The ordering assertion is positional, so it survives class-name churn; the
    colour assertions are scoped to the two chrome states' own rules rather
    than matched anywhere in the sheet, where a palette retune on an unrelated
    element used to be able to satisfy them.
    """

    sidebar = SIDEBAR.read_text(encoding="utf-8")
    hostname_idx = sidebar.index('id="os-rail-hostname"')
    chrome_idx = sidebar.index("<UpdateChrome />")
    server_idx = sidebar.index('data-testid="rail-server-icon"')
    assert server_idx < hostname_idx < chrome_idx, (
        "REQ-78 order is server icon, then hostname, then the update chrome"
    )

    css = read_css(CSS)
    for state, css_class in (
        ("local", "os-rail-update-chrome--local"),
        ("upstream", "os-rail-update-chrome--upstream"),
    ):
        bodies = [
            b
            for b in rule_bodies(css, f".{css_class}")
            if "color" in b or "background" in b
        ]
        assert bodies, f".{css_class} declares no colour — the {state} state is unstyled"
    # The two states must be visually distinct, which is the point of XOR.
    local_colour = next(
        b.split("color:")[1].split(";")[0].strip()
        for b in rule_bodies(css, ".os-rail-update-chrome--local")
        if "color:" in b
    )
    upstream_colour = next(
        b.split("color:")[1].split(";")[0].strip()
        for b in rule_bodies(css, ".os-rail-update-chrome--upstream")
        if "color:" in b
    )
    assert local_colour != upstream_colour, (
        "local and upstream chrome are the same colour, so the state is unreadable"
    )


def test_github_call_home_is_public_and_tokenless():
    """The call-home is public and unauthenticated.

    Kept as a *negative* check, because that is the one direction a source read
    can be trusted for: nothing in the module may reach for a credential. The
    positive direction — that the URLs point at the public repo and that no
    header is sent — is asserted where it can be observed:

    * ``webui/frontend/src/lib/__tests__/githubReleaseRepo.test.ts`` pins the
      default public slug and the derived Issues/Releases/API URLs.
    * ``webui/frontend/src/lib/__tests__/githubRelease.test.ts`` drives
      ``fetchLatestGithubRelease`` against a stubbed ``fetch`` and asserts the
      recorded headers carry no ``authorization`` and no ``token``.

    What the old assertions could not catch: a credential introduced as
    ``credentials: 'include'`` or under a custom header name satisfies every
    substring check here; the header assertion in the frontend test is what
    actually fails. What the old assertions *did* catch that the frontend tests
    do not: a token read straight off an env var, which never reaches a test's
    stubbed ``fetch`. Both directions are kept, each where it is honest.
    """
    src = (REPO / "webui/frontend/src/lib/githubRelease.ts").read_text(encoding="utf-8")
    # Credential reads, not the phrase "No tokens" in the docstring.
    for forbidden in ("GITHUB_TOKEN", "Authorization", "Bearer ", "GITHUB_PAT"):
        assert forbidden not in src, (
            f"githubRelease.ts references {forbidden!r}; the call-home must stay public "
            "and unauthenticated"
        )
    assert "https://api.github.com/repos/" in src
    assert "https://" in src


def test_backend_advertises_spa_hello_on_authenticated_connect():
    """The socket greets an authenticated SPA with its own version.

    The Python side is an AST read: the hello type is a module constant and the
    handshake is a real call site, so the pin no longer breaks when the constant
    moves or the method is reformatted — and, more to the point, it no longer
    passes when the phrase survives in a comment.
    """
    module = parse_module(CONSUMERS)
    assert "SPA_HELLO_TYPE" in defined_names(module), "the hello type constant is gone"
    assert "spa_hello" in string_constants(module), "the hello type no longer names spa_hello"

    assert await_sites(module, "connect"), "connect() no longer awaits anything — the handshake is gone"

    ws = CHAT_WS.read_text(encoding="utf-8")
    assert "'spa_hello'" in ws or '"spa_hello"' in ws, (
        "the SPA client no longer handles the spa_hello frame, so the version "
        "handshake silently degrades"
    )
