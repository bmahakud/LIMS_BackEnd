import uuid
from django.db import models
from django.conf import settings
from laboratory.models import Laboratory, Instrument
from test_catalogue.models import TestMethod
from samples.models import Specimen


class WorkOrderStatus(models.TextChoices):
    PLANNED = 'PLANNED', 'Work Order Planned'
    SCHEDULED = 'SCHEDULED', 'Scheduled on Benches'
    IN_PROGRESS = 'IN_PROGRESS', 'Testing in Progress'
    COMPLETED = 'COMPLETED', 'All Tests Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class WorkOrder(models.Model):
    """
    Formal laboratory work authorization grouping specimen assignments.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=50, unique=True, db_index=True, help_text="e.g. WO-2026-0312")
    laboratory = models.ForeignKey(Laboratory, on_delete=models.PROTECT, related_name='work_orders')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_work_orders')
    status = models.CharField(max_length=30, choices=WorkOrderStatus.choices, default=WorkOrderStatus.PLANNED)
    priority = models.CharField(max_length=20, choices=[('ROUTINE','Routine'), ('URGENT','Urgent Relining Campaign'), ('CRITICAL','Critical Outage Emergency')], default='ROUTINE')
    target_completion_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_number} [{self.get_status_display()}]"


class AssignmentStatus(models.TextChoices):
    QUEUED = 'QUEUED', 'Queued for Bench'
    RUNNING = 'RUNNING', 'Running Test Cycle'
    PASSED = 'PASSED', 'Completed: Meets DC-SPEC'
    DEVIATION = 'DEVIATION', 'Completed: Technical Deviation'
    FAILED = 'FAILED', 'Completed: Rejection'
    ABORTED = 'ABORTED', 'Aborted / Power Failure'


class TestAssignment(models.Model):
    """
    Individual test execution assigned to a prepared specimen on an instrument.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='assignments')
    specimen = models.ForeignKey(Specimen, on_delete=models.PROTECT, related_name='assignments')
    test_method = models.ForeignKey(TestMethod, on_delete=models.PROTECT, related_name='assignments')
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name='assignments')
    assigned_technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='test_assignments')
    
    # Required testing conditions
    test_temperature_c = models.PositiveIntegerField(null=True, blank=True, help_text="e.g. 1500°C for Creep / 1680°C for RUL")
    soaking_time_hours = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="e.g. 50.0 hours for Creep")
    applied_load_mpa = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True, help_text="e.g. 0.200 MPa for RUL/Creep")
    
    status = models.CharField(max_length=30, choices=AssignmentStatus.choices, default=AssignmentStatus.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['work_order', 'specimen']

    def __str__(self):
        return f"{self.work_order.order_number} - {self.specimen.specimen_code} ({self.test_method.standard_code})"
