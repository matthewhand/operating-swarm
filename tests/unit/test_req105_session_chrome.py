"""REQ-105 chrome contracts: rail Select / New session, shared picker chrome.

Two of the checks below used to be unfailable — `A or B` where `A` alone is
already truthy, so the expression was constant. Both were replaced with the
property the comment actually claimed, not with a differently-shaped no-op.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
PICKER = REPO / "webui" / "frontend" / "src" / "components" / "SessionPicker.tsx"
SESSIONS = REPO / "webui" / "frontend" / "src" / "lib" / "agentSessions.ts"
RAIL_MENU = REPO / "webui" / "frontend" / "src" / "lib" / "railContextMenu.ts"

# The module that actually browses a CLI provider's own session list. Naming it
# is the point: "does not list CLI provider sessions" is only checkable against
# the thing that does it.
CLI_SESSIONS_MODULE = "lib/cliSessions"


def test_rail_menu_has_select_and_new_session_for_agents():
    src = SIDEBAR.read_text(encoding="utf-8")
    menu = RAIL_MENU.read_text(encoding="utf-8")
    assert "Select session" in menu
    assert "New session" in menu
    assert "'new-session'" in menu
    # #580: one declared capability (seatCapabilities.seatHasSessions) drives
    # the rail menu AND the navbar — the per-kind booleans were folded away.
    assert "seatHasSessions" in src
    # #1726: the subject is `seat` — the SEAT the row belongs to — not `menu`.
    # A chat row (#1726) is a session whose rail id is `chat:<seat>:<session>`,
    # and the session store it lives in is the seat's, so the predicate has to
    # be asked about the seat.
    assert "hasSelectSession: seatHasSessions(seat)" in src
    assert "hasNewSession: seatHasSessions(seat)" in src
    # The old pin above could not fail on a wrong SUBJECT, and the wrong
    # subject is exactly the regression it missed: `seat` is a projection of
    # the two fields the predicate reads, so a catalog row's own `kind` (a
    # rail grouping such as 'design'/'subagent', not a seat kind) can no
    # longer answer and silently strip the items from a seat that has them.
    assert "const seat = useMemo(" in src
    assert "seatHasSessions(menu)" not in src
    assert "openAgentSessionPicker" in src
    # Teams/remotes keep Select Agent; do not pretend we own remote stores.
    assert "Select Agent" in menu
    assert "hasSelectAgent" in src
    assert "openCliSessionPicker" in src
    assert "startNew: true" in src


def test_session_picker_keeps_shared_chrome_and_new_session():
    src = PICKER.read_text(encoding="utf-8")
    assert "os-session-picker" in src
    assert "onNewSession" in src
    assert "New session" in src
    assert "sessionRelativeLabel" in src
    assert "no sessions yet" in src


def test_session_picker_renders_rows_it_is_handed_and_never_fetches():
    """#468 may reuse chrome; this file must not list CLI provider sessions.

    The old assertion was::

        assert "provider" not in src.lower() or "CLI provider" not in src

    It could not fail, twice over. ``"provider" not in src.lower()`` has been
    ``False`` since #1353 gave the picker a ``provider`` prop, so ``or``
    short-circuited to the second operand — and ``"CLI provider" not in src``
    is a check for a literal English phrase in a ``.tsx`` file, which nothing
    ever puts there. Both operands were doing no work.

    The property is real and is now stated as the mechanism that actually
    implements it: the picker is presentational. It receives its rows on props
    and narrows them with a pure filter. It has no network call of its own, so
    there is nothing in it that *could* browse a CLI provider's session list.
    Every assertion below fails if a fetch or a ``cliSessions`` import appears.
    """
    src = PICKER.read_text(encoding="utf-8")

    # 1. It imports no module that lists sessions over the network. The
    #    rail's own CLI provider browser is lib/cliSessions (fetchCliSessions);
    #    the Django row lister is lib/agentSessions. Both are absent.
    imports = re.findall(r"from\s+'([^']+)'", src)
    assert CLI_SESSIONS_MODULE not in " ".join(imports), (
        f"SessionPicker imports {CLI_SESSIONS_MODULE}; it must render the rows it "
        f"is handed, not browse a CLI provider's session list. imports={imports}"
    )
    assert "lib/api" not in " ".join(imports), (
        f"SessionPicker imports the API client; it must not fetch. imports={imports}"
    )

    # 2. It makes no request of its own, by any spelling.
    for banned in ("apiGet(", "apiPost(", "apiPut(", "apiDelete(", "fetch(", "XMLHttpRequest"):
        assert banned not in src, (
            f"SessionPicker calls {banned}; the picker must be presentational. "
            "Rows arrive on props and the page owns every request."
        )

    # 3. `provider` is a narrowing filter over the handed-in rows, not a source
    #    of them -- this is what the old `"provider" not in src` was groping for.
    assert "filterSessionsByProvider" in src, (
        "SessionPicker must scope its rows with filterSessionsByProvider; the "
        "provider prop is a filter, not a fetcher"
    )
    assert "lib/sessionPicker" in " ".join(imports), (
        f"filterSessionsByProvider is expected to come from lib/sessionPicker. "
        f"imports={imports}"
    )

    # 4. The rows still come in on props, so the narrowing cannot be bypassed
    #    by the picker quietly substituting its own list.
    assert re.search(r"sessions\s*[:,]", src), (
        "SessionPicker must take its rows from a `sessions` prop"
    )


def test_django_session_client_does_not_list_cli_providers():
    src = SESSIONS.read_text(encoding="utf-8")
    assert "/v1/agents/" in src
    assert "sessions/" in src
    assert "new: true" in src
    assert "cli-agents" not in src


def test_django_session_client_only_talks_to_the_django_sessions_endpoint():
    """The Django row lister talks to exactly one endpoint — exhaustively.

    The old assertion was::

        assert "provider" not in src.lower() or "does not browse CLI provider" in src

    It could not fail, and worse, it was satisfied by its own documentation.
    ``"provider" not in src.lower()`` is ``False`` — the module's own header
    comment contains the word — so ``or`` handed the decision to
    ``"does not browse CLI provider" in src``, and that sentence is *literally
    the docstring at the top of the file*. The assertion was checking that the
    promise is written down, not that the code keeps it. Deleting the whole
    CLI session browser from this module, or adding a call to it, would have
    left it green.

    The property is real, so it is asserted by enumerating every URL literal
    the module can issue and pinning the set. A new endpoint anywhere in the
    file — a CLI session list, a remote thread list — fails this.
    """
    src = SESSIONS.read_text(encoding="utf-8")

    # Every ``/v1/...`` string the module can send. An exhaustive enumeration,
    # not a spot check: adding a second endpoint is what makes this fail.
    endpoints = sorted(set(re.findall(r"[\`'\"](/v1/[^\`'\"]*)", src)))
    assert endpoints == ["/v1/agents/${encodeURIComponent(agent)}/sessions/"], (
        "agentSessions.ts may only read/write the Django agent-sessions rows; "
        f"found other endpoints: {endpoints}"
    )

    # And the reason that set matters: the module that browses a CLI provider's
    # own sessions is not among its imports.
    imports = re.findall(r"from\s+'([^']+)'", src)
    assert CLI_SESSIONS_MODULE not in " ".join(imports), (
        f"agentSessions.ts imports {CLI_SESSIONS_MODULE}, the CLI provider "
        f"session browser. imports={imports}"
    )
    assert sorted(imports) == [
        "./agentChat",
        "./api",
        "./chatTime",
        "./scaleOutSessions",
    ], (
        "agentSessions.ts gained an import; every new module is a new way to "
        f"reach a store it does not own. imports={sorted(imports)}"
    )

    # The behavioural half of this contract lives in the SPA suite and is
    # stronger than any source pin, so cite it rather than duplicate it:
    # webui/frontend/src/lib/__tests__/agentSessions.test.ts asserts the exact
    # request URL for both the list (`fetchAgentSessions`) and the create
    # (`createAgentSession`, with body { new: true, empty: true }). What it
    # does not cover is a *third* function added later -- that is the gap the
    # enumeration above closes.
