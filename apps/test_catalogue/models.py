import uuid
from django.db import models


class TestCategory(models.TextChoices):
    AP = 'AP', 'Apparent Porosity (AP)'
    BD = 'BD', 'Bulk Density (BD)'
    CCS = 'CCS', 'Cold Crushing Strength (CCS)'
    PLC = 'PLC', 'Permanent Linear Change (PLC)'
    TC = 'TC', 'Thermal Conductivity (TC)'
    CREEP = 'CREEP', 'Creep in Compression'
    RUL = 'RUL', 'Refractoriness Under Load (RUL)'
    CHEMICAL_ANALYSIS = 'CHEMICAL_ANALYSIS', 'Chemical Analysis (WD-XRF)'
    GRAIN_SIZE = 'GRAIN_SIZE', 'Grain Size Distribution'
    FLOW = 'FLOW', 'Flowability of Monolithics'
    ABRASION = 'ABRASION', 'Abrasion Resistance'
    MOR = 'MOR', 'Modulus of Rupture (Cold / Hot)'
    REVERSIBLE_THERMAL_EXP = 'REVERSIBLE_THERMAL_EXP', 'Reversible Thermal Expansion'


class TestDefinition(models.Model):
    """
    Core R-01 test category definition.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, choices=TestCategory.choices, unique=True)
    name = models.CharField(max_length=150)
    discipline = models.CharField(max_length=40, choices=[('PHYSICAL','Physical'), ('MECHANICAL','Mechanical'), ('THERMAL','Thermal'), ('CHEMICAL','Chemical')])
    default_unit = models.CharField(max_length=30)
    specimen_requirement_desc = models.CharField(max_length=200, help_text="e.g. 50mm dia x 50mm height cylinder, ground planar")
    standard_turnaround_days = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['discipline', 'name']

    def __str__(self):
        return f"{self.name} [{self.code}]"


class TestMethod(models.Model):
    """
    Standardized international method (ISO/ASTM/EN) mapped per product category.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    test_definition = models.ForeignKey(TestDefinition, on_delete=models.CASCADE, related_name='methods')
    standard_code = models.CharField(max_length=50, help_text="e.g. ISO 5017, ISO 10059-1, ISO 3187, ISO 1893, ISO 12677")
    title = models.CharField(max_length=255)
    organization = models.CharField(max_length=20, choices=[('ISO','ISO'), ('ASTM','ASTM'), ('EN','EN'), ('DIN','DIN')])
    applicable_product_category = models.CharField(
        max_length=50,
        help_text="e.g. Dense Shaped, Insulating Firebrick, Monolithics (not universally applicable)"
    )
    is_accredited = models.BooleanField(default=True, help_text="Under ISO/IEC 17025 accredited scope")

    class Meta:
        unique_together = ('test_definition', 'standard_code', 'applicable_product_category')
        ordering = ['standard_code']

    def __str__(self):
        return f"{self.standard_code} - {self.test_definition.code} ({self.applicable_product_category})"


class SpecificationSet(models.Model):
    """
    Specification governance package (e.g. DC-SPEC R-01 Rev 4.2).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, help_text="e.g. DC-SPEC R-01")
    title = models.CharField(max_length=200)
    revision = models.CharField(max_length=20, default='Rev 4.2')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.revision})"


class SpecificationLimit(models.Model):
    """
    Acceptance limits for specific test definitions and material grades.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    specification_set = models.ForeignKey(SpecificationSet, on_delete=models.CASCADE, related_name='limits')
    test_definition = models.ForeignKey(TestDefinition, on_delete=models.PROTECT)
    material_grade = models.CharField(max_length=150, help_text="e.g. Mullite-Bonded Corundum")
    min_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    max_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    unit = models.CharField(max_length=30)
    is_critical = models.BooleanField(default=True, help_text="Failing this metric causes automatic batch rejection")

    class Meta:
        unique_together = ('specification_set', 'test_definition', 'material_grade')

    def __str__(self):
        return f"{self.specification_set.code}: {self.test_definition.code} for {self.material_grade}"


class TestPlanTemplate(models.Model):
    """
    Reusable set of required tests per project campaign or refractory component.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, help_text="e.g. Blast Furnace Hearth & Tuyere Lining Suite")
    description = models.TextField(blank=True)
    methods = models.ManyToManyField(TestMethod, related_name='templates')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
