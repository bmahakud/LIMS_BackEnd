import uuid
from django.db import models
from organizations.models import Organization


class Client(models.Model):
    """
    Steelmaker, EPC contractor, or plant owner entity.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='client_profile')
    industry_segment = models.CharField(max_length=100, default='Integrated Blast Furnace Steelmaking')
    contact_person = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Client: {self.organization.name}"


class Vendor(models.Model):
    """
    Refractory manufacturer or material supplier.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='vendor_profile')
    vendor_code = models.CharField(max_length=50, unique=True, help_text="e.g. VEND-RHIMAG-01")
    iso_certified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Vendor: {self.organization.name} [{self.vendor_code}]"


class Project(models.Model):
    """
    Relining campaign or construction milestone (e.g. Tata Steel IJmuiden BF-6 Campaign 2026).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="e.g. BF6-RELINING-2026")
    name = models.CharField(max_length=255)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='projects')
    plant_asset = models.CharField(max_length=150, help_text="Blast Furnace 6 / Stove 61")
    start_date = models.DateField()
    target_completion = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.code} - {self.name}"


class MaterialType(models.TextChoices):
    SHAPED_DENSE = 'SHAPED_DENSE', 'Dense Shaped Refractory Bricks'
    INSULATING_FIREBRICK = 'INSULATING_FIREBRICK', 'Insulating Firebricks (IFB)'
    UNSHAPED_CASTABLE = 'UNSHAPED_CASTABLE', 'Unshaped Monolithics & Castables'
    CARBON_MICROPOROUS = 'CARBON_MICROPOROUS', 'Carbon & Microporous Blocks'
    SILICA_CHECKERS = 'SILICA_CHECKERS', 'Silica / Andalusite Stove Checkers'


class Material(models.Model):
    """
    Catalogued refractory material grade / formula.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="e.g. Mullite-Bonded Corundum Brick")
    code = models.CharField(max_length=50, unique=True, help_text="e.g. MAT-MBC-01")
    category = models.CharField(max_length=40, choices=MaterialType.choices)
    nominal_al2o3_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    nominal_sio2_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    max_service_temp_c = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class MaterialLot(models.Model):
    """
    Specific manufactured lot or production delivery under a Project.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lot_number = models.CharField(max_length=100, db_index=True, help_text="e.g. Lot #P004934-M2")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='material_lots')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='lots')
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='supplied_lots')
    quantity_units = models.PositiveIntegerField(help_text="Total number of whole refractory units produced")
    manufacturing_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('project', 'lot_number')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.lot_number} ({self.material.name})"
