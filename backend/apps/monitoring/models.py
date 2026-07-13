from django.db import models


class Service(models.Model):
    STATUS = [
        ("operational", "Operational"),
        ("degraded", "Degraded"),
        ("down", "Down"),
        ("unknown", "Unknown"),
    ]
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=60)  # github, render, gcp, sendgrid, notion
    status = models.CharField(max_length=20, choices=STATUS, default="unknown")
    last_checked = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("name", "type")
        ordering = ["type", "name"]

    def __str__(self):
        return f"{self.type}:{self.name}"


class Alert(models.Model):
    SEVERITY = [
        ("critical", "Critical"),
        ("warning", "Warning"),
        ("success", "Success"),
        ("info", "Info"),
    ]
    severity = models.CharField(max_length=20, choices=SEVERITY)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.severity}] {self.title}"


class Task(models.Model):
    PRIORITY = [("high", "High"), ("medium", "Medium"), ("low", "Low")]
    STATUS = [("todo", "Todo"), ("in_progress", "In Progress"), ("done", "Done")]
    source = models.CharField(max_length=60, default="manual")
    external_id = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=300)
    priority = models.CharField(max_length=20, choices=PRIORITY, default="medium")
    status = models.CharField(max_length=20, choices=STATUS, default="todo")
    deadline = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["deadline", "priority"]

    def __str__(self):
        return self.title


class Activity(models.Model):
    service = models.CharField(max_length=60)
    event = models.CharField(max_length=300)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "activities"

    def __str__(self):
        return f"{self.service}: {self.event}"


class Notification(models.Model):
    severity = models.CharField(max_length=20, default="info")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    read = models.BooleanField(default=False)
    delivered_discord = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
