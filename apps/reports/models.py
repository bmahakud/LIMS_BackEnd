import uuid
from django.db import models
from django.conf import settings
from projects.models import Project, MaterialLot
from samples.models import Sample
from quality.models import FinalDecision


class ReportStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft Preview'
    ISSUED = 'ISSUED', 'Approved & Issued (Locked)'
    REVISED = 'REVISED', 'Superseded by Revision'


class LaboratoryReport(models.Model):
    """
    Individual Sample Inspection Report / Certificate of Analysis.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_number = models.CharField(max_length=60, unique=True, db_index=True, help_text="e.g. DC-REP-2026-0842")
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name='reports')
    final_decision = models.OneToOneField(FinalDecision, on_delete=models.PROTECT, related_name='laboratory_report')
    status = models.CharField(max_length=20, choices=ReportStatus.choices, default=ReportStatus.DRAFT)
    revision_number = models.PositiveSmallIntegerField(default=1)
    
    # Snapshot payload stored immutably upon issuance
    report_snapshot_json = models.JSONField(default=dict, blank=True)
    pdf_file_path = models.CharField(max_length=500, blank=True)
    sha256_hash = models.CharField(max_length=64, blank=True)
    
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='issued_lab_reports')
    issued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.report_number} [{self.status}]"


class ConsolidatedReport(models.Model):
    """
    Project or Relining Campaign Consolidated Certificate of Refractory Characterization (CRC).
    Supports multiple samples/lots in a relining campaign, preserving sample-specific columns.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    crc_number = models.CharField(max_length=60, unique=True, db_index=True, help_text="e.g. DC-CRC-2026-BF6-01")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name='consolidated_reports')
    title = models.CharField(max_length=255, default='Consolidated Certificate of Refractory Characterization (CRC)')
    status = models.CharField(max_length=20, choices=ReportStatus.choices, default=ReportStatus.DRAFT)
    samples = models.ManyToManyField(Sample, related_name='consolidated_in')
    
    # Immutable snapshot payload
    report_snapshot_json = models.JSONField(default=dict, blank=True)
    pdf_file_path = models.CharField(max_length=500, blank=True)
    sha256_hash = models.CharField(max_length=64, blank=True)
    
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='approved_crc_reports')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.crc_number} - {self.project.code} [{self.status}]"


class ReportRevision(models.Model):
    """
    Revision tracking when an issued report requires a formal amendment.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    laboratory_report = models.ForeignKey(LaboratoryReport, on_delete=models.CASCADE, related_name='revisions')
    revision_number = models.PositiveSmallIntegerField()
    reason_for_amendment = models.TextField()
    previous_snapshot_json = models.JSONField()
    revised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    revised_at = models.DateTimeField(auto_now_add=True)
