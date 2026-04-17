"""Per-system log collector daemons (background threads)."""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from config import SCHEDULER_INTERVAL_SECONDS, SCHEDULER_SEARCH_CONFIG_INTERVAL_SECONDS

from fastlog import database
from fastlog.log_collector import LogCollector, LogCollectorDaemon

logger = logging.getLogger(__name__)


class DaemonManager:
    """Owns one `LogCollectorDaemon` thread per system_id."""

    def __init__(self, collector: LogCollector, interval_seconds: float = SCHEDULER_INTERVAL_SECONDS):
        self.collector = collector
        self.interval_seconds = interval_seconds
        self.search_config_interval_seconds = SCHEDULER_SEARCH_CONFIG_INTERVAL_SECONDS
        self.running = False
        self._guard = threading.Lock()
        self._daemons: dict[int, LogCollectorDaemon] = {}

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        systems = database.list_systems()
        logger.info("DaemonManager.start: systems=%s interval_s=%s", len(systems), self.interval_seconds)
        for sys_item in systems:
            self.ensure_daemon(int(sys_item["id"]))

    def stop_all(self) -> None:
        with self._guard:
            self.running = False
            for sid, d in list(self._daemons.items()):
                d.stop()
                d.join(timeout=10.0)
            self._daemons.clear()

    def ensure_daemon(self, system_id: int) -> None:
        """Start or restart the daemon for this system."""
        with self._guard:
            old = self._daemons.pop(system_id, None)
            if old:
                old.stop()
                old.join(timeout=10.0)
            if not self.running:
                self.running = True
            daemon = LogCollectorDaemon(system_id, self.interval_seconds, self.collector)
            daemon.start()
            self._daemons[system_id] = daemon
            logger.info(
                "ensure_daemon: system_id=%s restarted=%s interval_s=%s",
                system_id,
                old is not None,
                self.interval_seconds,
            )

    def stop_daemon(self, system_id: int) -> None:
        with self._guard:
            d = self._daemons.pop(system_id, None)
            if d:
                d.stop()
                d.join(timeout=10.0)
                logger.info("stop_daemon: system_id=%s", system_id)

    def status_snapshot(self) -> dict[str, Any]:
        """Aggregate stats for /api/background-tasks (compat with old scheduler fields)."""
        with self._guard:
            items = list(self._daemons.items())
        ticks = [d.last_tick_at for _, d in items if d.last_tick_at is not None]
        inserted_sum = sum(int(d.last_inserted_total or 0) for _, d in items)
        last_tick = max(ticks) if ticks else None
        err_sid: Optional[int] = None
        err_msg: Optional[str] = None
        err_at: Optional[float] = None
        for sid, d in items:
            if d.last_error:
                err_sid = sid
                err_msg = d.last_error
                err_at = d.last_error_at
                break
        return {
            "scheduler_running": bool(self.running and items),
            "interval_seconds": self.interval_seconds,
            "last_tick_at": last_tick,
            "last_main_inserted_total": inserted_sum,
            "last_scheduler_error": err_msg,
            "last_scheduler_error_system_id": err_sid,
            "last_scheduler_error_at": err_at,
            "daemon_count": len(items),
        }
