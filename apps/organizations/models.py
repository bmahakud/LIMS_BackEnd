import uuid
from django.db import models


class OrganizationType(models.TextChoices):
    DANIELI_CORUS = 'DANIELI_CORUS', 'Danieli Corus BU'
    STEELMAKER_CLIENT = 'STEELMAKER_CLIENT', 'Steelmaker / EPC Client'
    REFRACTORY_MANUFACTURER = 'REFRACTORY_MANUFACTURER', 'Refractory Manufacturer'
    THIRD_PARTY_INSPECTOR = 'THIRD_PARTY_INSPECTOR', 'Third-Party Inspection Agency'


class Organization(models.Model):
    """
    Multi-tenant enterprise entity (e.g. Danieli Corus IJmuiden, Tata Steel, RHI Magnesita).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    org_type = models.CharField(max_length=40, choices=OrganizationType.choices)
    country = models.CharField(max_length=2, help_text='ISO 3166-1 alpha-2 code')
    address = models.TextField(blank=True)
    accreditation_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='ISO/IEC 17025 Accreditation identifier if applicable'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'

    def __str__(self):
        return f"{self.name} ({self.get_org_type_display()})"


class Facility(models.Model):
    """
    Physical plant, works, or regional testing facility belonging to an Organization.
    (e.g., IJmuiden Refractory Testing Centre, Radenthein Works, Taranto Steel Plant).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='facilities')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    city = models.CharField(max_length=100)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['organization', 'name']
        verbose_name = 'Facility / Works'
        verbose_name_plural = 'Facilities & Works'

    def __str__(self):
        return f"{self.organization.name} - {self.name} [{self.code}]"


class LaboratoryArea(models.Model):
    """
    Specific testing bay, furnace hall, or metrology room within a facility.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='lab_areas')
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_temperature_controlled = models.BooleanField(default=True)
    is_humidity_controlled = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('facility', 'code')
        ordering = ['facility', 'code']
        verbose_name = 'Laboratory Testing Area'
        verbose_name_plural = 'Laboratory Testing Areas'

    def __str__(self):
        return f"{self.facility.name} - {self.name} ({self.code})"
