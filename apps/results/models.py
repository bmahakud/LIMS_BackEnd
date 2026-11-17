import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from work_orders.models import TestAssignment
from test_catalogue.models import TestMethod
from laboratory.models import Instrument


class TestRunStatus(models.TextChoices):
    RUNNING = 'RUNNING', 'Running on Bench'
    COMPLETED = 'COMPLETED', 'Execution Completed'
    ABORTED = 'ABORTED', 'Aborted / Machine Tripped'


class TestRun(models.Model):
    """
    Physical execution run of a TestAssignment on an Instrument or manual test bench.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(TestAssignment, on_delete=models.CASCADE, related_name='test_runs')
    run_number = models.PositiveSmallIntegerField(default=1)
    technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='executed_runs')
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name='runs')
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=TestRunStatus.choices, default=TestRunStatus.RUNNING)
    ambient_temp_c = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal('22.0'))
    ambient_relative_humidity_pct = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal('50.0'))
    remarks = models.TextField(blank=True)

    class Meta:
        unique_together = ('assignment', 'run_number')
        ordering = ['assignment', 'run_number']

    def __str__(self):
        return f"{self.assignment.specimen.specimen_code} - Run #{self.run_number} ({self.status})"


class ComparisonQualifier(models.TextChoices):
    NONE = 'NONE', 'Exact (=)'
    LESS_THAN = 'LT', 'Less than (<)'
    LESS_THAN_OR_EQUAL = 'LTE', 'Less than or equal (<=)'
    GREATER_THAN = 'GT', 'Greater than (>)'
    GREATER_THAN_OR_EQUAL = 'GTE', 'Greater than or equal (>=)'
    APPROX = 'APPROX', 'Approximately (~)'


class Measurement(models.Model):
    """
    Individual raw metrological observation (dry weight, soaked weight, max load kN, displacement mm).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='measurements')
    parameter_name = models.CharField(max_length=100, help_text="e.g. Dry Mass m1, Hydrostatic Mass m2, Peak Load Fmax")
    raw_input_text = models.CharField(max_length=100, help_text="Verbatim reading as entered by technician")
    numeric_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    qualifier = models.CharField(max_length=10, choices=ComparisonQualifier.choices, default=ComparisonQualifier.NONE)
    unit = models.CharField(max_length=30)
    measured_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.parameter_name}: {self.raw_input_text} {self.unit}"


class VerificationStatus(models.TextChoices):
    UNVERIFIED = 'UNVERIFIED', 'Unverified / Draft'
    VERIFIED = 'VERIFIED', 'Scientifically Verified by Metallurgist'
    REJECTED = 'REJECTED', 'Rejected / Re-measurement Required'


class Result(models.Model):
    """
    Synthesized scientific test result for a Specimen and TestMethod.
    Never treats qualified values (e.g. '>1600') as exact numbers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    test_run = models.ForeignKey(TestRun, on_delete=models.PROTECT, related_name='results')
    test_method = models.ForeignKey(TestMethod, on_delete=models.PROTECT)
    parameter_code = models.CharField(max_length=40, help_text="CCS, BD, AP, PLC, RUL, CREEP, Al2O3, Fe2O3")
    
    # Value representation
    raw_input_text = models.CharField(max_length=100, help_text="e.g. 108.4 or >1680 or <0.05")
    numeric_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    qualifier = models.CharField(max_length=10, choices=ComparisonQualifier.choices, default=ComparisonQualifier.NONE)
    unit = models.CharField(max_length=30)
    
    # Provenance
    is_manual_entry = models.BooleanField(default=True)
    technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='recorded_results')
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    # Revision & Verification
    revision_number = models.PositiveSmallIntegerField(default=1)
    verification_status = models.CharField(
        max_length=30, choices=VerificationStatus.choices, default=VerificationStatus.UNVERIFIED
    )
    is_latest = models.BooleanField(default=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        qual = f"{self.get_qualifier_display()} " if self.qualifier != ComparisonQualifier.NONE else ""
        return f"{self.parameter_code}: {qual}{self.numeric_value or self.raw_input_text} {self.unit} ({self.verification_status})"


class ResultRevision(models.Model):
    """
    Audit snapshot of historical result values before amendment.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result = models.ForeignKey(Result, on_delete=models.CASCADE, related_name='revisions')
    revision_number = models.PositiveSmallIntegerField()
    previous_raw_text = models.CharField(max_length=100)
    previous_numeric_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    reason_for_change = models.TextField()
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)


class ResultVerification(models.Model):
    """
    Formal sign-off by a Lead Metallurgist verifying mathematical & metrological correctness.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result = models.OneToOneField(Result, on_delete=models.CASCADE, related_name='verification')
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='verifications')
    verified_at = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(blank=True)


class RetestStatus(models.TextChoices):
    REQUESTED = 'REQUESTED', 'Retest Requested'
    APPROVED = 'APPROVED', 'Approved by QA Director'
    SPECIMEN_CUT = 'SPECIMEN_CUT', 'Reserve Specimen Prepared'
    COMPLETED = 'COMPLETED', 'Retest Completed'


class RetestRequest(models.Model):
    """
    Traceable retest request when a statistical outlier or mechanical defect is detected.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_result = models.ForeignKey(Result, on_delete=models.PROTECT, related_name='retest_requests')
    reason = models.TextField(help_text="e.g. Statistical outlier per Grubbs' test or pre-existing microcrack observed.")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_retests')
    status = models.CharField(max_length=30, choices=RetestStatus.choices, default=RetestStatus.REQUESTED)
    requested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Retest for {self.original_result.parameter_code} on {self.original_result.test_run.assignment.specimen.specimen_code}"
