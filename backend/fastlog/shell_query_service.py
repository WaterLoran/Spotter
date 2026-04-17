from datetime import datetime

from fastlog import database
from fastlog.ssh_client import SSHClient, SSHConfig


class ShellQueryService:
    def __init__(self):
        self._polling_tasks = []

    def _get_ssh(self, system_id):
        cfg = database.get_config(system_id)
        return SSHClient(
            SSHConfig(
                host=cfg.get("server_host", "127.0.0.1"),
                username=cfg.get("server_username", "root"),
                password=cfg.get("server_password", ""),
                port=int(cfg.get("server_port", 22)),
            )
        )

    def _calc_diff(self, prev_output, curr_output, ignore_patterns=""):
        ignores = [i.strip() for i in (ignore_patterns or "").split(";") if i.strip()]
        prev_lines = prev_output.splitlines()
        curr_lines = curr_output.splitlines()
        diff_lines = []
        max_len = max(len(prev_lines), len(curr_lines))
        for idx in range(max_len):
            prev = prev_lines[idx] if idx < len(prev_lines) else ""
            curr = curr_lines[idx] if idx < len(curr_lines) else ""
            if any((p in prev) or (p in curr) for p in ignores):
                continue
            if prev != curr:
                diff_lines.append({"line_no": idx + 1, "prev": prev, "curr": curr})
        return diff_lines

    def execute_query(self, system_id, query_id):
        queries = database.list_shell_queries(system_id)
        query = next((q for q in queries if int(q["id"]) == int(query_id)), None)
        if not query:
            raise ValueError("查询不存在")
        ssh = self._get_ssh(system_id)
        output, err = ssh.execute_command(query["command"])
        ssh.close()
        full = output if output else err
        history = database.list_shell_query_history(query_id)
        prev = history[0]["full_output"] if history else ""
        diff_lines = self._calc_diff(prev, full, query.get("ignore_patterns", ""))
        hid = database.add_shell_query_history(query_id, full, bool(diff_lines), diff_lines)
        return {
            "history_id": hid,
            "executed_at": datetime.utcnow().isoformat(sep=" "),
            "is_different": bool(diff_lines),
            "diff_lines": diff_lines,
            "full_output": full,
        }

    def list_polling_tasks(self):
        return self._polling_tasks
