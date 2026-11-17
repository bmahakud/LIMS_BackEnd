"""Facility-scoped, action-aware authorization for scientific LIMS resources.

Every operational view must explicitly declare its write roles and foreign-key
facility path. The API never grants scientific permissions based on is_superuser.
"""
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied


def authorized_facility_ids(user):
    if not user or not user.is_authenticated or not user.is_active:
        return set()
    from accounts.models import OrganizationMembership
    # Explicit join consistency is checked below; existing historical memberships
    # may contain mismatched organization/facility references.
    memberships = OrganizationMembership.objects.filter(
        user=user, is_active=True, organization__is_active=True,
        facility__is_active=True,
    ).values_list("facility_id", "organization_id", "facility__organization_id")
    return {str(fac_id) for fac_id, org_id, facility_org in memberships if org_id == facility_org}


def role_in_facility(user, role_types, facility_id):
    if not facility_id or not user or not user.is_authenticated or not user.is_active:
        return False
    from accounts.models import OrganizationMembership
    return OrganizationMembership.objects.filter(
        user=user, is_active=True, role__role_type__in=role_types,
        organization__is_active=True, facility__is_active=True,
        facility_id=facility_id,
        facility__organization_id__in=OrganizationMembership.objects.filter(
            user=user, is_active=True, facility_id=facility_id,
            organization__is_active=True
        ).values_list("organization_id", flat=True),
    ).exists()


def resolve_path(value, dotted_path):
    for part in dotted_path.split("."):
        if value is None:
            return None
        value = getattr(value, part, None)
    return value


class OperationalAccessPermission(permissions.BasePermission):
    """Facility membership for reads; role and facility membership for writes."""

    def has_permission(self, request, view):
        facilities = authorized_facility_ids(request.user)
        if not facilities:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        roles = view.write_roles.get(getattr(view, "action", None), ())
        return bool(roles) and any(
            role_in_facility(request.user, roles, fid) for fid in facilities
        )

    def has_object_permission(self, request, view, obj):
        facility_id = resolve_path(obj, view.facility_attr)
        if str(facility_id) not in authorized_facility_ids(request.user):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        roles = view.write_roles.get(getattr(view, "action", None), ())
        return bool(roles) and role_in_facility(request.user, roles, facility_id)


class ScopedOperationalMixin:
    """Fail-closed queryset and mutation guards. Add before ModelViewSet."""

    permission_classes = [permissions.IsAuthenticated, OperationalAccessPermission]
    facility_lookup = None
    facility_attr = None
    write_roles = {}
    cross_facility_attrs = ()
    final_sample_attr = None

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.facility_lookup:
            raise AssertionError("Scoped viewsets must declare facility_lookup")
        facilities = authorized_facility_ids(self.request.user)
        if not facilities:
            return queryset.none()
        return queryset.filter(**{self.facility_lookup + "__in": facilities}).distinct()

    def _candidate_path(self, serializer, dotted_path):
        parts = dotted_path.split(".")
        value = serializer.validated_data.get(
            parts[0],
            getattr(serializer.instance, parts[0], None) if serializer.instance else None,
        )
        return resolve_path(value, ".".join(parts[1:])) if len(parts) > 1 else value

    def ensure_write_scope(self, serializer):
        roles = self.write_roles.get(getattr(self, "action", None), ())
        if not roles:
            raise PermissionDenied("This scientific record operation is not permitted.")
        facility_id = self._candidate_path(serializer, self.facility_attr)
        if not role_in_facility(self.request.user, roles, facility_id):
            raise PermissionDenied("This role cannot modify records in the selected facility.")
        for path in self.cross_facility_attrs:
            other_facility = self._candidate_path(serializer, path)
            if other_facility is not None and str(other_facility) != str(facility_id):
                raise PermissionDenied("Linked laboratory resources must belong to the same facility.")
        if self.final_sample_attr:
            sample = self._candidate_path(serializer, self.final_sample_attr)
            if sample is not None:
                from samples.models import SampleStatus
                if sample.status in (SampleStatus.REPORT_ISSUED, SampleStatus.STORED):
                    raise PermissionDenied("Issued or archived scientific records require a controlled revision.")

    def perform_create(self, serializer):
        self.ensure_write_scope(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self.ensure_write_scope(serializer)
        serializer.save()

    def perform_destroy(self, instance):
        raise PermissionDenied("Scientific records must be retained; use a controlled revision workflow.")
