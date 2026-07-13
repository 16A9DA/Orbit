from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.assistant.service import ask
from apps.monitoring.models import Activity, Alert, Notification, Service, Task
from apps.monitoring.runner import run_all

from .serializers import (
    ActivitySerializer,
    AlertSerializer,
    NotificationSerializer,
    ServiceSerializer,
    TaskSerializer,
)


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer


class AlertViewSet(viewsets.ModelViewSet):
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer


class ActivityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Activity.objects.all()[:100]
    serializer_class = ActivitySerializer


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer


@api_view(["GET"])
def summary(request):
    services = Service.objects.all()
    return Response({
        "services": ServiceSerializer(services, many=True).data,
        "counts": {
            "services": services.count(),
            "degraded": services.filter(status__in=["down", "degraded"]).count(),
            "alerts_critical": Alert.objects.filter(resolved=False, severity="critical").count(),
            "alerts_warning": Alert.objects.filter(resolved=False, severity="warning").count(),
            "tasks_open": Task.objects.exclude(status="done").count(),
            "unread": Notification.objects.filter(read=False).count(),
        },
        "alerts": AlertSerializer(Alert.objects.filter(resolved=False)[:20], many=True).data,
        "tasks": TaskSerializer(Task.objects.exclude(status="done")[:20], many=True).data,
        "activity": ActivitySerializer(Activity.objects.all()[:25], many=True).data,
    })


@api_view(["POST"])
def refresh(request):
    return Response(run_all())


@api_view(["POST"])
def assistant(request):
    question = request.data.get("question", "").strip()
    if not question:
        return Response({"error": "question required"}, status=400)
    return Response({"answer": ask(question)})
