from dataclasses import dataclass
import logging

import paramiko

logger = logging.getLogger(__name__)

@dataclass
class SSHConfig:
    host: str
    username: str
    password: str
    port: int = 22
    timeout: int = 10


class SSHClient:
    def __init__(self, config: SSHConfig):
        self.config = config
        self.client = None

    def connect(self):
        if self.client:
            return
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=self.config.host,
            username=self.config.username,
            password=self.config.password,
            port=self.config.port,
            timeout=self.config.timeout,
        )

    def execute_command(self, command: str):
        self.connect()
        _, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        if err.strip():
            logger.warning(
                "SSH ERR [%s:%s] cmd=%r err=%r",
                self.config.host,
                self.config.port,
                command[:200],
                err[:300],
            )
        return out, err

    def _quote(self, path: str) -> str:
        """POSIX single-quote escape for shell arguments."""
        return "'" + path.replace("'", "'\"'\"'") + "'"

    def list_files(self, directory: str, modified_within_minutes: int = 0):
        """List regular files under directory.

        If modified_within_minutes > 0, returns files whose *modification time*
        OR *creation/birth time* falls within that many minutes.  Using the union
        of both predicates ensures that closed log files (whose mtime is the last
        write, which may be slightly older than the window) are not skipped when
        they were created within the window.

        ``-Bmin`` (birth time) is supported on macOS/BSD; on Linux it silently
        produces no output so the result degrades gracefully to mtime-only.
        ``sort -u`` deduplicates the combined list.
        """
        mmin = int(modified_within_minutes or 0)
        if mmin > 0:
            cmd = (
                f"{{ find {directory} -type f -mmin -{mmin} 2>/dev/null;"
                f" find {directory} -type f -Bmin -{mmin} 2>/dev/null; }}"
                f" | sort -u"
            )
        else:
            cmd = f"find {directory} -type f 2>/dev/null"
        out, _ = self.execute_command(cmd)
        return [line.strip() for line in out.splitlines() if line.strip()]

    def get_file_stat(self, file_path: str) -> tuple[int, int]:
        """Return (size_bytes, mtime_unix) for a remote file.
        Tries GNU stat (Linux) first, falls back to BSD stat (macOS/FreeBSD).
        Returns (0, 0) on any error (file missing, stat unavailable, etc.).
        """
        q = self._quote(file_path)
        # GNU stat (Linux): -c '%s %Y'  |  BSD stat (macOS): -f '%z %m'
        cmd = f"stat -c '%s %Y' {q} 2>/dev/null || stat -f '%z %m' {q} 2>/dev/null || echo '0 0'"
        out, _ = self.execute_command(cmd)
        parts = out.strip().split()
        try:
            return int(parts[0]), int(parts[1])
        except (IndexError, ValueError):
            return 0, 0

    def read_bytes_from(self, file_path: str, offset: int) -> str:
        """Read file content from byte *offset* to EOF.
        Uses ``tail -c +N`` where N = offset + 1 (1-indexed).
        Returns empty string on error.
        """
        q = self._quote(file_path)
        start = max(1, offset + 1)
        out, _ = self.execute_command(f"tail -c +{start} {q} 2>/dev/null")
        return out

    def test_connection(self):
        try:
            self.connect()
            out, _ = self.execute_command("echo ok")
            return {"ok": out.strip() == "ok"}
        except Exception as ex:
            # Do not propagate: UI expects 200 + data.ok false, not HTTP 500
            msg = f"{type(ex).__name__}: {ex}"
            logger.warning(
                "SSH test_connection failed host=%s port=%s: %s",
                self.config.host,
                self.config.port,
                msg[:300],
            )
            return {"ok": False, "error": msg[:500]}
        finally:
            self.close()

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
