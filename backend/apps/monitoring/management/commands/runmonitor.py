"""`python manage.py runmonitor` — run every collector once (seed/refresh)."""
from django.core.management.base import BaseCommand

from apps.monitoring.runner import run_all


class Command(BaseCommand):
    help = "Run all integration collectors once."

    def handle(self, *args, **options):
        results = run_all()
        for name, res in results.items():
            self.stdout.write(f"{name}: {res}")
