import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from organizations.models import Organization, Facility, LaboratoryArea


class CustomUserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier for auth.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is mandatory')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class RoleType(models.TextChoices):
    SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'
    FACILITY_MANAGER = 'FACILITY_MANAGER', 'Facility Manager'
    SAMPLE_CLERK = 'SAMPLE_CLERK', 'Sample Clerk'
    INSPECTOR = 'INSPECTOR', 'Inspector'
    LAB_MANAGER = 'LAB_MANAGER', 'Lab Manager'
    LAB_TECHNICIAN = 'LAB_TECHNICIAN', 'Lab Technician'
    QA_REVIEWER = 'QA_REVIEWER', 'QA Reviewer'
    AUTHORIZED_APPROVER = 'AUTHORIZED_APPROVER', 'Authorized Approver'
    REPORT_COORDINATOR = 'REPORT_COORDINATOR', 'Report Coordinator'
    STORAGE_CUSTODIAN = 'STORAGE_CUSTODIAN', 'Storage Custodian'


class Role(models.Model):
    """
    Explicit RBAC role entity defining security authority levels and capabilities.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role_type = models.CharField(max_length=40, choices=RoleType.choices, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Specific permission flags
    can_sign_certificates = models.BooleanField(default=False, help_text="Authorized technical/scientific approver for certificates")
    can_verify_results = models.BooleanField(default=False, help_text="Can perform QA review and statistical verification")
    can_input_results = models.BooleanField(default=False, help_text="Can input metrological testing results")
    can_manage_samples = models.BooleanField(default=False, help_text="Can register, intake, and sub-sample specimens")
    can_manage_storage = models.BooleanField(default=False, help_text="Can manage archive racks and disposal")
    can_manage_facility = models.BooleanField(default=False, help_text="Can manage equipment and lab areas")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Security Role'
        verbose_name_plural = 'Security Roles'

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    Custom User model using UUID primary key and email authentication.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None  # Explicitly disabled
    email = models.EmailField('email address', unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=40, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class OrganizationMembership(models.Model):
    """
    Decoupled relationship linking Users, Organizations/Facilities/Laboratories, and Roles.
    Supports multiple roles per user scoped to specific facilities and testing areas.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='user_memberships')
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='facility_memberships'
    )
    laboratory_area = models.ForeignKey(
        LaboratoryArea,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='area_memberships'
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='assigned_memberships')
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'organization', 'facility', 'role')
        ordering = ['organization', 'user']
        verbose_name = 'Organization Membership'
        verbose_name_plural = 'Organization Memberships'

    def __str__(self):
        facility_str = f" @ {self.facility.code}" if self.facility else ""
        return f"{self.user.email} -> {self.organization.name}{facility_str} [{self.role.name}]"
