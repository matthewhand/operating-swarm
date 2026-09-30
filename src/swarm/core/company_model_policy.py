"""Company model policy (#1315).

A Company stores which model ids its bots may use. Evaluation is fail-closed
for blank ids and secret-shaped values. Bot-create enforcement lives in
``company_attach`` (#1317).

Modes:

* ``allow_all`` — any non-denied, non-secret model id is allowed (default).
* ``allowlist`` — only listed models, minus ``denied_models``. Empty list
  denies every id.
* ``denylist`` — any model except those in ``denied_models``.

``denied_models`` always wins. ``default_model``, when set, must itself pass
the policy. No secrets. SQLite/Postgres only; no Neon.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from swarm.core.user_preferences import is_secret_key

POLICY_MODES = frozenset({"allow_all", "allowlist", "denylist"})
POLICY_KEYS = frozenset({"mode", "allowed_models", "denied_models", "default_model"})
DEFAULT_POLICY_MODE = "allow_all"
MAX_MODEL_ID_LEN = 255
MAX_POLICY_MODELS = 256

REASON_ALLOW_ALL = "allow_all"
REASON_ALLOWLISTED = "allowlisted"
REASON_DENIED = "denied"
REASON_NOT_ALLOWLISTED = "not_allowlisted"
REASON_BLANK = "blank"
REASON_SECRET = "secret"
REASON_INVALID = "invalid"


class CompanyModelPolicyError(ValueError):
    """Invalid Company model-policy payload."""

    def __init__(self, message: str, *, code: str = "invalid_policy") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ModelPolicyDecision:
    """Whether ``model`` may be used under a Company policy."""

    allowed: bool
    reason: str
    model: str
    default_model: str = ""


def empty_model_policy() -> dict[str, Any]:
    """Canonical empty policy: allow all, no default."""
    return {
        "mode": DEFAULT_POLICY_MODE,
        "allowed_models": [],
        "denied_models": [],
        "default_model": "",
    }


def normalize_model_id(value: Any) -> str:
    """Strip a model id. Blank after strip is empty. Secrets raise."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CompanyModelPolicyError("Model id must be a string.", code="invalid_model")
    model = value.strip()
    if not model:
        return ""
    if len(model) > MAX_MODEL_ID_LEN:
        raise CompanyModelPolicyError(
            f"Model id exceeds {MAX_MODEL_ID_LEN} characters.",
            code="invalid_model",
        )
    if _is_secret_model_id(model):
        raise CompanyModelPolicyError(
            "Model ids must not look like secrets.",
            code="secret_refused",
        )
    return model


def _is_secret_model_id(model: str) -> bool:
    """Reject credential-shaped values, not provider ids that mention 'token'."""
    if _looks_like_secret_value(model):
        return True
    # Prefix checks apply to each path segment so ``openai/sk-...`` cannot
    # sneak past the whole-string startswith test. Word fragments such as
    # "token" stay limited to bare ids: ``huggingface/token-classifier`` is a
    # model name.
    for segment in model.split("/"):
        # Leading whitespace on a segment used to hide ``sk-`` / ``ghp_``.
        piece = segment.strip()
        if piece and _looks_like_secret_value(piece):
            return True
    # Word fragments ("api_key", "token") use the same probe. A ZWSP
    # inside "api_key" is not a different model name.
    return "/" not in model and is_secret_key(_prefix_probe(model))


def _prefix_probe(value: str) -> str:
    """Drop characters that hid a credential marker.

    ``str.strip`` removes leading and trailing spaces, line separators, and
    paragraph separators. It does not touch those characters in the middle,
    so ``s k-`` and an NBSP (U+00A0) inside ``sk-`` used to stay allowed.
    Format and control characters (ZWSP, BOM) are not spaces either. Spaces
    (Zs), line separators (Zl), and paragraph separators (Zp) are removed
    for this check only. The stored model id is unchanged.
    """
    cleaned = "".join(
        ch
        for ch in value
        if unicodedata.category(ch) not in {"Cf", "Cc", "Zl", "Zp", "Zs"}
    )
    return cleaned.strip()


def _looks_like_secret_value(value: str) -> bool:
    lowered = _prefix_probe(value).lower()
    if lowered.startswith(("sk-", "rk-", "ghp_", "gho_", "xoxb-", "xoxp-")):
        return True
    if "-----begin" in lowered:
        return True
    return False


def _normalize_model_list(values: Any, *, field: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise CompanyModelPolicyError(
            f"{field} must be a list of model ids.",
            code="invalid_policy",
        )
    if len(values) > MAX_POLICY_MODELS:
        raise CompanyModelPolicyError(
            f"{field} exceeds {MAX_POLICY_MODELS} entries.",
            code="invalid_policy",
        )
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        model = normalize_model_id(raw)
        if not model or model in seen:
            continue
        seen.add(model)
        out.append(model)
    return out


def normalize_model_policy(raw: Any | None) -> dict[str, Any]:
    """Coerce a JSON bag into the canonical Company model-policy shape."""
    policy = _canonicalize_model_policy(raw)
    default_model = str(policy.get("default_model") or "")
    if default_model:
        decision = _evaluate_canonical(policy, default_model)
        if not decision.allowed:
            raise CompanyModelPolicyError(
                "default_model is not allowed by this Company model policy.",
                code="default_model_denied",
            )
    return policy


def _canonicalize_model_policy(raw: Any | None) -> dict[str, Any]:
    if raw is None or raw == "":
        return empty_model_policy()
    if not isinstance(raw, Mapping):
        raise CompanyModelPolicyError(
            "model_policy must be an object.",
            code="invalid_policy",
        )
    # A typo such as ``deny_models`` used to be dropped, leaving an empty deny
    # list (allow every model). #1492 refuses a corrupt bag on attach, so
    # rejecting the key here stays fail-closed.
    unknown = sorted(str(key) for key in raw if str(key) not in POLICY_KEYS)
    if unknown:
        shown = ", ".join(unknown[:8])
        raise CompanyModelPolicyError(
            f"model_policy has unknown keys: {shown}.",
            code="invalid_policy",
        )
    mode = str(raw.get("mode") or DEFAULT_POLICY_MODE).strip().lower()
    if mode not in POLICY_MODES:
        raise CompanyModelPolicyError(
            "model_policy.mode must be allow_all, allowlist, or denylist.",
            code="invalid_policy",
        )
    allowed = _normalize_model_list(raw.get("allowed_models"), field="allowed_models")
    denied = _normalize_model_list(raw.get("denied_models"), field="denied_models")
    default_model = normalize_model_id(raw.get("default_model") or "")
    return {
        "mode": mode,
        "allowed_models": allowed,
        "denied_models": denied,
        "default_model": default_model,
    }


def _evaluate_canonical(canonical: Mapping[str, Any], model_id: str) -> ModelPolicyDecision:
    default_model = str(canonical.get("default_model") or "")
    if not model_id:
        return ModelPolicyDecision(
            allowed=False,
            reason=REASON_BLANK,
            model="",
            default_model=default_model,
        )

    denied = set(canonical.get("denied_models") or [])
    if model_id in denied:
        return ModelPolicyDecision(
            allowed=False,
            reason=REASON_DENIED,
            model=model_id,
            default_model=default_model,
        )

    mode = str(canonical.get("mode") or DEFAULT_POLICY_MODE)
    if mode == "allowlist":
        allowed = set(canonical.get("allowed_models") or [])
        if model_id in allowed:
            return ModelPolicyDecision(
                allowed=True,
                reason=REASON_ALLOWLISTED,
                model=model_id,
                default_model=default_model,
            )
        return ModelPolicyDecision(
            allowed=False,
            reason=REASON_NOT_ALLOWLISTED,
            model=model_id,
            default_model=default_model,
        )

    return ModelPolicyDecision(
        allowed=True,
        reason=REASON_ALLOW_ALL if mode == "allow_all" else "not_denied",
        model=model_id,
        default_model=default_model,
    )


def evaluate_model_policy(
    policy: Mapping[str, Any] | None,
    model: Any,
) -> ModelPolicyDecision:
    """Decide whether ``model`` is allowed under ``policy``.

    Blank or secret-shaped ids are never allowed. A corrupt policy bag is
    fail-closed (deny) so it cannot widen access. Writers must call
    :func:`normalize_model_policy` so invalid input is rejected on persist.
    """
    try:
        canonical = _canonicalize_model_policy(policy)
    except CompanyModelPolicyError as exc:
        reason = REASON_SECRET if exc.code == "secret_refused" else REASON_INVALID
        return ModelPolicyDecision(
            allowed=False,
            reason=reason,
            model="",
            default_model="",
        )

    try:
        model_id = normalize_model_id(model)
    except CompanyModelPolicyError as exc:
        reason = REASON_SECRET if exc.code == "secret_refused" else REASON_INVALID
        return ModelPolicyDecision(
            allowed=False,
            reason=reason,
            model="",
            default_model=str(canonical.get("default_model") or ""),
        )

    return _evaluate_canonical(canonical, model_id)


def resolve_default_model(policy: Mapping[str, Any] | None) -> str:
    """Return the policy default when it is itself allowed, else empty."""
    canonical = normalize_model_policy(policy)
    default_model = str(canonical.get("default_model") or "")
    if not default_model:
        return ""
    decision = evaluate_model_policy(canonical, default_model)
    return default_model if decision.allowed else ""


def policy_public_payload(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    """JSON-safe policy object for API responses (never includes secrets)."""
    return normalize_model_policy(policy)


def iter_policy_models(policy: Mapping[str, Any] | None) -> Iterable[str]:
    """Unique model ids named by the policy (allow + deny + default)."""
    canonical = normalize_model_policy(policy)
    seen: set[str] = set()
    for model in (
        *(canonical.get("allowed_models") or []),
        *(canonical.get("denied_models") or []),
        canonical.get("default_model") or "",
    ):
        if model and model not in seen:
            seen.add(model)
            yield model
