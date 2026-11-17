import uuid
from django.db import models
from django.conf import settings
from organizations.models import Facility
from projects.models import MaterialLot


class SampleStatus(models.TextChoices):
    REGISTERED = 'REGISTERED', 'Registered at Origin'
    DISPATCHED = 'DISPATCHED', 'Dispatched in Transit'
    RECEIVED = 'RECEIVED', 'Received at Laboratory'
    PREPARATION = 'PREPARATION', 'Specimen Preparation / Diamond Cutting'
    TESTING = 'TESTING', 'Active Testing on Benches'
    QA_REVIEW = 'QA_REVIEW', 'QA Outlier & Tolerance Review'
    REPORT_ISSUED = 'REPORT_ISSUED', 'Inspection Certificate Released'
    STORED = 'STORED', 'Archived in Counter-Sample Storage'
    
    # Exception states
    HELD_DAMAGED = 'HELD_DAMAGED', 'Held: Packaging Damage / Moisture Exposure'
    REJECTED = 'REJECTED', 'Rejected / Non-Compliant Lot'


class Sample(models.Model):
    """
    Permanent laboratory sample parent entity. Retains single permanent record across facilities.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample_code = models.CharField(max_length=50, unique=True, db_index=True, help_text="e.g. DC-SMP-2026-0842")
    material_lot = models.ForeignKey(MaterialLot, on_delete=models.PROTECT, related_name='samples')
    current_facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='housed_samples')
    status = models.CharField(max_length=30, choices=SampleStatus.choices, default=SampleStatus.REGISTERED)
    quantity_bricks = models.PositiveIntegerField(help_text="Whole refractory brick units in lot delivery")
    sampling_date = models.DateField()
    sampled_by = models.CharField(max_length=150, help_text="Inspector who sampled per ISO 5022 / R-01")
    is_counter_sample = models.BooleanField(default=False, help_text="Retained 24 months per Procedure R-01 §6")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sample_code} ({self.material_lot.lot_number}) [{self.get_status_display()}]"


class SampleCollection(models.Model):
    """
    On-site representative sampling record per ISO 5022.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.OneToOneField(Sample, on_delete=models.CASCADE, related_name='collection_record')
    location_description = models.CharField(max_length=200, help_text="Pallet numbers, kiln car IDs, or warehouse bay")
    sampling_protocol = models.CharField(max_length=100, default='ISO 5022 / Procedure R-01 §1')
    courier_tracking_no = models.CharField(max_length=100, blank=True)
    dispatch_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PackagingCondition(models.TextChoices):
    INTACT = 'INTACT', 'Intact Pallet & Moisture Barrier'
    DAMAGED_CRUSHED = 'DAMAGED_CRUSHED', 'Physical Pallet Damage / Crushed'
    DAMAGED_MOISTURE = 'DAMAGED_MOISTURE', 'Moisture Wrap Compromised'
    DAMAGED_CHIPPED = 'DAMAGED_CHIPPED', 'Excessive Corner Chipping'


class SampleReceipt(models.Model):
    """
    Formal receipt and intake checklist verification at testing facility.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.OneToOneField(Sample, on_delete=models.CASCADE, related_name='receipt_record')
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='received_samples')
    received_date = models.DateTimeField(auto_now_add=True)
    packaging_condition = models.CharField(max_length=40, choices=PackagingCondition.choices, default=PackagingCondition.INTACT)
    moisture_barrier_intact = models.BooleanField(default=True)
    heat_numbers_verified = models.BooleanField(default=True)
    is_accepted = models.BooleanField(default=True)
    discrepancy_remarks = models.TextField(blank=True)

    def __str__(self):
        return f"Receipt for {self.sample.sample_code} (Accepted={self.is_accepted})"


class SamplePhoto(models.Model):
    """
    Photographic evidence of intake pallets, damage, or witness core sections.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name='photos')
    image_url = models.CharField(max_length=500, help_text="Stored asset URL")
    caption = models.CharField(max_length=255)
    is_damage_evidence = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class SpecimenStatus(models.TextChoices):
    PREPARED = 'PREPARED', 'Prepared & Ground Planar'
    ASSIGNED = 'ASSIGNED', 'Assigned to Work Order'
    TESTING = 'TESTING', 'Under Active Test'
    TESTED = 'TESTED', 'Tested (Destructive)'
    REJECTED = 'REJECTED', 'Specimen Rejected (Cutting Defect / Microcrack)'


class Specimen(models.Model):
    """
    Sub-sampled physical testing specimen prepared from parent brick (Child specimen).
    Tracks parent-child genealogy.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    specimen_code = models.CharField(max_length=60, unique=True, db_index=True, help_text="e.g. DC-SMP-2026-0842-SP01")
    parent_sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name='specimens')
    sub_index = models.PositiveSmallIntegerField(help_text="Specimen index #1, #2, #3...")
    geometry = models.CharField(max_length=100, help_text="e.g. Cylinder 50mm dia x 50mm h or Prism 150x25x25mm")
    length_mm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    width_mm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    height_mm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    planarity_checked = models.BooleanField(default=True, help_text="Ground planar to ±0.05 mm per ISO norms")
    status = models.CharField(max_length=30, choices=SpecimenStatus.choices, default=SpecimenStatus.PREPARED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('parent_sample', 'sub_index')
        ordering = ['parent_sample', 'sub_index']

    def __str__(self):
        return f"{self.specimen_code} ({self.geometry})"


class PreparationRecord(models.Model):
    """
    Record of diamond saw cutting and planar grinding before testing.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    specimen = models.OneToOneField(Specimen, on_delete=models.CASCADE, related_name='preparation_record')
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='prepared_specimens')
    cutting_tool_used = models.CharField(max_length=100, default='Diamond Wet Saw')
    grinding_surface_dry = models.BooleanField(default=True)
    drying_oven_temp_c = models.PositiveIntegerField(default=110, help_text="Drying temperature (110°C) per ISO norms")
    drying_duration_hours = models.DecimalField(max_digits=4, decimal_places=1, default=12.0)
    completed_at = models.DateTimeField(auto_now_add=True)


class SampleTransfer(models.Model):
    """
    Chain-of-custody transfer between testing bays or external sister laboratories.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name='transfers')
    from_facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='outbound_transfers')
    to_facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='inbound_transfers')
    transferred_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=200, help_text="Specialized high-temp creep or WD-XRF testing")
    transferred_at = models.DateTimeField(auto_now_add=True)
