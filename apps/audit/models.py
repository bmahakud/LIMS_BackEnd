import uuid
from django.db import models
from django.conf import settings


class AuditAction(models.TextChoices):
    CREATE = 'CREATE', 'Created Entity'
    UPDATE = 'UPDATE', 'Updated Record'
    VERIFY = 'VERIFY', 'Verified Results'
    DECIDE = 'DECIDE', 'Final QA Decision'
    ISSUE_REPORT = 'ISSUE_REPORT', 'Issued Consolidated Report'
    RETEST = 'RETEST', 'Requested Retest'


class AuditEvent(models.Model):
    """
    Immutable ISO/IEC 17025 audit trail logging every change, scientific verification, and approval.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='audit_events')
    action = models.CharField(max_length=40, choices=AuditAction.choices)
    entity_type = models.CharField(max_length=100, db_index=True)
    entity_id = models.CharField(max_length=100, db_index=True)
    summary = models.TextField()
    changes_json = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.actor.email} {self.action} on {self.entity_type}:{self.entity_id}"
