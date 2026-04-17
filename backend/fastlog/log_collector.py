"""Remote log collection via SSH: find recently modified files + grep (shell)."""

from __future__ import annotations

import logging
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

# find -mmin window used by the daemon tick.  Must be larger than
# SCHEDULER_INTERVAL_SECONDS / 60 so that no modification is missed
# between two consecutive ticks.  1 minute is sufficient for the
# default 10-second polling interval.
_DAEMON_TICK_FIND_MMIN = 1

from fastlog import database
from fastlog.init_progress import progress_manager
from fastlog.ssh_client import SSHClient, SSHConfig

logger = logging.getLogger(__name__)


def _shell_single_quote(s: str) -> str:
    """Safe single-quoted string for POSIX shell."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _parse_keywords(search_text: str) -> list[str]:
    return [k.strip() for k in (search_text or "").split(";") if k.strip()]


_BLOCK_LINE_RE = re.compile(r"^(\d+)([-:])(.*)$")


def _ssh_target_for_log(system_id: int, cfg_override: Optional[dict[str, Any]] = None) -> str:
    cfg = database.get_config(system_id)
    if cfg_override:
        cfg = {**cfg, **cfg_override}
    host = cfg.get("server_host", "?")
    port = database.parse_stored_int(cfg.get("server_port"), 22)
    user = cfg.get("server_username", "?")
    return f"{user}@{host}:{port}"


class LogCollector:
    """SSH log collection: list files with find -mmin, grep -n -F with context, insert into DB."""

    def __init__(self) -> None:
        self._locks_guard = threading.Lock()
        self._system_locks: dict[int, threading.Lock] = {}

    @contextmanager
    def _locked_system(self, system_id: int) -> Iterator[None]:
        with self._locks_guard:
            lock = self._system_locks.setdefault(system_id, threading.Lock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def _build_ssh(
        self,
        system_id: int,
        cfg_override: Optional[dict[str, Any]] = None,
        cfg_base: Optional[dict[str, Any]] = None,
    ) -> SSHClient:
        cfg = cfg_base if cfg_base is not None else database.get_config(system_id)
        if cfg_override:
            cfg = {**cfg, **cfg_override}
        return SSHClient(
            SSHConfig(
                host=cfg.get("server_host", "127.0.0.1"),
                username=cfg.get("server_username", "root"),
                password=cfg.get("server_password", ""),
                port=database.parse_stored_int(cfg.get("server_port"), 22),
            )
        )

    def test_connection(self, system_id: int, cfg_override: Optional[dict[str, Any]] = None):
        ssh = self._build_ssh(system_id, cfg_override=cfg_override)
        try:
            out = ssh.test_connection()
            logger.info(
                "test_connection: system_id=%s target=%s ok=%s",
                system_id,
                _ssh_target_for_log(system_id, cfg_override),
                (out or {}).get("ok"),
            )
            return out
        finally:
            ssh.close()

    def _extract_printed_at(self, line: str) -> Optional[str]:
        patterns = [
            r"[A-Z]?(\d{8}\s\d{2}:\d{2}:\d{2}\.\d+)",
            r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)",
        ]
        for pattern in patterns:
            m = re.search(pattern, line)
            if not m:
                continue
            val = m.group(1)
            for fmt in ("%Y%m%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(val, fmt).isoformat(sep=" ")
                except ValueError:
                    pass
        return None

    def _grep_file_remote(
        self,
        ssh: SSHClient,
        file_path: str,
        keywords: list[str],
        before: int,
        after: int,
    ) -> list[tuple[int, str, str]]:
        """Return (anchor_line_number, merged_block, anchor_line_text)."""
        if not keywords:
            return []
        first = keywords[0]
        b = max(0, int(before))
        a = max(0, int(after))
        fp = _shell_single_quote(file_path)
        pat = _shell_single_quote(first)
        cmd = f"grep -n -F -B {b} -A {a} -- {pat} {fp} 2>/dev/null || true"
        out, _ = ssh.execute_command(cmd)
        results: list[tuple[int, str, str]] = []
        for raw_block in out.split("\n--\n"):
            block = raw_block.strip("\n")
            if not block.strip():
                continue
            lines = block.splitlines()
            merged_parts: list[str] = []
            anchor_no: Optional[int] = None
            anchor_text: Optional[str] = None
            for line in lines:
                m = _BLOCK_LINE_RE.match(line)
                if not m:
                    continue
                _num, sep, content = m.group(1), m.group(2), m.group(3)
                merged_parts.append(content)
                if sep == ":":
                    anchor_no = int(_num)
                    anchor_text = content
            if anchor_no is None or anchor_text is None:
                continue
            if not all(k in anchor_text for k in keywords):
                continue
            merged = "\n".join(merged_parts)
            results.append((anchor_no, merged, anchor_text))
        return results

    def _rule_collect(
        self,
        system_id: int,
        ssh: SSHClient,
        rule: dict[str, Any],
        search_label: str,
        *,
        task_id: Optional[str] = None,
        processed_files_counter: Optional[list[int]] = None,
        total_files: Optional[int] = None,
    ) -> Optional[int]:
        """Process one rule; return number of newly inserted rows, or None if cancelled."""
        tr = int(rule.get("time_range_minutes") or 0)
        directory = str(rule.get("log_directory") or "/var/log").strip() or "/var/log"
        search_text = str(rule.get("search_text") or "")
        before = int(rule.get("context_before") or rule.get("context_lines_before") or 0)
        after = int(rule.get("context_after") or rule.get("context_lines_after") or 0)
        keywords = _parse_keywords(search_text)
        if not keywords:
            return 0

        files = ssh.list_files(directory, modified_within_minutes=tr if tr > 0 else 0)
        logger.info(
            "_rule_collect: system_id=%s dir=%s mmin=%s file_count=%s label=%r",
            system_id,
            directory,
            tr if tr > 0 else "all",
            len(files),
            search_label[:80] if search_label else "",
        )
        inserted = 0
        for file_path in files:
            if task_id and progress_manager.is_cancel_requested(task_id):
                progress_manager.mark_cancelled(task_id)
                return None
            for line_no, merged, _anchor in self._grep_file_remote(ssh, file_path, keywords, before, after):
                printed_at = self._extract_printed_at(merged) or datetime.utcnow().isoformat(sep=" ")
                if database.create_log(
                    system_id,
                    merged,
                    file_path,
                    line_no,
                    search_label,
                    printed_at=printed_at,
                ):
                    inserted += 1
            if processed_files_counter is not None:
                processed_files_counter[0] += 1
                if task_id and total_files is not None and total_files > 0:
                    pct = int((processed_files_counter[0] / total_files) * 100)
                    progress_manager.update_task(
                        task_id,
                        processed_files=processed_files_counter[0],
                        total_files=total_files,
                        percentage=min(100, pct),
                        current_file=file_path,
                    )
        logger.info(
            "_rule_collect: system_id=%s dir=%s inserted_rows=%s",
            system_id,
            directory,
            inserted,
        )
        return inserted

    def _gather_rules_daemon(self, system_id: int) -> list[dict[str, Any]]:
        cfg = database.get_config(system_id)
        rules: list[dict[str, Any]] = []
        if database.parse_stored_int(cfg.get("main_log_collection_enabled"), 1):
            rules.append(
                {
                    "log_directory": cfg.get("log_directory", "/var/log"),
                    "search_text": cfg.get("search_text", "error"),
                    "time_range_minutes": database.parse_stored_int(cfg.get("init_time_range_minutes"), 120),
                    "context_before": int(cfg.get("context_lines_before", 0)),
                    "context_after": int(cfg.get("context_lines_after", 0)),
                    "label": cfg.get("search_text", "error"),
                }
            )
        for sc in database.list_search_configs(system_id):
            if int(sc.get("enabled", 1)) != 1:
                continue
            rules.append(
                {
                    "log_directory": sc.get("log_directory", "/var/log"),
                    "search_text": sc.get("search_text", ""),
                    "time_range_minutes": database.parse_stored_int(sc.get("init_time_range_minutes"), 120),
                    "context_before": int(sc.get("context_lines_before", 0)),
                    "context_after": int(sc.get("context_lines_after", 0)),
                    "label": sc.get("search_text", ""),
                }
            )
        return rules

    def collect_daemon_tick(self, system_id: int) -> int:
        """One scheduler tick: incremental collection of new bytes from recently changed files.

        Strategy
        --------
        1. Gather all active rules to know which directories and keywords to watch.
        2. For each directory run ``find -mmin -1`` to get files modified in the
           last minute (safely larger than the 10-second poll interval).
        3. For each file compare current size against the persisted ``file_states``
           record:
           - **First sight**: register current size as the starting position; no
             lines are read this tick so that only *future* writes are collected.
           - **Truncated**: file shrank (log rotated/cleared); reset tracking to
             the current size and skip reading this tick.
           - **Grown**: read only the new bytes via ``tail -c +<offset+1>``,
             filter lines against rule keywords, insert matching blocks, and
             update ``file_states``.
        """
        t0 = time.perf_counter()
        tgt = _ssh_target_for_log(system_id)
        rules = self._gather_rules_daemon(system_id)
        if not rules:
            logger.warning(
                "collect_daemon_tick: system_id=%s ssh_target=%s rules=0 — check main_log_collection_enabled / search_configs",
                system_id,
                tgt,
            )
            return 0

        # Group rules by directory so we issue one `find` per directory.
        dir_rules: dict[str, list[dict[str, Any]]] = {}
        for rule in rules:
            d = str(rule.get("log_directory") or "/var/log").strip() or "/var/log"
            kws = _parse_keywords(str(rule.get("search_text") or ""))
            if not kws:
                continue
            dir_rules.setdefault(d, []).append(
                {
                    "keywords": kws,
                    "label": str(rule.get("label") or rule.get("search_text") or ""),
                    "context_before": int(rule.get("context_before") or 0),
                    "context_after": int(rule.get("context_after") or 0),
                }
            )

        if not dir_rules:
            logger.warning(
                "collect_daemon_tick: system_id=%s all rules have empty search_text — nothing to collect",
                system_id,
            )
            return 0

        logger.info(
            "collect_daemon_tick: begin system_id=%s ssh_target=%s dirs=%s",
            system_id,
            tgt,
            list(dir_rules.keys()),
        )

        with self._locked_system(system_id):
            ssh = self._build_ssh(system_id)
            try:
                total = 0
                for directory, sub_rules in dir_rules.items():
                    files = ssh.list_files(directory, modified_within_minutes=_DAEMON_TICK_FIND_MMIN)
                    for file_path in files:
                        size, mtime = ssh.get_file_stat(file_path)
                        if size == 0:
                            continue

                        state = database.get_file_state(system_id, file_path)

                        # --- First sight: record position, nothing to read yet ---
                        if state is None:
                            database.upsert_file_state(system_id, file_path, size, size, 0, mtime)
                            logger.info(
                                "collect_daemon_tick: first-seen system_id=%s file=%s size=%s — registered",
                                system_id,
                                file_path,
                                size,
                            )
                            continue

                        last_size = int(state["last_size"])
                        last_line_number = int(state["last_line_number"])

                        # --- Truncation (log rotation / clear): reset, skip this tick ---
                        if size < last_size:
                            logger.info(
                                "collect_daemon_tick: truncated system_id=%s file=%s old=%s new=%s — resetting",
                                system_id,
                                file_path,
                                last_size,
                                size,
                            )
                            database.upsert_file_state(system_id, file_path, size, size, 0, mtime)
                            continue

                        # --- No new bytes ---
                        if size == last_size:
                            continue

                        # --- New bytes available: read incrementally ---
                        new_content = ssh.read_bytes_from(file_path, last_size)
                        new_lines = new_content.splitlines()
                        if not new_lines:
                            database.upsert_file_state(
                                system_id, file_path, size, size, last_line_number, mtime
                            )
                            continue

                        inserted_for_file = 0
                        for sub_rule in sub_rules:
                            keywords = sub_rule["keywords"]
                            label = sub_rule["label"]
                            cb = sub_rule["context_before"]
                            ca = sub_rule["context_after"]
                            for i, line in enumerate(new_lines):
                                if not all(k in line for k in keywords):
                                    continue
                                # Collect context from within the new chunk only.
                                before = new_lines[max(0, i - cb) : i]
                                after = new_lines[i + 1 : i + 1 + ca]
                                block = "\n".join(before + [line] + after)
                                abs_line_no = last_line_number + i + 1
                                printed_at = (
                                    self._extract_printed_at(line)
                                    or datetime.utcnow().isoformat(sep=" ")
                                )
                                if database.create_log(
                                    system_id,
                                    block,
                                    file_path,
                                    abs_line_no,
                                    label,
                                    printed_at=printed_at,
                                    ingest_chunk_start_byte=last_size,
                                ):
                                    inserted_for_file += 1

                        total += inserted_for_file
                        new_line_count = len(new_lines)
                        database.upsert_file_state(
                            system_id,
                            file_path,
                            size,
                            size,
                            last_line_number + new_line_count,
                            mtime,
                        )
                        logger.info(
                            "collect_daemon_tick: system_id=%s file=%s new_bytes=%s new_lines=%s inserted=%s",
                            system_id,
                            file_path,
                            size - last_size,
                            new_line_count,
                            inserted_for_file,
                        )

                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "collect_daemon_tick: done system_id=%s inserted_total=%s elapsed_ms=%.0f",
                    system_id,
                    total,
                    elapsed_ms,
                )
                return total
            finally:
                ssh.close()

    def initialize(self, system_id: int, task_id: Optional[str] = None) -> bool:
        """Full collect after reinitialize (main + search configs)."""
        tgt = _ssh_target_for_log(system_id)
        rules = self._gather_rules_daemon(system_id)
        logger.info(
            "initialize: begin system_id=%s ssh_target=%s rules=%s task_id=%s",
            system_id,
            tgt,
            len(rules),
            task_id,
        )
        if not rules:
            if task_id:
                progress_manager.complete_task(task_id)
            logger.warning("initialize: no rules, skip system_id=%s", system_id)
            return True
        with self._locked_system(system_id):
            ssh = self._build_ssh(system_id)
            try:
                total_files = 0
                for rule in rules:
                    tr = int(rule.get("time_range_minutes") or 0)
                    d = str(rule.get("log_directory") or "/var/log").strip() or "/var/log"
                    total_files += len(ssh.list_files(d, modified_within_minutes=tr if tr > 0 else 0))
                if task_id:
                    progress_manager.update_task(task_id, total_files=total_files, processed_files=0, total_matches=0)
                processed_files_counter = [0]
                total_matches = 0
                for rule in rules:
                    label = str(rule.get("label") or rule.get("search_text") or "")
                    n = self._rule_collect(
                        system_id,
                        ssh,
                        rule,
                        label,
                        task_id=task_id,
                        processed_files_counter=processed_files_counter,
                        total_files=total_files,
                    )
                    if n is None:
                        return False
                    total_matches += n
                    if task_id:
                        progress_manager.update_task(task_id, total_matches=total_matches)
                logger.info(
                    "initialize: done system_id=%s total_matches=%s task_id=%s",
                    system_id,
                    total_matches,
                    task_id,
                )
                return True
            finally:
                ssh.close()

    def append_logs(
        self,
        system_id: int,
        payload: Optional[dict[str, Any]],
        task_id: Optional[str] = None,
        *,
        use_main_log_config: bool = False,
        cfg_snapshot: Optional[dict[str, Any]] = None,
    ) -> bool:
        """One-shot append using main config snapshot (append_* fields)."""
        cfg = cfg_snapshot if cfg_snapshot is not None else database.get_config(system_id)
        payload = payload or {}
        st = payload.get("search_text")
        if st is None or (isinstance(st, str) and not str(st).strip()):
            st = cfg.get("append_search_text") or cfg.get("search_text") or ""
        tr = payload.get("time_range_minutes")
        if tr is None:
            tr = cfg.get("append_time_range_minutes")
        rule = {
            "log_directory": str(cfg.get("log_directory") or "/var/log").strip() or "/var/log",
            "search_text": str(st).strip() if isinstance(st, str) else str(st),
            "time_range_minutes": database.parse_stored_int(tr, 0),
            "context_before": database.parse_stored_int(
                cfg.get("append_context_before", cfg.get("context_lines_before")), 0
            ),
            "context_after": database.parse_stored_int(
                cfg.get("append_context_after", cfg.get("context_lines_after")), 0
            ),
            "label": str(st).strip() if isinstance(st, str) else str(st),
        }
        with self._locked_system(system_id):
            ssh = self._build_ssh(system_id, cfg_base=cfg)
            try:
                total_files = len(
                    ssh.list_files(
                        rule["log_directory"],
                        modified_within_minutes=rule["time_range_minutes"] if rule["time_range_minutes"] > 0 else 0,
                    )
                )
                if task_id:
                    progress_manager.update_task(task_id, total_files=total_files, processed_files=0, total_matches=0)
                processed_files_counter = [0]
                n = self._rule_collect(
                    system_id,
                    ssh,
                    rule,
                    rule["label"],
                    task_id=task_id,
                    processed_files_counter=processed_files_counter,
                    total_files=total_files,
                )
                if n is None:
                    return False
                if database.parse_stored_int(cfg.get("append_dedupe_same_content"), 1):
                    database.dedupe_logs_by_content(system_id)
                return True
            finally:
                ssh.close()

    def execute_search_configs(
        self, system_id: int, task_id: Optional[str] = None, *, for_scheduled_poll: bool = False
    ) -> None:
        del for_scheduled_poll  # single code path
        configs = database.list_search_configs(system_id)
        rules: list[dict[str, Any]] = []
        for sc in configs:
            if int(sc.get("enabled", 1)) != 1:
                continue
            rules.append(
                {
                    "log_directory": sc.get("log_directory", "/var/log"),
                    "search_text": sc.get("search_text", ""),
                    "time_range_minutes": database.parse_stored_int(sc.get("init_time_range_minutes"), 120),
                    "context_before": int(sc.get("context_lines_before", 0)),
                    "context_after": int(sc.get("context_lines_after", 0)),
                    "label": sc.get("search_text", ""),
                }
            )
        if not rules:
            if task_id:
                progress_manager.update_task(task_id, percentage=100)
            return
        with self._locked_system(system_id):
            ssh = self._build_ssh(system_id)
            try:
                total_files = 0
                for rule in rules:
                    tr = int(rule.get("time_range_minutes") or 0)
                    d = str(rule.get("log_directory") or "/var/log").strip() or "/var/log"
                    total_files += len(ssh.list_files(d, modified_within_minutes=tr if tr > 0 else 0))
                if task_id:
                    progress_manager.update_task(task_id, total_files=total_files, processed_files=0)
                processed_files_counter = [0]
                for rule in rules:
                    label = str(rule.get("label") or "")
                    n = self._rule_collect(
                        system_id,
                        ssh,
                        rule,
                        label,
                        task_id=task_id,
                        processed_files_counter=processed_files_counter,
                        total_files=total_files,
                    )
                    if n is None:
                        return
                if task_id:
                    progress_manager.update_task(task_id, percentage=100)
            finally:
                ssh.close()


class LogCollectorDaemon:
    """Per-system background thread: repeated collect_daemon_tick."""

    def __init__(self, system_id: int, interval_seconds: float, collector: LogCollector):
        self.system_id = system_id
        self.interval_seconds = interval_seconds
        self.collector = collector
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_tick_at: Optional[float] = None
        self.last_inserted_total: int = 0
        self.last_error: Optional[str] = None
        self.last_error_at: Optional[float] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"log-daemon-{self.system_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        logger.info(
            "LogCollectorDaemon: loop start system_id=%s interval_s=%s target=%s",
            self.system_id,
            self.interval_seconds,
            _ssh_target_for_log(self.system_id),
        )
        while not self._stop.is_set():
            tick_t0 = time.perf_counter()
            try:
                n = self.collector.collect_daemon_tick(self.system_id)
                self.last_inserted_total = int(n or 0)
                self.last_tick_at = time.time()
                self.last_error = None
                self.last_error_at = None
                tick_ms = (time.perf_counter() - tick_t0) * 1000
                logger.info(
                    "LogCollectorDaemon: tick_ok system_id=%s inserted=%s tick_elapsed_ms=%.0f",
                    self.system_id,
                    n or 0,
                    tick_ms,
                )
            except Exception as ex:
                self.last_error = f"{type(ex).__name__}: {ex}"
                self.last_error_at = time.time()
                tick_ms = (time.perf_counter() - tick_t0) * 1000
                logger.exception(
                    "LogCollectorDaemon: tick_failed system_id=%s after_ms=%.0f err=%s",
                    self.system_id,
                    tick_ms,
                    self.last_error,
                )
            self._stop.wait(self.interval_seconds)
