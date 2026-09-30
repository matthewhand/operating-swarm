"""Structural (AST) source pins for Python modules.

Why this exists
---------------
The rotted-test family asserts on *text*: ``assert "await self._save()" in src``,
``src.count("await self._persist_completed_turn()") == 2``. Those assertions
break when code is legitimately refactored (a signature wrapped across lines, a
helper moved, a call site added) and they pass on a match inside a comment or a
docstring — neither of which is behaviour.

An AST read fixes both halves:

* formatting-immune — whitespace, line wrapping and import order cannot change
  the parse, so a reformat is not a test failure;
* comment/docstring-proof — comments and string literals are not statements, so
  a phrase surviving in prose can no longer satisfy a pin.

It is still a *structural* pin, not a behavioural one. Where a behavioural
assertion is possible it is strictly better; use this when the protected
property is "this call site exists in this function", which cannot be observed
from the outside (a stub responder is only reachable through a live LLM).
"""

from __future__ import annotations

import ast
from pathlib import Path

__all__ = [
    "parse_module",
    "iter_functions",
    "find_function",
    "awaited_call_count",
    "has_awaited_call",
    "await_sites",
    "calls_within",
    "calls_within_body",
    "defined_names",
    "string_constants",
]


def parse_module(path: Path | str) -> ast.Module:
    """Parse ``path`` (or a source string) into an AST module."""
    if isinstance(path, (str, Path)) and Path(path).exists():
        source = Path(path).read_text(encoding="utf-8")
    else:
        source = str(path)
    return ast.parse(source)


def iter_functions(module: ast.Module, *, name: str | None = None):
    """Yield every ``def``/``async def`` in the module, at any nesting depth.

    Mixins and consumer classes spread the same method names across files, so
    callers pass a bare name and get every definition found in this module.
    """
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if name is None or node.name == name:
            yield node


def find_function(module: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """The single function called ``name``; raises if absent or ambiguous."""
    found = list(iter_functions(module, name=name))
    if not found:
        raise AssertionError(f"no function named {name!r} in the module")
    if len(found) > 1:
        names = ", ".join(f"{n.name}@{n.lineno}" for n in found)
        raise AssertionError(f"{name!r} is defined {len(found)}x ({names}); name them uniquely")
    return found[0]


def awaited_call_count(module: ast.Module, func_name: str, dotted: str) -> int:
    """How many times ``func_name`` awaits ``<dotted>`` (e.g. ``self._save``).

    Only real ``await <Call>`` nodes count. A mention inside a comment, a
    docstring, or a plain (un-awaited) call is not a persistence point — which
    is exactly the distinction a substring count cannot make.
    """
    total = 0
    for fn in iter_functions(module, name=func_name):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
                continue
            if _dotted(node.value.func) == dotted:
                total += 1
    return total


def has_awaited_call(module: ast.Module, func_name: str, dotted: str) -> bool:
    return awaited_call_count(module, func_name, dotted) > 0


def await_sites(module: ast.Module, func_name: str) -> list[ast.Await]:
    """Every ``await`` inside ``func_name``.

    Use when the property is "this coroutine hands off / persists / announces",
    not "it calls this one named helper": a bare ``await`` is immune to a
    rename of the callee and to a reformat, where a substring pin is not.
    """
    out: list[ast.Await] = []
    for fn in iter_functions(module, name=func_name):
        out.extend(node for node in ast.walk(fn) if isinstance(node, ast.Await))
    return out


def calls_within(module: ast.Module, func_name: str) -> set[str]:
    """Dotted names of every call made inside ``func_name`` and its closures.

    ``asyncio.Lock()`` inside ``_ensure_chat_turn_lock`` → ``{"asyncio.Lock"}``.
    A comment or a docstring cannot contribute, which is the whole point.
    """
    out: set[str] = set()
    for fn in iter_functions(module, name=func_name):
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                out.add(_dotted(node.func))
    return out


def calls_within_body(module: ast.Module, func_name: str) -> set[str]:
    """Call names in ``func_name``'s own body, excluding nested functions.

    Needed whenever a method delegates to helpers: without this, a wrapper's
    callee set silently absorbs everything its inner function calls, so a
    wrapper can look like it persists a turn when it only calls a helper that
    happens to mention the word.
    """
    out: set[str] = set()
    for fn in iter_functions(module, name=func_name):
        nested: set[int] = set()
        for node in ast.walk(fn):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not fn:
                nested.update(id(child) for child in ast.walk(node))
        for node in ast.walk(fn):
            if id(node) in nested:
                continue
            if isinstance(node, ast.Call):
                out.add(_dotted(node.func))
    return out


def defined_names(module: ast.Module) -> set[str]:
    """Every name bound by a ``def``/``class``/assignment at module level."""
    names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def string_constants(module: ast.Module) -> set[str]:
    """Every string literal in the module (docstrings included)."""
    out: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


def _dotted(node: ast.expr) -> str:
    """``self._persist_completed_turn`` -> ``"self._persist_completed_turn"``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))
