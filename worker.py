from __future__ import annotations

import os

from redis import Redis
from rq import Worker

from app import create_app


class RecoveringWorker(Worker):
    def run_maintenance_tasks(self):
        super().run_maintenance_tasks()
        from huishi.media_tasks import recover_video_tasks
        from huishi.db import close_db
        try:
            recover_video_tasks(self.huishi_app)
        except Exception:
            # A temporary database/queue outage must not terminate the worker.
            self.huishi_app.logger.exception('Video recovery maintenance deferred')
        finally:
            close_db()


def main() -> None:
    app = create_app()
    redis_url = str(app.config.get("REDIS_URL") or "").strip()
    if not redis_url:
        raise RuntimeError("HUISHI_REDIS_URL must be set before starting the RQ worker")
    queue_name = str(app.config.get("RQ_QUEUE_NAME", "huishi-generation"))
    connection = Redis.from_url(redis_url)
    with app.app_context():
        worker = RecoveringWorker([queue_name], connection=connection, maintenance_interval=60)
        worker.huishi_app = app
        worker.work(with_scheduler=os.environ.get("HUISHI_RQ_WITH_SCHEDULER", "0") == "1")


if __name__ == "__main__":
    main()
