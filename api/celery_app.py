"""
The one Celery application instance every task in api/workers.py registers
against. Split out of workers.py so anything needing to reference the app
(a future admin CLI, tests overriding broker settings) doesn't have to
import workers.py itself and its task side effects.
"""

from __future__ import annotations

from celery import Celery

from common.config import load_settings


def make_celery_app() -> Celery:
    settings = load_settings()
    if settings.celery_task_always_eager:
        # No real worker process consumes this broker in eager mode - a
        # task call runs in-process immediately - so there is nothing for
        # a real network broker/backend to do. BUG FOUND via testing:
        # pointing broker/backend at redis_url even in eager mode still
        # made Celery attempt a real TCP connection at task-call time
        # (result-backend bookkeeping), hanging for minutes against a
        # redis_url nothing is listening on in this environment. This is
        # deliberately decoupled from api/store.py's OWN Redis-backed
        # JobStore, which is a completely separate Redis usage.
        app = Celery("recut", broker="memory://", backend="cache+memory://")
    else:
        app = Celery("recut", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.task_always_eager = settings.celery_task_always_eager
    return app


celery_app = make_celery_app()
