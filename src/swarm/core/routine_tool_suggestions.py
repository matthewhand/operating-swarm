"""Heuristic missing-tool suggestions from routine instructions (#1410).

Scans Agent Instructions (and optionally a GitHub ``pull_request`` trigger)
for implied capabilities. Returns canned, token-free suggestions for tools
that are not already on the routine.

Never auto-enables a tool. Destructive ids (Open Pull Request,
``write_file``) require an explicit operator confirm before they join
``tools``. Suggestion copy is always a canned template — instruction
excerpts and token-shaped strings never appear in the payload.
Slack is not suggested: there is no routine tool id for it, and a
made-up ``slack`` slug would be handed to the plugin allowlist.

Single source of truth (#1669)
------------------------------
**This module owns the rule set.** #1410 shipped the same two rules a second
time in ``webui/frontend/src/lib/routineToolSuggestions.ts``; #1669 demoted
that file to a *mirror* of the ``SUGGESTION_RULES`` table below and nothing
else. The mirror has to exist — the composer needs an answer per keystroke
and ``routineToolCatalog.ts`` needs a label map synchronously — but it is
checked, not trusted: ``tests/core/test_routine_tool_suggestions_single_source_1669.py``
parses it and diffs it rule-for-rule against this module, so a one-sided edit
to either file fails the backend suite. It also asserts the destructive-id set
matches, and that the mirror never grows its own ranker or its own
apply/confirm mutator (which is the drift direction that actually bit).

Consequences for editors: change a pattern or a reason HERE first, then
mirror it. The ranking layer below lives here and only here.

#1454 adds the *ranking* layer used when the catalog is large (1000+
plugin/MCP/built-in rows). Handing a small on-device or WebGPU model a flat
catalog of 1000 tools is counter-productive, so the builder shortlists by
confidence instead of dumping instructions. The layer is deliberately split:

* :func:`lexical_tool_confidence` — the default scorer. Pure: no network, no
  LLM, no clock, no I/O, no randomness. Same input -> same output, so it is
  exhaustively unit-testable.
* :func:`rank_tools_by_confidence` — ordering, pinning and truncation. It takes
  an optional injected ``scorer`` so a local/browser model (cactus-needle, a
  CLM-0.1-class WebGPU model, …) can supply confidences later. An injected
  scorer can only reorder *inside* a band: it can never beat the explicit-name
  pin and it can never promote a destructive tool out of confirm.

What "confidence" actually is
-----------------------------
A **hand-weighted lexical-overlap score in [0, 1]** — not a calibrated
probability, and never produced by a language model here. Use it to shortlist,
never as "the model is 90% sure".

* ``1.00`` — the instructions *explicitly name* the tool: a #1410 rule matched,
  or the tool id / label appears as a contiguous phrase in the instructions.
* up to :data:`HEURISTIC_CEILING` (``0.90``) — everything else:
  ``id_coverage * 0.50 + label_coverage * 0.25 + description_coverage * 0.15``.
  The ceiling sits below ``1.00`` so a named tool always outranks a
  merely-high-scoring one.
* ``0.00`` — a negation cue within :data:`NEGATION_WINDOW` tokens before the
  match, or no overlap at all.

Limits, stated honestly:

* Purely lexical. Synonyms ("tweet" vs "post to the social account") and
  paraphrases are missed; an id like ``read`` over-matches any mention of the
  word.
* Coverage is an unweighted bag-of-words over the tool's own text, so a long
  description containing common words can lift a weak match.
* The weights are hand-set, not fitted and not cross-validated.
* The #1410 built-in hints are regexes, not semantics.
* ``catalog=None`` ranks nothing on purpose: composing the live catalog reads
  MCP/plugin state. Callers pass
  ``routine_tools.compose_routine_picker_catalog(config)``; when that is
  unavailable the graceful degrade is plain :func:`suggest_routine_tools`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from swarm.core.routine_tools import TOOL_MEMORIES, TOOL_OPEN_PULL_REQUEST

logger = logging.getLogger(__name__)

DESTRUCTIVE_ROUTINE_TOOLS = frozenset({TOOL_OPEN_PULL_REQUEST, "write_file"})

_TOKENISH_RE = re.compile(
    r"(ghp_|github_pat_|sk-|xai-|Bearer\s+[A-Za-z0-9._\-]{12,})",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_WORD_RE = re.compile(r"[a-z0-9]+")

# --- #1454 ranking weights. Hand-set, documented, not calibrated. ------------
NAMED_CONFIDENCE = 1.0
WEIGHT_ID_COVERAGE = 0.50
WEIGHT_LABEL_COVERAGE = 0.25
WEIGHT_DESCRIPTION_COVERAGE = 0.15
# Sum of the coverage weights. Strictly below NAMED_CONFIDENCE on purpose:
# "explicitly named beats merely high-scoring".
HEURISTIC_CEILING = round(
    WEIGHT_ID_COVERAGE + WEIGHT_LABEL_COVERAGE + WEIGHT_DESCRIPTION_COVERAGE, 2
)

#: Tokens that carry no topical signal in a tool id/label/description.
_STOPWORDS = frozenset(
    """
    a about all an and any are as at be been but by can cant did do does dont
    for from get gets give had has have how if in into is it its just like make
    may more most no nor not of off on once only or other our out over own per
    same should since so some such than that the their them then there these
    they this those through to too under until up use used using very via was
    way we were what when where which while who why will with without you your
    """.split()  # noqa: SIM905 - a word list reads better than 100 quoted lines
)

#: A negation cue suppresses matches that follow it within ``NEGATION_WINDOW``
#: raw tokens. ``don``/``dont`` cover "don't" ("t" is dropped as a 1-char token).
_NEGATION_CUES = frozenset(
    """
    not no never dont don cannot nothing without avoid skip
    """.split()  # noqa: SIM905 - a word list reads better than 10 quoted lines
)
NEGATION_WINDOW = 5

#: Canned copy. Instruction text is never interpolated into a reason.
NAMED_REASON = "Instructions name this tool — add it?"
MATCHED_REASON = "Ranks against these instructions — review before adding."

#: Bound what a model is ever shown. 1000+ rows x unbounded descriptions does
#: not fit a small on-device context window.
MAX_SCORER_DESCRIPTION = 200

ToolConfidenceScorer = Callable[[str, Sequence[Mapping[str, Any]]], Mapping[str, Any]]


def _rule(
    *,
    tool_id: str,
    label: str,
    reason: str,
    patterns: tuple[str, ...],
    negations: tuple[str, ...] = (),
    destructive: bool | None = None,
) -> dict[str, Any]:
    is_destructive = (
        DESTRUCTIVE_ROUTINE_TOOLS.__contains__(tool_id)
        if destructive is None
        else destructive
    )
    return {
        "id": tool_id,
        "label": label,
        "reason": reason,
        "patterns": tuple(re.compile(p, re.IGNORECASE) for p in patterns),
        "negations": tuple(re.compile(p, re.IGNORECASE) for p in negations),
        "destructive": is_destructive,
        "auto_enable": False,
    }


SUGGESTION_RULES: tuple[dict[str, Any], ...] = (
    _rule(
        tool_id=TOOL_OPEN_PULL_REQUEST,
        label="Open Pull Request",
        reason="Instructions mention opening a PR — add Open Pull Request?",
        patterns=(
            r"\bpull[\s-]?requests?\b",
            r"\bopen(?:ing)?\s+(?:a\s+|the\s+)?pr\b",
            r"\bcreate(?:ing)?\s+(?:a\s+|the\s+)?pr\b",
            r"\bgh\s+pr\b",
            r"\bprs?\b",
        ),
        negations=(
            r"\bdo\s+not\b[\s\S]{0,80}\b(?:pr|pull[\s-]?request)",
            r"\bdon'?t\b[\s\S]{0,80}\b(?:pr|pull[\s-]?request)",
            r"\bnever\b[\s\S]{0,80}\b(?:pr|pull[\s-]?request)",
            r"\bwithout\b[\s\S]{0,80}\b(?:pr|pull[\s-]?request)",
        ),
    ),
    _rule(
        tool_id=TOOL_MEMORIES,
        label="Memories",
        reason="Instructions mention memory — add Memories?",
        patterns=(
            r"\bmemories\b",
            r"\bmemory\b",
            r"\bprior\s+context\b",
            r"\brecall\s+(?:prior|previous|past)\b",
        ),
        negations=(
            r"\bdo\s+not\b[\s\S]{0,80}\b(?:memor(?:y|ies)|remember)",
            r"\bdon'?t\b[\s\S]{0,80}\b(?:memor(?:y|ies)|remember)",
        ),
    ),
)

SUGGESTABLE_TOOL_LABELS: dict[str, str] = {
    str(rule["id"]): str(rule["label"]) for rule in SUGGESTION_RULES
}


def scrub_suggestion_text(text: str) -> str:
    """Drop token-shaped substrings. Never copy secrets into suggestions."""
    return _TOKENISH_RE.sub("", str(text or ""))


def instruction_fingerprint(
    instruction: str, trigger: Mapping[str, Any] | None = None
) -> str:
    """Normalized scan text. Punctuation-only edits keep the same fingerprint."""
    raw = " ".join(part for part in (_scan_parts(instruction, trigger)) if part)
    lowered = scrub_suggestion_text(raw).lower()
    return _NON_ALNUM_RE.sub(" ", lowered).strip()


def _scan_parts(instruction: str, trigger: Mapping[str, Any] | None) -> list[str]:
    parts = [scrub_suggestion_text(str(instruction or ""))]
    incoming = trigger if isinstance(trigger, Mapping) else {}
    event_type = str(incoming.get("event_type") or "").strip().lower()
    # Optional trigger signal: a pull_request event implies opening/updating a PR.
    # Do not scan trigger.kind (github_pr_merged would false-positive).
    if event_type.startswith("pull_request"):
        parts.append("pull request")
    return parts


def _scan_text(instruction: str, trigger: Mapping[str, Any] | None) -> str:
    return " ".join(part for part in _scan_parts(instruction, trigger) if part)


def _rule_matches(rule: Mapping[str, Any], text: str) -> bool:
    if any(neg.search(text) for neg in rule["negations"]):
        return False
    return any(pat.search(text) for pat in rule["patterns"])


# --------------------------------------------------------------------------
# #1454 — deterministic ranking over a large catalog
# --------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    """Lowercase word tokens. Stopwords included — negation needs them."""
    return _WORD_RE.findall(str(text or "").lower())


def _content_tokens(tokens: Sequence[str]) -> list[str]:
    """Topical tokens: no stopwords, no 1-2 letter noise (numbers survive)."""
    return [t for t in tokens if t not in _STOPWORDS and (len(t) > 2 or t.isdigit())]


def _negated_region(raw_tokens: Sequence[str]) -> frozenset[int]:
    """Raw-token indices sitting inside a negation scope."""
    region: set[int] = set()
    for index, token in enumerate(raw_tokens):
        if token in _NEGATION_CUES:
            region.update(range(index + 1, index + 1 + NEGATION_WINDOW))
    return frozenset(region)


def _phrase_positions(content: Sequence[str], needle: Sequence[str]) -> list[int]:
    """Start indices where ``needle`` appears contiguously inside ``content``."""
    if not needle or len(needle) > len(content):
        return []
    width = len(needle)
    first = needle[0]
    return [
        start
        for start in range(len(content) - width + 1)
        if content[start] == first
        and list(content[start : start + width]) == list(needle)
    ]


def _title_case_tool_id(tool_id: str) -> str:
    return " ".join(
        part.capitalize() for part in re.split(r"[_\-\s.]+", tool_id) if part
    )


class _Text:
    """Pre-tokenized scan text.

    Built once per call so a 1000+ row catalog tokenizes the instruction (and
    resolves the negation scope) exactly once.
    """

    __slots__ = ("raw", "content", "bag", "negated", "_raw_at", "_content_at")

    def __init__(self, scan_text: str) -> None:
        self.raw: tuple[str, ...] = tuple(_tokens(scan_text))
        pairs = [
            (token, index)
            for index, token in enumerate(self.raw)
            if token not in _STOPWORDS and (len(token) > 2 or token.isdigit())
        ]
        self.content: tuple[str, ...] = tuple(token for token, _ in pairs)
        self._raw_at: tuple[int, ...] = tuple(index for _, index in pairs)
        self._content_at: dict[str, int] = {}
        for position, (token, _) in enumerate(pairs):
            self._content_at.setdefault(token, position)
        self.bag: frozenset[str] = frozenset(self.content)
        self.negated: frozenset[int] = _negated_region(self.raw)

    def phrase_hits(self, phrase: Sequence[str]) -> list[int]:
        """Raw-token indices of contiguous matches, for the negation check."""
        return [
            self._raw_at[start] for start in _phrase_positions(self.content, phrase)
        ]

    def coverage(self, phrase: Sequence[str]) -> float:
        """Fraction of ``phrase`` present, zeroed when a hit is negated.

        Conservative: if a negation cue precedes *any* matched token, the whole
        term scores 0.
        """
        if not phrase:
            return 0.0
        hits = 0
        for token in phrase:
            position = self._content_at.get(token)
            if position is None:
                continue
            hits += 1
            if self._raw_at[position] in self.negated:
                return 0.0
        if not hits:
            return 0.0
        return hits / len(phrase)


def _tool_text(row: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """``(id, label, description)`` content tokens for one catalog row."""
    tool_id = _content_tokens(_tokens(str(row.get("id") or "")))
    label = _content_tokens(_tokens(str(row.get("label") or "")))
    description = _content_tokens(_tokens(str(row.get("description") or "")))
    return tool_id, label, description


def _is_destructive(row: Mapping[str, Any]) -> bool:
    if DESTRUCTIVE_ROUTINE_TOOLS.__contains__(str(row.get("id") or "")):
        return True
    return bool(row.get("destructive"))


def _named_reason(row: Mapping[str, Any]) -> str:
    for rule in SUGGESTION_RULES:
        if str(rule["id"]) == str(row.get("id") or ""):
            return str(rule["reason"])
    return NAMED_REASON


def _catalog_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by id (first wins) and re-scrub every text field.

    The picker catalog already scrubs, but this module must not depend on that
    staying true: a token-shaped string in a description must never reach a
    model prompt, a reason, or a log.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows or ():
        if not isinstance(raw, Mapping):
            continue
        tool_id = scrub_suggestion_text(str(raw.get("id") or "")).strip()
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        row = dict(raw)
        row["id"] = tool_id
        for field in ("label", "description"):
            row[field] = scrub_suggestion_text(str(raw.get(field) or "")).strip()
        out.append(row)
    return out


def scorer_view(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Minimal, scrubbed, length-bounded view handed to a model scorer.

    Only id/label/description leave the process, and each is truncated at
    :data:`MAX_SCORER_DESCRIPTION` because a 1000-row catalog plus full tool
    bodies does not fit a small on-device context window. These rows are all a
    local/browser model is allowed to see.
    """
    return [
        {
            "id": str(row["id"]),
            "label": str(row["label"])[:MAX_SCORER_DESCRIPTION],
            "description": str(row["description"])[:MAX_SCORER_DESCRIPTION],
        }
        for row in _catalog_rows(rows)
    ]


def named_tool_ids(scan_text: str, rows: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    """Ids the scan text explicitly names.

    "Named" means a #1410 rule matched, or the tool id / label appears as a
    contiguous topical phrase. Computed independently of any scorer so the
    explicit-name pin cannot be moved by a model.
    """
    text = _Text(scrub_suggestion_text(scan_text))
    catalog = _catalog_rows(rows)
    known = {str(row["id"]) for row in catalog}
    named = {
        str(rule["id"])
        for rule in SUGGESTION_RULES
        if str(rule["id"]) in known and _rule_matches(rule, str(scan_text or ""))
    }
    for row in catalog:
        tool_id = str(row["id"])
        if tool_id in named:
            continue
        id_tokens, label_tokens, _ = _tool_text(row)
        for phrase in (id_tokens, label_tokens):
            if not phrase:
                continue
            hits = text.phrase_hits(phrase)
            if hits and not any(hit in text.negated for hit in hits):
                named.add(tool_id)
                break
    return frozenset(named)


def lexical_tool_confidence(
    scan_text: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    """Default scorer: deterministic lexical overlap in ``[0, HEURISTIC_CEILING]``.

    Pure — no network, no LLM, no clock, no randomness, no I/O. Explicit naming
    is *not* handled here; :func:`named_tool_ids` owns that so a model scorer
    cannot move the pin. See the module docstring for what the number means and
    what it cannot do.
    """
    text = _Text(scrub_suggestion_text(scan_text))
    scores: dict[str, float] = {}
    for raw in _catalog_rows(rows):
        tool_id = str(raw["id"])
        id_tokens, label_tokens, description_tokens = _tool_text(raw)
        score = (
            text.coverage(id_tokens) * WEIGHT_ID_COVERAGE
            + text.coverage(label_tokens) * WEIGHT_LABEL_COVERAGE
            + text.coverage(description_tokens) * WEIGHT_DESCRIPTION_COVERAGE
        )
        scores[tool_id] = round(min(max(score, 0.0), HEURISTIC_CEILING), 4)
    return scores


def _scorer_name(scorer: ToolConfidenceScorer) -> str:
    name = getattr(scorer, "__name__", "") or type(scorer).__name__
    return str(name)[:64] or "model"


def _coerce_confidence(value: Any) -> float:
    """Clamp a model-supplied number into [0, 1]. Junk becomes ``0.0``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return min(max(number, 0.0), 1.0)


def _resolve_scores(
    scan_text: str,
    view: Sequence[Mapping[str, Any]],
    scorer: ToolConfidenceScorer | None,
) -> tuple[dict[str, float], str]:
    """Run the injected scorer, degrading to the lexical default on failure.

    The failure log carries the exception *class* only — a model error message
    can echo the prompt, and prompts must never become logs.
    """
    if scorer is None:
        return lexical_tool_confidence(scan_text, view), "lexical"
    name = _scorer_name(scorer)
    try:
        raw_scores = scorer(scan_text, view)
    except Exception as exc:  # noqa: BLE001 - degrade, never hard-fail the builder
        logger.warning(
            "tool confidence scorer %s failed (%s); using lexical fallback",
            name,
            type(exc).__name__,
        )
        return lexical_tool_confidence(scan_text, view), "lexical"
    if not isinstance(raw_scores, Mapping):
        logger.warning(
            "tool confidence scorer %s returned %s; using lexical fallback",
            name,
            type(raw_scores).__name__,
        )
        return lexical_tool_confidence(scan_text, view), "lexical"
    known = {str(row["id"]) for row in view}
    scores: dict[str, float] = {}
    for key, value in raw_scores.items():
        tool_id = str(key or "").strip()
        if tool_id in known:
            scores[tool_id] = _coerce_confidence(value)
    return scores, name


def _clamp_top_n(top_n: int | None) -> int | None:
    if top_n is None:
        return None
    try:
        value = int(top_n)
    except (TypeError, ValueError):
        return None
    return max(value, 0)


def _clamp_min_confidence(min_confidence: float) -> float:
    if isinstance(min_confidence, bool) or not isinstance(min_confidence, (int, float)):
        return 0.0
    value = float(min_confidence)
    if value != value or value in (float("inf"), float("-inf")):
        return 0.0
    return min(max(value, 0.0), 1.0)


def rank_tools_by_confidence(
    instruction: str,
    catalog: Sequence[Mapping[str, Any]] | None = None,
    *,
    tools: Sequence[str] | None = None,
    trigger: Mapping[str, Any] | None = None,
    dismissed: Mapping[str, str] | None = None,
    top_n: int | None = None,
    min_confidence: float = 0.0,
    scorer: ToolConfidenceScorer | None = None,
) -> list[dict[str, Any]]:
    """Rank a (possibly 1000+ row) tool catalog against the instructions.

    Ordering is total and deterministic: ``(-confidence, id)``. Nothing is
    dropped silently:

    * tools already on the routine (``tools``) are excluded — no nag (#1410).
    * a tool the instructions *explicitly name* is pinned: it is kept even when
      it falls outside ``top_n`` (the row gets ``pinned=True``), so the returned
      list can legitimately exceed ``top_n``.
    * ``min_confidence`` defaults to ``0.0``, so a catalog where nothing scores
      returns every row (in id order) rather than an empty list.
    * ``top_n`` is clamped to >= 0; ``None`` means no truncation.

    ``scorer`` is the local/browser-model seam. It sees only
    :func:`scorer_view` and may reorder within the band, but it can neither
    promote a tool above a named one nor lift confidence past
    :data:`HEURISTIC_CEILING` for non-named tools.
    """
    scan = _scan_text(instruction, trigger)
    present = {str(tid).strip().lower() for tid in (tools or []) if str(tid).strip()}
    ignored = dismissed if isinstance(dismissed, Mapping) else {}
    fingerprint = instruction_fingerprint(instruction, trigger)

    # Dismissal runs *before* the top-N cut so a dismissed tool frees its slot
    # instead of hiding the ranked neighbour behind it.
    kept = [
        row
        for row in _catalog_rows(catalog or ())
        if str(row["id"]).strip().lower() not in present
        and ignored.get(str(row["id"])) != fingerprint
    ]
    scores, scorer_label = _resolve_scores(scan, scorer_view(kept), scorer)
    named = named_tool_ids(scan, kept)
    floor = _clamp_min_confidence(min_confidence)

    rows: list[dict[str, Any]] = []
    for row in kept:
        tool_id = str(row["id"])
        is_named = tool_id in named
        confidence = (
            NAMED_CONFIDENCE
            if is_named
            else min(_coerce_confidence(scores.get(tool_id, 0.0)), HEURISTIC_CEILING)
        )
        if confidence < floor:
            continue
        destructive = _is_destructive(row)
        rows.append(
            {
                "id": tool_id,
                "label": str(row.get("label") or "") or _title_case_tool_id(tool_id),
                "description": str(row.get("description") or ""),
                "kind": str(row.get("kind") or ""),
                "source": str(row.get("source") or ""),
                "confidence": confidence,
                "named": is_named,
                "pinned": False,
                "reason": _named_reason(row) if is_named else MATCHED_REASON,
                "destructive": destructive,
                "requires_confirm": destructive,
                # #1410 invariant, unchanged: nothing is ever auto-enabled.
                "auto_enable": False,
                "scorer": scorer_label,
            }
        )

    rows.sort(key=lambda item: (-item["confidence"], item["id"]))
    limit = _clamp_top_n(top_n)
    if limit is None or limit >= len(rows):
        return rows
    head = rows[:limit]
    tail = rows[limit:]
    for item in tail:
        if item["named"]:
            item["pinned"] = True
            head.append(item)
    return head


def suggest_routine_tools(
    instruction: str,
    tools: list[str] | None = None,
    trigger: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Flag likely-needed tools that are absent from ``tools``.

    Reasons are canned templates. Token-shaped instruction text is scrubbed
    before the scan and never copied into the result.
    """
    present = {str(tid).strip().lower() for tid in (tools or []) if str(tid).strip()}
    text = _scan_text(instruction, trigger)
    out: list[dict[str, Any]] = []
    for rule in SUGGESTION_RULES:
        tool_id = str(rule["id"])
        if tool_id.strip().lower() in present:
            continue
        if not _rule_matches(rule, text):
            continue
        out.append(
            {
                "id": tool_id,
                "label": rule["label"],
                "reason": rule["reason"],
                "destructive": bool(rule["destructive"]),
                "auto_enable": False,
            }
        )
    return out


def apply_suggested_tool(
    tools: list[str] | None,
    tool_id: str,
    *,
    confirmed: bool,
) -> list[str]:
    """Add ``tool_id`` only when the operator confirmed.

    Unconfirmed calls (including destructive tools) return ``tools`` unchanged.
    """
    current = [str(tid) for tid in (tools or []) if str(tid).strip()]
    slug = str(tool_id or "").strip()
    if not slug or not confirmed:
        return current
    if slug.lower() in {t.lower() for t in current}:
        return current
    return [*current, slug]


def visible_tool_suggestions(
    instruction: str,
    tools: list[str] | None,
    trigger: Mapping[str, Any] | None,
    dismissed: Mapping[str, str] | None,
) -> list[dict[str, Any]]:
    """Suggestions minus those dismissed for the current instruction fingerprint."""
    fingerprint = instruction_fingerprint(instruction, trigger)
    ignored = dismissed if isinstance(dismissed, Mapping) else {}
    visible: list[dict[str, Any]] = []
    for row in suggest_routine_tools(instruction, tools, trigger):
        if ignored.get(row["id"]) == fingerprint:
            continue
        visible.append(row)
    return visible
