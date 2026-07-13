import os
import threading
import webbrowser

from django.contrib.staticfiles.management.commands.runserver import Command as RunserverCommand

from apps.monitoring.runner import start_background

URL = "http://127.0.0.1:8000/"


class Command(RunserverCommand):
    help = "Run the dashboard server, start monitoring, open the browser."

    def handle(self, *args, **options):
        # RUN_MAIN is set only in the reloader child, so this fires once.
        if os.environ.get("RUN_MAIN") != "true":
            threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
        start_background()
        super().handle(*args, **options)
