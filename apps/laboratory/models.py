import uuid
from django.db import models
from organizations.models import Facility, LaboratoryArea


class Laboratory(models.Model):
    """
    Accredited testing laboratory instance hosted at a physical Facility.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    facility = models.OneToOneField(Facility, on_delete=models.CASCADE, related_name='testing_laboratory')
    name = models.CharField(max_length=200)
    accreditation_scope = models.CharField(max_length=150, default='ISO/IEC 17025:2017 Accredited')
    is_operational = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} [{self.facility.code}]"


class Instrument(models.Model):
    """
    Calibrated laboratory apparatus (high-temperature furnace, load frame, XRF spectrometer).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_tag = models.CharField(max_length=50, unique=True, help_text="e.g. EQ-FURN-01")
    name = models.CharField(max_length=150)
    laboratory = models.ForeignKey(Laboratory, on_delete=models.CASCADE, related_name='instruments')
    area = models.ForeignKey(LaboratoryArea, on_delete=models.SET_NULL, null=True, blank=True, related_name='instruments')
    manufacturer = models.CharField(max_length=100)
    model_number = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, unique=True)
    max_temperature_c = models.PositiveIntegerField(null=True, blank=True)
    max_load_kn = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_operational = models.BooleanField(default=True)
    next_calibration_due = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['asset_tag']

    def __str__(self):
        return f"{self.asset_tag} - {self.name} ({self.laboratory.facility.code})"
