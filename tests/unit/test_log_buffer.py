"""
Tests for the log buffer ring handler and sanitization utilities.
"""

from __future__ import annotations

import logging

import pytest

from misaka.utils.log_buffer import (
    LogEntry,
    RingBufferHandler,
    sanitize,
)


class TestSanitize:

    def test_redacts_sk_ant_key(self) -> None:
        text = "key=sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        result = sanitize(text)
        assert "abcdefghijklmnopqrstuvwxyz" not in result
        assert "sk-ant-api03-" in result

    def test_redacts_bearer_token(self) -> None:
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.long-token-here"
        result = sanitize(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "Bearer" in result

    def test_redacts_password_assignment(self) -> None:
        text = "password=mysecretpassword123"
        result = sanitize(text)
        assert "mysecretpassword123" not in result

    def test_preserves_normal_text(self) -> None:
        text = "This is normal log output with no secrets"
        assert sanitize(text) == text


class TestLogEntry:

    def test_format_line(self) -> None:
        entry = LogEntry(
            timestamp="2026-04-11 10:00:00",
            level="INFO",
            logger_name="misaka.main",
            message="Application started",
        )
        line = entry.format_line()
        assert "2026-04-11 10:00:00" in line
        assert "[INFO]" in line
        assert "misaka.main" in line
        assert "Application started" in line


class TestRingBufferHandler:

    def test_basic_emit(self) -> None:
        handler = RingBufferHandler(maxlen=10)
        logger = logging.getLogger("test.ring_buffer.basic")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("test message")

        entries = handler.get_entries()
        assert len(entries) == 1
        assert entries[0].level == "INFO"
        assert "test message" in entries[0].message

        logger.removeHandler(handler)

    def test_maxlen_eviction(self) -> None:
        handler = RingBufferHandler(maxlen=3)
        logger = logging.getLogger("test.ring_buffer.eviction")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        for i in range(5):
            logger.info("msg %d", i)

        entries = handler.get_entries()
        assert len(entries) == 3
        assert "msg 2" in entries[0].message
        assert "msg 4" in entries[2].message

        logger.removeHandler(handler)

    def test_level_filter(self) -> None:
        handler = RingBufferHandler(maxlen=10)
        logger = logging.getLogger("test.ring_buffer.filter")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warning msg")
        logger.error("error msg")

        info_entries = handler.get_entries(level_filter="INFO")
        assert len(info_entries) == 1
        assert info_entries[0].level == "INFO"

        error_entries = handler.get_entries(level_filter="ERROR")
        assert len(error_entries) == 1

        all_entries = handler.get_entries()
        assert len(all_entries) == 4

        logger.removeHandler(handler)

    def test_clear(self) -> None:
        handler = RingBufferHandler(maxlen=10)
        logger = logging.getLogger("test.ring_buffer.clear")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("test")
        assert handler.entry_count == 1

        handler.clear()
        assert handler.entry_count == 0
        assert handler.get_entries() == []

        logger.removeHandler(handler)

    def test_entry_count(self) -> None:
        handler = RingBufferHandler(maxlen=10)
        assert handler.entry_count == 0

    def test_max_entries(self) -> None:
        handler = RingBufferHandler(maxlen=50)
        assert handler.max_entries == 50

    def test_sanitization_filter_applied(self) -> None:
        handler = RingBufferHandler(maxlen=10)
        logger = logging.getLogger("test.ring_buffer.sanitize")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("Using key sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890abcd")

        entries = handler.get_entries()
        assert len(entries) == 1
        assert "abcdefghijklmnopqrstuvwxyz" not in entries[0].message

        logger.removeHandler(handler)
