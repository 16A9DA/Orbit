from django.utils import timezone

from apps.monitoring.models import Activity, Service


def upsert_service(name, type, status, metadata=None):
    Service.objects.update_or_create(
        name=name,
        type=type,
        defaults={
            "status": status,
            "last_checked": timezone.now(),
            "metadata": metadata or {},
        },
    )


def log_activity(service, event, metadata=None):
    Activity.objects.create(service=service, event=event, metadata=metadata or {})


def get_recent_activity(service=None, limit=10):
    qs = Activity.objects.all().order_by("-created_at")

    if service:
        qs = qs.filter(service=service)

    return qs[:limit]


def get_service(name):
    return Service.objects.filter(name=name).first()
