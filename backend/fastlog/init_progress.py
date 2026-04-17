import threading
import uuid
from copy import deepcopy


class InitProgressManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks = {}

    def create_task(self):
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = {
                "status": "running",
                "total_files": 0,
                "processed_files": 0,
                "total_matches": 0,
                "current_file": "",
                "percentage": 0,
                "error": None,
                "cancel_requested": False,
            }
        return task_id

    def update_task(self, task_id, **kwargs):
        with self._lock:
            if task_id not in self._tasks:
                return
            self._tasks[task_id].update(kwargs)

    def complete_task(self, task_id):
        self.update_task(task_id, status="completed", percentage=100)

    def fail_task(self, task_id, error):
        self.update_task(task_id, status="error", error=str(error))

    def cancel_task(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.get("status") in ("completed", "error", "cancelled"):
                return False
            task["cancel_requested"] = True
            return True

    def is_cancel_requested(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            return bool(task and task.get("cancel_requested"))

    def mark_cancelled(self, task_id):
        self.update_task(task_id, status="cancelled")

    def get_task(self, task_id):
        with self._lock:
            return deepcopy(self._tasks.get(task_id))


progress_manager = InitProgressManager()
