from rest_framework import serializers
from .models import User, Role, OrganizationMembership


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = [
            'id', 'role_type', 'name', 'description',
            'can_sign_certificates', 'can_verify_results', 'can_input_results',
            'can_manage_samples', 'can_manage_storage', 'can_manage_facility'
        ]


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    organization_id = serializers.UUIDField(source='organization.id', read_only=True)
    facility_name = serializers.CharField(source='facility.name', read_only=True, allow_null=True)
    facility_code = serializers.CharField(source='facility.code', read_only=True, allow_null=True)
    facility_id = serializers.UUIDField(source='facility.id', read_only=True, allow_null=True)
    laboratory_area_name = serializers.CharField(source='laboratory_area.name', read_only=True, allow_null=True)
    laboratory_area_code = serializers.CharField(source='laboratory_area.code', read_only=True, allow_null=True)

    class Meta:
        model = OrganizationMembership
        fields = [
            'id', 'organization_id', 'organization_name',
            'facility_id', 'facility_name', 'facility_code',
            'laboratory_area_name', 'laboratory_area_code',
            'role', 'is_primary', 'is_active'
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name',
            'phone_number', 'job_title', 'is_active', 'date_joined',
            'memberships'
        ]

    def get_memberships(self, obj):
        active_memberships = obj.memberships.filter(is_active=True, organization__is_active=True)
        return OrganizationMembershipSerializer(active_memberships, many=True).data


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserManageListSerializer(serializers.ModelSerializer):
    """
    Serializer for administrative user directory with primary role and facility.
    """
    primary_role = serializers.SerializerMethodField()
    primary_facility = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name',
            'phone_number', 'job_title', 'is_active',
            'is_staff', 'is_superuser', 'date_joined', 'last_login',
            'primary_role', 'primary_facility', 'memberships'
        ]

    def get_primary_role(self, obj):
        membership = obj.memberships.filter(is_active=True, is_primary=True).first() or obj.memberships.filter(is_active=True).first()
        if membership and membership.role:
            return RoleSerializer(membership.role).data
        return None

    def get_primary_facility(self, obj):
        membership = obj.memberships.filter(is_active=True, is_primary=True).first() or obj.memberships.filter(is_active=True).first()
        if membership and membership.facility:
            return {
                'id': str(membership.facility.id),
                'name': membership.facility.name,
                'code': membership.facility.code,
            }
        return None

    def get_memberships(self, obj):
        memberships = obj.memberships.all().select_related('role', 'organization', 'facility', 'laboratory_area')
        return OrganizationMembershipSerializer(memberships, many=True).data


class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    job_title = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    phone_number = serializers.CharField(max_length=40, required=False, allow_blank=True, default='')
    role_id = serializers.UUIDField(required=False, allow_null=True)
    role_type = serializers.CharField(required=False, allow_blank=True, default='')
    organization_id = serializers.UUIDField(required=False, allow_null=True)
    facility_id = serializers.UUIDField(required=False, allow_null=True)
    is_active = serializers.BooleanField(default=True)

    def validate(self, attrs):
        # Reject attempts to inject technical Django privileges
        disallowed = {'is_superuser', 'is_staff', 'groups', 'user_permissions', 'can_sign_certificates'}
        attempted = disallowed.intersection(self.initial_data.keys())
        if attempted:
            raise serializers.ValidationError(
                f"Security Violation: Technical privileges {list(attempted)} cannot be assigned via public API payloads."
            )
        return attrs

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return normalized


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'job_title', 'phone_number', 'is_active']

    def validate(self, attrs):
        disallowed = {'is_superuser', 'is_staff', 'groups', 'user_permissions', 'can_sign_certificates'}
        attempted = disallowed.intersection(self.initial_data.keys())
        if attempted:
            raise serializers.ValidationError(
                f"Security Violation: Technical privileges {list(attempted)} cannot be modified via user update endpoint."
            )
        return attrs


class AdminPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(min_length=8, write_only=True)


class MembershipAssignSerializer(serializers.Serializer):
    role_id = serializers.UUIDField()
    organization_id = serializers.UUIDField(required=False, allow_null=True)
    facility_id = serializers.UUIDField(required=False, allow_null=True)
    laboratory_area_id = serializers.UUIDField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(default=False)
    approval_justification = serializers.CharField(required=False, allow_blank=True, default='')


class MembershipUpdateSerializer(serializers.Serializer):
    role_id = serializers.UUIDField(required=False)
    facility_id = serializers.UUIDField(required=False, allow_null=True)
    laboratory_area_id = serializers.UUIDField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
    approval_justification = serializers.CharField(required=False, allow_blank=True, default='')


class OrganizationDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    org_type = serializers.CharField()
    country = serializers.CharField()
    address = serializers.CharField()
    accreditation_number = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    facilities_count = serializers.IntegerField(default=0)


class FacilityDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    organization_id = serializers.UUIDField(source='organization.id')
    organization_name = serializers.CharField(source='organization.name')
    name = serializers.CharField()
    code = serializers.CharField()
    city = serializers.CharField()
    is_primary = serializers.BooleanField()
    is_active = serializers.BooleanField()



