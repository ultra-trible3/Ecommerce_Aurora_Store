"""Dashboard models: admin audit log."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AdminAuditLog(models.Model):
    """Audit trail of all admin actions."""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=30, db_index=True)
    object_type = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=100, blank=True, db_index=True)
    object_repr = models.CharField(max_length=200)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("admin audit log")
        verbose_name_plural = _("admin audit logs")
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["action", "-created_at"]),
        ]
    
    def __str__(self):
        return f"{self.user} — {self.action} — {self.object_type} ({self.object_id})"