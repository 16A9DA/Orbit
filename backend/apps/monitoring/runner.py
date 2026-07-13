"""Run every integration collector once, or on a loop in a background thread."""
import logging
import threading
import time

from django.conf import settings

from apps.github import service as github
from apps.google_cloud import service as gcp
from apps.notion import service as notion
from apps.render import service as render
from apps.sendgrid import service as sendgrid

log = logging.getLogger(__name__)

COLLECTORS = {
    "github": github.collect,
    "render": render.collect,
    "gcp": gcp.collect,
    "sendgrid": sendgrid.collect,
    "notion": notion.collect,
}


def run_all():
    results = {}
    for name, fn in COLLECTORS.items():
        try:
            results[name] = fn()
        except Exception as e:  # one bad integration must not stop the rest
            log.exception("Collector %s crashed", name)
            results[name] = {"error": str(e)}
    return results


_started = False


def start_background():
    """Idempotent: launch one daemon thread polling every SCHEDULER_INTERVAL seconds."""
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            run_all()
            time.sleep(settings.SCHEDULER_INTERVAL)

    threading.Thread(target=loop, daemon=True, name="dashboard-scheduler").start()
    log.info("Background scheduler started (interval=%ss)", settings.SCHEDULER_INTERVAL)
