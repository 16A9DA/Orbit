from django.contrib import admin

from .models import Activity, Alert, Notification, Service, Task

for m in (Service, Alert, Task, Activity, Notification):
    admin.site.register(m)
