from rest_framework import permissions
from .models import RoleType


class BaseRolePermission(permissions.BasePermission):
    """
    Base class checking active memberships and role types.
    """
    allowed_roles = []

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False

        # Active memberships check
        user_roles = request.user.memberships.filter(
            is_active=True,
            organization__is_active=True
        ).values_list('role__role_type', flat=True)

        return any(role in self.allowed_roles for role in user_roles)


class IsSuperAdmin(BaseRolePermission):
    allowed_roles = [RoleType.SUPER_ADMIN]


class IsFacilityManager(BaseRolePermission):
    allowed_roles = [RoleType.FACILITY_MANAGER, RoleType.SUPER_ADMIN]


class IsLabManager(BaseRolePermission):
    allowed_roles = [RoleType.LAB_MANAGER, RoleType.SUPER_ADMIN]


class IsSampleClerk(BaseRolePermission):
    allowed_roles = [RoleType.SAMPLE_CLERK, RoleType.LAB_MANAGER]


class IsInspector(BaseRolePermission):
    allowed_roles = [RoleType.INSPECTOR, RoleType.LAB_MANAGER]


class IsLabTechnician(BaseRolePermission):
    allowed_roles = [RoleType.LAB_TECHNICIAN, RoleType.LAB_MANAGER]


class IsQAReviewer(BaseRolePermission):
    allowed_roles = [RoleType.QA_REVIEWER]


class IsAuthorizedApprover(permissions.BasePermission):
    """
    Strict isolation: Super Admin CANNOT automatically approve scientific certificates
    unless explicitly assigned the AUTHORIZED_APPROVER role.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False

        return request.user.memberships.filter(
            is_active=True,
            role__role_type=RoleType.AUTHORIZED_APPROVER,
            role__can_sign_certificates=True
        ).exists()


class IsReportCoordinator(BaseRolePermission):
    allowed_roles = [RoleType.REPORT_COORDINATOR, RoleType.LAB_MANAGER]


class IsStorageCustodian(BaseRolePermission):
    allowed_roles = [RoleType.STORAGE_CUSTODIAN, RoleType.LAB_MANAGER]


def admin_organization_ids(user):
    """Organization scope of explicitly assigned LIMS Super Admin memberships."""
    if not user or not user.is_authenticated or not user.is_active:
        return set()
    return {
        str(value) for value in user.memberships.filter(
            is_active=True, role__role_type=RoleType.SUPER_ADMIN,
            organization__is_active=True
        ).values_list('organization_id', flat=True)
    }


def scoped_user_queryset(actor):
    """Hide users outside an administrator's organization memberships."""
    from .models import User
    org_ids = admin_organization_ids(actor)
    if not org_ids:
        return User.objects.none()
    return User.objects.filter(memberships__organization_id__in=org_ids).distinct()


class CanManageUsers(permissions.BasePermission):
    """
    Server-side permission: Requires active LIMS Super Admin membership in an active organization,
    or designated Django superuser.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False

        return bool(admin_organization_ids(request.user))


class HasActiveLimsAccess(permissions.BasePermission):
    """
    Ensures the user account is active, authenticated, and has at least one active membership
    (or is a superuser).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False
        return request.user.memberships.filter(
            is_active=True,
            organization__is_active=True,
            facility__is_active=True,
        ).exists()


def validate_membership_scope(user, organization, facility=None, laboratory_area=None):
    """
    Strict hierarchical validation of LIMS multi-tenant entities:
    - User active state.
    - Organization active state.
    - Facility active state & belongs to selected organization.
    - Laboratory area active state & belongs to selected facility.
    """
    from rest_framework.exceptions import ValidationError

    if not user.is_active:
        raise ValidationError("Target user account is inactive.")

    if not organization or not organization.is_active:
        raise ValidationError("Target organization is missing or inactive.")

    if facility:
        if not facility.is_active:
            raise ValidationError("Target facility is inactive.")
        if facility.organization_id != organization.id:
            raise ValidationError(
                f"Facility '{facility.name}' does not belong to organization '{organization.name}'."
            )

    if laboratory_area:
        if not facility:
            raise ValidationError("Laboratory area cannot be specified without a facility.")
        if not laboratory_area.is_active:
            raise ValidationError("Target laboratory area is inactive.")
        if laboratory_area.facility_id != facility.id:
            raise ValidationError(
                f"Laboratory area '{laboratory_area.name}' does not belong to facility '{facility.name}'."
            )


