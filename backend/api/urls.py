from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("services", views.ServiceViewSet)
router.register("alerts", views.AlertViewSet)
router.register("tasks", views.TaskViewSet)
router.register("activity", views.ActivityViewSet)
router.register("notifications", views.NotificationViewSet)

urlpatterns = [
    path("summary/", views.summary),
    path("refresh/", views.refresh),
    path("assistant/", views.assistant),
    path("render/<str:service_id>/logs/", views.render_logs),
    path("render/<str:service_id>/deploy/", views.render_deploy),
    path("", include(router.urls)),
]
