from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler


class PollingManager:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.jobs = {}
        self.scheduler.start()

    def upsert_job(self, job_id, func, seconds):
        self.remove_job(job_id)
        self.jobs[job_id] = {"seconds": seconds, "last_executed_at": None, "status": "running"}

        def wrapped():
            self.jobs[job_id]["last_executed_at"] = datetime.utcnow().isoformat(sep=" ")
            return func()

        self.scheduler.add_job(wrapped, "interval", seconds=max(1, int(seconds)), id=job_id, replace_existing=True)

    def remove_job(self, job_id):
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        self.jobs.pop(job_id, None)

    def list_jobs(self):
        return [{"id": k, **v} for k, v in self.jobs.items()]
