"""One rule set, two runtimes: the TS mirror may not drift from the Python source (#1669).

#1410 shipped the tool-suggestion rules twice — once in
``src/swarm/core/routine_tool_suggestions.py`` and once, hand-typed, in
``webui/frontend/src/lib/routineToolSuggestions.ts``. The issue filed against
that said the Python copy was dead code; by the time #1669 was worked it was
not — #1454 wired ``rank_tools_by_confidence`` to
``GET /v1/routines/tool-catalog/?instruction=`` — so the *TS* file is the
duplicate. Neither copy can simply be deleted:

* Python owns the rule set and the ranker, and has a production importer.
* The composer calls ``visibleToolSuggestions`` in a ``useMemo`` with no
  network, and ``routineToolCatalog.ts`` needs ``SUGGESTABLE_TOOL_LABELS``
  synchronously, so the browser needs its own copy of two regexes.

That leaves the honest failure mode: two hand-maintained copies silently
disagreeing, and the tests still pass on both sides. So parity is *enforced*
here instead of merely intended. These tests parse the TypeScript rule table
out of the mirror's source and diff it, rule for rule and regex for regex,
against the imported Python table. Add a rule on one side only, change a
pattern on one side only, or drop a negation — the backend suite goes red.

They also pin the boundaries of the split, because the drift that actually
bites is not the rules, it is the *layer* each side grows:

* the mirror must not grow a confidence ranker — that is Python's job (#1454);
* the mirror must not grow an apply/confirm mutator — ``RoutineToolsFields``
  does the dedupe, and a second confirm gate is a second thing to get wrong;
* no other module under ``src/`` may re-declare the rules, which is how the
  original duplication would come back;
* both copies must keep a production importer, so this cannot be "resolved" by
  quietly orphaning either one (the defect #1454 was filed for);
* the pointer docstring in ``routine_tools.py`` must name the survivor.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from swarm.core.routine_tool_suggestions import (
    DESTRUCTIVE_ROUTINE_TOOLS,
    SUGGESTABLE_TOOL_LABELS,
    SUGGESTION_RULES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITATIVE = REPO_ROOT / "src/swarm/core/routine_tool_suggestions.py"
FRONTEND_LIB = REPO_ROOT / "webui/frontend/src/lib"
MIRROR = FRONTEND_LIB / "routineToolSuggestions.ts"
ROUTINES_TS = FRONTEND_LIB / "routines.ts"
VIEW = REPO_ROOT / "src/swarm/views/routines_api.py"

#: Fragments unique to this rule set. Used to detect a *third* declaration of
#: the rules, which the exact-parity tests above cannot see because they only
#: compare these two files.
RULE_TABLE_FINGERPRINTS = (
    r"pull[\s-]?request",
    r"recall\s+(?:prior|previous|past)",
    r"memor(?:y|ies)|remember",
)


# --- TypeScript source scanning --------------------------------------------
#
# The mirror keeps its patterns as string sources and compiles them with 'i'
# (the Python table stores raw sources and compiles with re.IGNORECASE) so the
# two can be compared as text. That makes the module parseable here without a
# TS toolchain, which matters: this guard has to run in the backend suite.

_LITERAL_RE = re.compile(r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'|\"[^\"\\\n]*(?:\\.[^\"\\\n]*)*\"")
_TOOL_CONST_RE = re.compile(r"export\s+const\s+(TOOL_\w+)\s*=\s*'([^']*)'")
_RULE_CALL_RE = re.compile(r"\brule\s*\(")


def _strip_comments(text: str) -> str:
    """Blank out comments, preserving offsets so spans stay indexable."""
    out = list(text)
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end == -1 else end
            for pos in range(index, end):
                out[pos] = " "
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = length if end == -1 else end + 2
            for pos in range(index, end):
                if out[pos] != "\n":
                    out[pos] = " "
            index = end
            continue
        index += 1
    return "".join(out)


def _match_bracket(text: str, open_index: int) -> int:
    """Index of the bracket closing the one at ``open_index``."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = [text[open_index]]
    index = open_index + 1
    length = len(text)
    while index < length:
        char = text[index]
        if char in "'\"":
            match = _LITERAL_RE.match(text, index)
            if match is None:  # unbalanced quote — let the exact-parity assert speak
                raise AssertionError(f"unterminated string literal at offset {index} in {MIRROR.name}")
            index = match.end()
            continue
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            assert stack and stack[-1] == pairs[char], f"unbalanced {char} in {MIRROR.name}"
            stack.pop()
            if not stack:
                return index
        index += 1
    raise AssertionError(f"unclosed bracket at offset {open_index} in {MIRROR.name}")


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are not inside a string or a nested bracket."""
    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "'\"":
            match = _LITERAL_RE.match(text, index)
            assert match is not None, f"unterminated string literal in {MIRROR.name}"
            index = match.end()
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return [part.strip() for part in parts]


def _literals(fragment: str) -> list[str]:
    """Decode every string literal in ``fragment`` (TS quoting is Python's)."""
    return [ast.literal_eval(match.group(0)) for match in _LITERAL_RE.finditer(fragment)]


def _tool_constants() -> dict[str, str]:
    return {name: value for name, value in _TOOL_CONST_RE.findall(ROUTINES_TS.read_text())}


def _mirror_destructive() -> set[str]:
    """Ids the mirror flags destructive, with TOOL_* constants resolved."""
    code = _strip_comments(MIRROR.read_text())
    declaration = re.search(r"\bDESTRUCTIVE_ROUTINE_TOOLS\b[^=]*=", code)
    assert declaration is not None, "the mirror no longer declares DESTRUCTIVE_ROUTINE_TOOLS"
    array_start = code.index("[", declaration.end())
    body = code[array_start + 1 : _match_bracket(code, array_start)]
    constants = _tool_constants()
    ids: set[str] = set()
    for item in _split_top_level(body):
        if item.startswith(("'", '"')):
            ids.add(_literals(item)[0])
        else:
            assert item in constants, f"unresolved tool id {item!r} in {MIRROR.name}"
            ids.add(constants[item])
    return ids


def _mirror_rules() -> list[dict[str, object]]:
    """Parse the mirror's ``SUGGESTION_RULES`` into the Python rule shape.

    ``destructive`` is resolved here, exactly as ``rule()`` resolves it in the
    source of truth: an explicit argument wins, otherwise membership of
    DESTRUCTIVE_ROUTINE_TOOLS decides. That makes the flag a real comparison
    rather than a constant on both sides.
    """
    code = _strip_comments(MIRROR.read_text())
    declaration = re.search(r"\bSUGGESTION_RULES\b[^=]*=", code)
    assert declaration is not None, "routineToolSuggestions.ts no longer declares SUGGESTION_RULES"
    array_start = code.index("[", declaration.end())
    body = code[array_start + 1 : _match_bracket(code, array_start)]

    constants = _tool_constants()
    destructive_ids = _mirror_destructive()
    rules: list[dict[str, object]] = []
    for call in _RULE_CALL_RE.finditer(body):
        open_paren = call.end() - 1
        args = _split_top_level(body[open_paren + 1 : _match_bracket(body, open_paren)])
        assert len(args) in (4, 5, 6), f"rule() takes 4-6 args, got {len(args)} in {MIRROR.name}"

        tool_id = args[0].strip()
        if tool_id.startswith(("'", '"')):
            tool_id = _literals(tool_id)[0]
        else:
            assert tool_id in constants, f"unresolved tool id {tool_id!r} in {MIRROR.name}"
            tool_id = constants[tool_id]

        rules.append(
            {
                "id": tool_id,
                "label": _literals(args[1])[0],
                "reason": _literals(args[2])[0],
                "patterns": _literals(args[3]),
                "negations": _literals(args[4]) if len(args) >= 5 else [],
                "destructive": (
                    args[5] == "true" if len(args) == 6 else tool_id in destructive_ids
                ),
            }
        )
    assert rules, "no rule() calls found in the mirror's SUGGESTION_RULES"
    return rules


def _python_rules() -> list[dict[str, object]]:
    return [
        {
            "id": rule["id"],
            "label": rule["label"],
            "reason": rule["reason"],
            "patterns": [pattern.pattern for pattern in rule["patterns"]],
            "negations": [negation.pattern for negation in rule["negations"]],
            "destructive": bool(rule["destructive"]),
        }
        for rule in SUGGESTION_RULES
    ]


# --- the invariant ---------------------------------------------------------


def test_the_mirror_rule_table_matches_the_python_source_of_truth():
    """The load-bearing check: one side edited, both sides stay green -> fail."""
    assert _mirror_rules() == _python_rules()


def test_the_mirror_parses_at_all():
    """A parser that silently found nothing must not read as parity."""
    mirrored = _mirror_rules()
    assert len(mirrored) == len(SUGGESTION_RULES)
    assert [row["id"] for row in mirrored] == [str(rule["id"]) for rule in SUGGESTION_RULES]


def test_destructive_ids_agree_across_the_split():
    """A tool the backend treats as destructive must be destructive in the UI too."""
    assert _mirror_destructive() == set(DESTRUCTIVE_ROUTINE_TOOLS)
    assert _mirror_destructive() == {"open_pull_request", "write_file"}


def test_slack_is_not_invented_by_either_copy():
    """Both copies refuse to invent a `slack` id (#1410): there is no such tool.

    Asserted on the rule tables, not on source text — both modules *document*
    that they refuse it, so a substring search would only match the prose.
    """
    for label, rules in (("python", _python_rules()), ("mirror", _mirror_rules())):
        ids = [str(row["id"]) for row in rules]
        assert "slack" not in {tid.lower() for tid in ids}, f"{label} invented a slack tool id"
    assert "slack" not in {key.lower() for key in SUGGESTABLE_TOOL_LABELS}


def test_suggestable_labels_agree():
    mirrored = {str(row["id"]): str(row["label"]) for row in _mirror_rules()}
    assert mirrored == SUGGESTABLE_TOOL_LABELS
    # routineToolCatalog.ts resolves picker labels through this map.
    catalog = (FRONTEND_LIB / "routineToolCatalog.ts").read_text()
    assert "SUGGESTABLE_TOOL_LABELS" in catalog


# --- the boundaries of the split ------------------------------------------


def test_the_mirror_does_not_reimplement_the_ranker():
    """#1454's scorer has one home. A second one is the drift we are preventing."""
    code = _strip_comments(MIRROR.read_text())
    for symbol in ("confidence", "scorer", "rank_tools", "lexical_tool_confidence"):
        assert symbol not in code, f"the TS mirror grew a {symbol!r}; the ranker is Python-only"


def test_the_mirror_exposes_no_mutator_and_only_the_needed_exports():
    """Suggestions are read-only. #1410's `applySuggestedTool` twin was dead."""
    exported = set(
        re.findall(
            r"^export\s+(?:async\s+)?(?:function|const|interface|type|class)\s+(\w+)",
            _strip_comments(MIRROR.read_text()),
            re.MULTILINE,
        )
    )
    assert exported == {
        "RoutineToolSuggestion",
        "SUGGESTABLE_TOOL_LABELS",
        "instructionFingerprint",
        "visibleToolSuggestions",
    }


def test_no_other_module_redeclares_the_rules():
    """How the original duplication comes back: a third copy, in Python."""
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src/swarm").rglob("*.py")):
        if path == AUTHORITATIVE:
            continue
        text = path.read_text()
        hits = [fp for fp in RULE_TABLE_FINGERPRINTS if fp in text]
        if hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)} ({len(hits)} fingerprints)")
    assert not offenders, (
        "the #1410 rule set is re-declared outside the source of truth: " + "; ".join(offenders)
    )


def test_the_python_module_owns_the_rules():
    """Cheap tripwire: if the authoritative file is renamed or gutted, fail loudly."""
    assert "Single source of truth" in AUTHORITATIVE.read_text()
    assert "1669" in AUTHORITATIVE.read_text()


# --- neither copy may be silently orphaned ---------------------------------


def test_both_copies_keep_a_production_importer():
    """Deleting a caller is not a fix. The defect #1454 was filed for was orphaning."""
    assert "routine_tool_suggestions" in VIEW.read_text(), "the ranker lost its production importer"

    importers = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "webui/frontend/src").rglob("*.ts*")
        if "routineToolSuggestions" in path.read_text() and path != MIRROR
    ]
    assert importers, "the TS mirror has no importer — the composer would be silently undecorated"
    assert any("RoutineToolSuggestions.tsx" in name for name in importers)


def test_the_pointer_docstring_names_the_survivor():
    """routine_tools.py tells readers where missing-tool detect lives."""
    tools_source = (REPO_ROOT / "src/swarm/core/routine_tools.py").read_text()
    pointer = re.search(r"Missing-tool\s*\n?\s*detect lives in ``(\w+)``", tools_source)
    assert pointer is not None, "the missing-tool detect pointer docstring is gone"
    assert pointer.group(1) == "routine_tool_suggestions"
