from django.utils import timezone

from apps.monitoring.models import Activity, Service


def upsert_service(name, type, status, metadata=None):
    prev = Service.objects.filter(name=name, type=type).values_list("status", flat=True).first()
    Service.objects.update_or_create(
        name=name,
        type=type,
        defaults={
            "status": status,
            "last_checked": timezone.now(),
            "metadata": metadata or {},
        },
    )
    # Push a Discord alert only when a service first goes bad, not every poll.
    if status in ("down", "degraded") and prev not in ("down", "degraded"):
        # Imported lazily to avoid a circular import at module load.
        from apps.notifications.service import notify
        severity = "critical" if status == "down" else "warning"
        notify(severity, f"{name} is {status}",
               (metadata or {}).get("error", f"{name} reported {status}."),
               source=type, discord=True)


def log_activity(service, event, metadata=None):
    Activity.objects.create(service=service, event=event, metadata=metadata or {})


def get_recent_activity(service=None, limit=10):
    qs = Activity.objects.all().order_by("-timestamp")

    if service:
        qs = qs.filter(service=service)

    return qs[:limit]


def get_service(name):
    return Service.objects.filter(name=name).first()
