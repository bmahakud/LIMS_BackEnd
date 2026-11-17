import uuid
from django.db import models


class InquiryStatus(models.TextChoices):
    NEW = 'NEW', 'New Intake'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
    CONTACTED = 'CONTACTED', 'Client Contacted'
    CONVERTED = 'CONVERTED', 'Converted to Testing Project'
    CLOSED = 'CLOSED', 'Closed / Archived'


class Inquiry(models.Model):
    """
    Public testing enquiry submitted through the public portal.
    Stores inquiries with privacy retention and abuse tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    organization = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    sample_type = models.CharField(max_length=150, blank=True)
    timeline = models.CharField(max_length=100, blank=True)
    message = models.TextField()
    test_requirements = models.JSONField(default=list, blank=True, help_text="List of requested test codes or names")

    status = models.CharField(max_length=30, choices=InquiryStatus.choices, default=InquiryStatus.NEW)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Public Inquiry'
        verbose_name_plural = 'Public Inquiries'

    def __str__(self):
        return f"[{self.status}] {self.name} - {self.organization} ({self.created_at.strftime('%Y-%m-%d')})"
