"""Backward-compatible name for the log collector (legacy imports)."""

from fastlog.log_collector import LogCollector

LogProcessor = LogCollector

__all__ = ["LogCollector", "LogProcessor"]
