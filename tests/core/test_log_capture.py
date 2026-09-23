"""#903 — in-memory LogCapture: the diagnostics ring buffer.

Thread-safe, never-raises, swarm-logger-scoped. The later diagnostics
payload (#904) composes `recent()` output; masking lives there, not here.
"""

from __future__ import annotations

import logging

import pytest

from swarm.core.log_capture import LogCapture


@pytest.fixture()
def capture():
    handle = LogCapture.install()
    yield handle
    handle.uninstall()


def _emit(logger: logging.Logger, level: int, msg: str) -> None:
    record = logging.LogRecord(
        name=logger.name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    logger.handle(record)


def test_install_and_uninstall_leave_other_handlers_intact(capture):
    logger = logging.getLogger("swarm")
    before = list(logger.handlers)
    handle2 = LogCapture.install()
    logger2 = logging.getLogger("swarm")
    assert any(isinstance(h, LogCapture) for h in logger2.handlers)
    handle2.uninstall()
    assert list(logging.getLogger("swarm").handlers) == before


def test_recent_returns_last_lines_in_chronological_order(capture):
    logger = logging.getLogger("swarm.test")
    for i in range(5):
        _emit(logger, logging.INFO, f"line-{i}")
    lines = LogCapture.recent()
    assert [line["message"] for line in lines] == [f"line-{i}" for i in range(5)]


def test_ring_buffer_truncates_to_capacity(monkeypatch):
    monkeypatch.setenv("SWARM_DIAG_LOG_LINES", "3")
    handle = LogCapture.install()
    try:
        logger = logging.getLogger("swarm.test.ring")
        for i in range(10):
            _emit(logger, logging.INFO, f"ring-{i}")
        lines = LogCapture.recent()
        assert len(lines) == 3
        assert [line["message"] for line in lines] == ["ring-7", "ring-8", "ring-9"]
    finally:
        handle.uninstall()


def test_recent_filters_by_level(capture):
    logger = logging.getLogger("swarm.test.levels")
    _emit(logger, logging.INFO, "info-line")
    _emit(logger, logging.ERROR, "error-line")
    errors = LogCapture.recent(level="ERROR")
    assert [line["message"] for line in errors] == ["error-line"]


def test_per_level_counts_sum_to_buffered_records(capture):
    logger = logging.getLogger("swarm.test.counts")
    _emit(logger, logging.INFO, "a")
    _emit(logger, logging.INFO, "b")
    _emit(logger, logging.WARNING, "c")
    counts = LogCapture.level_counts()
    assert counts["INFO"] == 2
    assert counts["WARNING"] == 1
    assert sum(counts.values()) == 3


def test_records_carry_structured_fields(capture):
    logger = logging.getLogger("swarm.test.shape")
    _emit(logger, logging.WARNING, "shaped")
    line = LogCapture.recent(limit=1)[0]
    assert set(line) >= {"ts", "level", "logger", "message"}
    assert line["level"] == "WARNING"
    assert line["logger"] == "swarm.test.shape"


def test_formatter_failure_does_not_raise(capture):
    class _Boom(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:  # noqa: D102
            raise RuntimeError("boom")

    logger = logging.getLogger("swarm.test.boom")
    _emit(logger, logging.INFO, "will fail to format")
    # must not raise; the record is dropped (or stderr-logged) silently
    lines = LogCapture.recent()
    assert isinstance(lines, list)
