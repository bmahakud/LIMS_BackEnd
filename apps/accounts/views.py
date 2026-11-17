from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from django.utils.decorators import method_decorator
from django.middleware.csrf import get_token, rotate_token
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

from django.db import transaction
from django.db.models import Q
from organizations.models import Organization, Facility, LaboratoryArea
from audit.models import AuditEvent, AuditAction
from .models import User, Role, RoleType, OrganizationMembership
from .permissions import CanManageUsers, validate_membership_scope, scoped_user_queryset, admin_organization_ids
from .services import UserProvisioningService
from .serializers import (
    LoginRequestSerializer,
    UserProfileSerializer,
    RoleSerializer,
    OrganizationMembershipSerializer,
    UserManageListSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    AdminPasswordResetSerializer,
    MembershipAssignSerializer,
    MembershipUpdateSerializer,
    OrganizationDetailSerializer,
    FacilityDetailSerializer,
)


class AuthRateThrottle(AnonRateThrottle):
    rate = '15/min'


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CSRFTokenView(APIView):
    """
    Returns CSRF cookie and token for the Single Page Application.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Retrieve CSRF Token",
        description="Sets the csrftoken cookie on the client and returns the token in the JSON body.",
        responses={200: inline_serializer(name="CSRFResponse", fields={"csrfToken": serializers.CharField()})}
    )
    def get(self, request, *args, **kwargs):
        token = get_token(request)
        return Response({"csrfToken": token})


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    """
    Server-side session authentication with rate limiting and generic error messages.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="User Session Login",
        description="Authenticates credentials and establishes a secure HttpOnly session.",
        request=LoginRequestSerializer,
        responses={
            200: UserProfileSerializer,
            400: inline_serializer(name="LoginError", fields={"detail": serializers.CharField()}),
            401: inline_serializer(name="AuthFailed", fields={"detail": serializers.CharField()}),
            403: inline_serializer(name="InactiveUser", fields={"detail": serializers.CharField()}),
            429: inline_serializer(name="RateLimited", fields={"detail": serializers.CharField()})
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = LoginRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Invalid credentials format."},
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data['email'].strip().lower()
        password = serializer.validated_data['password']

        # Check user existence and active status explicitly
        user_candidate = User.objects.filter(email=email).first()
        if user_candidate and not user_candidate.is_active:
            if user_candidate.check_password(password):
                return Response(
                    {"detail": "Account is inactive. Contact the laboratory administrator."},
                    status=status.HTTP_403_FORBIDDEN
                )

        user = authenticate(request, email=email, password=password)

        if user is None:
            # Generic message prevents user enumeration
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {"detail": "Account is inactive. Contact the laboratory administrator."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Login and establish session
        login(request, user)
        # Return new CSRF token to client because session login rotates the token
        new_csrf = get_token(request)
        profile_data = UserProfileSerializer(user).data
        profile_data['csrfToken'] = new_csrf
        return Response(profile_data, status=status.HTTP_200_OK)


@method_decorator(csrf_protect, name='dispatch')
class LogoutView(APIView):
    """
    Terminates the user's active session.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="User Logout",
        description="Clears the server-side session and cookies.",
        responses={200: inline_serializer(name="LogoutResponse", fields={"detail": serializers.CharField()})}
    )
    def post(self, request, *args, **kwargs):
        logout(request)
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


class CurrentUserView(APIView):
    """
    Returns the authenticated user's profile and active laboratory memberships.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Current Authenticated User Profile",
        description="Returns user details and scoped laboratory roles.",
        responses={200: UserProfileSerializer}
    )
    def get(self, request, *args, **kwargs):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserManagementListView(APIView):
    """
    Administrative directory listing and provisioning of laboratory personnel.
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="List Laboratory Personnel",
        description="Returns list of users filtered by role, search keyword, or active status.",
        responses={200: UserManageListSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        qs = scoped_user_queryset(request.user).prefetch_related(
            'memberships__role',
            'memberships__organization',
            'memberships__facility',
            'memberships__laboratory_area'
        )

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(job_title__icontains=search)
            )

        role_filter = request.query_params.get('role', '').strip()
        if role_filter:
            qs = qs.filter(memberships__role__role_type=role_filter, memberships__is_active=True)

        status_filter = request.query_params.get('is_active', '').strip().lower()
        if status_filter in ['true', '1']:
            qs = qs.filter(is_active=True)
        elif status_filter in ['false', '0']:
            qs = qs.filter(is_active=False)

        users = qs.distinct().order_by('last_name', 'first_name')
        serializer = UserManageListSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Register New Laboratory Personnel",
        description="Provisions a user and establishes their initial RBAC membership.",
        request=UserCreateSerializer,
        responses={201: UserManageListSerializer}
    )
    def post(self, request, *args, **kwargs):
        serializer = UserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            user = UserProvisioningService.create_user(
                actor=request.user,
                email=data['email'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                password=data['password'],
                job_title=data.get('job_title', ''),
                phone_number=data.get('phone_number', ''),
                is_active=data.get('is_active', True),
                role_id=data.get('role_id'),
                role_type=data.get('role_type'),
                organization_id=data.get('organization_id'),
                facility_id=data.get('facility_id'),
                approval_justification=data.get('approval_justification', ''),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except serializers.ValidationError as e:
            return Response(e.detail if hasattr(e, 'detail') else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            from rest_framework.exceptions import APIException
            if hasattr(e, 'status_code'):
                return Response({"detail": str(e.detail if hasattr(e, 'detail') else e)}, status=e.status_code)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserManageListSerializer(user).data, status=status.HTTP_201_CREATED)


class UserManagementDetailView(APIView):
    """
    Retrieve and update individual user profile and status.
    """
    permission_classes = [CanManageUsers]

    def get_object(self, user_id):
        return scoped_user_queryset(self.request.user).filter(id=user_id).prefetch_related(
            'memberships__role',
            'memberships__organization',
            'memberships__facility'
        ).first()

    @extend_schema(
        summary="Retrieve User Details",
        description="Returns full profile and active/inactive memberships for a user.",
        responses={200: UserManageListSerializer}
    )
    def get(self, request, user_id, *args, **kwargs):
        user = self.get_object(user_id)
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserManageListSerializer(user).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update User Profile & Status",
        description="Updates personnel contact information, job title, and active status.",
        request=UserUpdateSerializer,
        responses={200: UserManageListSerializer}
    )
    def patch(self, request, user_id, *args, **kwargs):
        user = self.get_object(user_id)
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated_user = UserProvisioningService.update_user_profile(
                actor=request.user,
                user=user,
                data=serializer.validated_data,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except serializers.ValidationError as e:
            return Response(e.detail if hasattr(e, 'detail') else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            from rest_framework.exceptions import APIException
            if hasattr(e, 'status_code'):
                return Response({"detail": str(e.detail if hasattr(e, 'detail') else e)}, status=e.status_code)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserManageListSerializer(updated_user).data, status=status.HTTP_200_OK)


class UserPasswordResetView(APIView):
    """
    Administrative reset of a user's password.
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="Admin Password Reset",
        description="Resets the password of the specified user with min 8 characters.",
        request=AdminPasswordResetSerializer,
        responses={200: inline_serializer(name="PasswordResetOk", fields={"detail": serializers.CharField()})}
    )
    def post(self, request, user_id, *args, **kwargs):
        user = scoped_user_queryset(request.user).filter(id=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_password = serializer.validated_data['new_password']
        try:
            UserProvisioningService.reset_password(
                actor=request.user,
                user=user,
                new_password=new_password,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except serializers.ValidationError as e:
            return Response(e.detail if hasattr(e, 'detail') else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            if hasattr(e, 'status_code'):
                return Response({"detail": str(e.detail if hasattr(e, 'detail') else e)}, status=e.status_code)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": f"Password for {user.email} was successfully updated."}, status=status.HTTP_200_OK)


class UserMembershipManagementView(APIView):
    """
    Assign, update, or revoke security roles and facility memberships for a user.
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="List User Memberships",
        description="Returns all active and inactive role memberships for the specified user.",
        responses={200: OrganizationMembershipSerializer(many=True)}
    )
    def get(self, request, user_id, *args, **kwargs):
        user = scoped_user_queryset(request.user).filter(id=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        memberships = user.memberships.all().select_related('role', 'organization', 'facility', 'laboratory_area')
        return Response(OrganizationMembershipSerializer(memberships, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Assign Role & Facility Membership",
        description="Attaches a new RBAC role and facility scope to the specified user.",
        request=MembershipAssignSerializer,
        responses={201: OrganizationMembershipSerializer}
    )
    def post(self, request, user_id, *args, **kwargs):
        user = scoped_user_queryset(request.user).filter(id=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = MembershipAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        role = Role.objects.filter(id=serializer.validated_data['role_id']).first()
        if not role:
            return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

        org_id = serializer.validated_data.get('organization_id')
        org = Organization.objects.filter(id=org_id).first() if org_id else None

        fac_id = serializer.validated_data.get('facility_id')
        facility = Facility.objects.filter(id=fac_id).first() if fac_id else None

        area_id = serializer.validated_data.get('laboratory_area_id')
        lab_area = LaboratoryArea.objects.filter(id=area_id).first() if area_id else None

        is_primary = serializer.validated_data.get('is_primary', False)
        justification = serializer.validated_data.get('approval_justification', '')

        try:
            membership = UserProvisioningService.assign_membership(
                actor=request.user,
                user=user,
                role=role,
                organization=org,
                facility=facility,
                laboratory_area=lab_area,
                is_primary=is_primary,
                approval_justification=justification,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except serializers.ValidationError as e:
            detail = e.detail
            if isinstance(detail, list) and len(detail) == 1:
                return Response({"detail": str(detail[0])}, status=status.HTTP_400_BAD_REQUEST)
            if isinstance(detail, dict) and "approval_justification" in detail:
                msg = detail["approval_justification"]
                msg_str = msg[0] if isinstance(msg, list) else msg
                return Response({"detail": str(msg_str)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(detail if isinstance(detail, (dict, list)) else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            if hasattr(e, 'status_code'):
                detail = getattr(e, 'detail', str(e))
                if isinstance(detail, list) and len(detail) == 1:
                    return Response({"detail": str(detail[0])}, status=e.status_code)
                return Response({"detail": str(detail)}, status=e.status_code)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(OrganizationMembershipSerializer(membership).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Toggle or Revoke Membership",
        description="Deactivates or deletes a specific role membership.",
        responses={200: inline_serializer(name="RevokeOk", fields={"detail": serializers.CharField()})}
    )
    def delete(self, request, user_id, membership_id, *args, **kwargs):
        user = scoped_user_queryset(request.user).filter(id=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            UserProvisioningService.revoke_membership(
                actor=request.user,
                user=user,
                membership_id=membership_id,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except serializers.ValidationError as e:
            return Response(e.detail if hasattr(e, 'detail') else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            if hasattr(e, 'status_code'):
                return Response({"detail": str(e.detail if hasattr(e, 'detail') else e)}, status=e.status_code)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Role membership was revoked."}, status=status.HTTP_200_OK)


class RoleDirectoryView(APIView):
    """
    Returns available security roles, descriptions, and functional permission flags.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Directory of Available Security Roles",
        description="Returns list of all active roles with ISO/IEC 17025 authority flags.",
        responses={200: RoleSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        roles = Role.objects.all().order_by('name')
        return Response(RoleSerializer(roles, many=True).data, status=status.HTTP_200_OK)


class FacilityDirectoryView(APIView):
    """
    Returns active organizations and testing facilities for assignment.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Directory of Testing Facilities & Organizations",
        description="Returns organizations and facilities available for personnel assignment.",
        responses={200: inline_serializer(name="FacilitiesDirectory", fields={"organizations": serializers.ListField()})}
    )
    def get(self, request, *args, **kwargs):
        orgs = Organization.objects.filter(is_active=True, id__in=request.user.memberships.filter(is_active=True, organization__is_active=True).values_list('organization_id', flat=True)).prefetch_related('facilities__lab_areas')
        data = []
        for org in orgs:
            facilities_data = []
            for fac in org.facilities.filter(is_active=True):
                areas_data = [
                    {'id': str(a.id), 'code': a.code, 'name': a.name}
                    for a in fac.lab_areas.filter(is_active=True)
                ]
                facilities_data.append({
                    'id': str(fac.id),
                    'code': fac.code,
                    'name': fac.name,
                    'city': fac.city,
                    'is_primary': fac.is_primary,
                    'areas': areas_data
                })
            data.append({
                'id': str(org.id),
                'name': org.name,
                'org_type': org.org_type,
                'country': org.country,
                'facilities': facilities_data
            })
        return Response({'organizations': data}, status=status.HTTP_200_OK)


class UserAccessHistoryView(APIView):
    """
    Returns audit trail events targeting the specified user.
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="User Access & Modification History",
        description="Retrieves ISO/IEC 17025 compliant audit events recorded against this user.",
        responses={200: inline_serializer(name="AccessHistoryList", fields={"events": serializers.ListField()})}
    )
    def get(self, request, user_id, *args, **kwargs):
        user = scoped_user_queryset(request.user).filter(id=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        history = UserProvisioningService.get_access_history(user.id)
        return Response({"events": history}, status=status.HTTP_200_OK)


class UserInvitationView(APIView):
    """
    Initiates an account invitation or password reset notification.
    Enforces security rule: Does not simulate delivery when email backend is unconfigured.
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="Initiate Invitation / Password Reset",
        description="Dispatches a secure invitation or flags interactive setup if email delivery is inactive.",
        responses={200: inline_serializer(name="InvitationResponse", fields={
            "delivered": serializers.BooleanField(),
            "channel": serializers.CharField(),
            "message": serializers.CharField(),
        })}
    )
    def post(self, request, user_id, *args, **kwargs):
        user = scoped_user_queryset(request.user).filter(id=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        result = UserProvisioningService.initiate_invitation_or_reset(actor=request.user, user=user)
        return Response(result, status=status.HTTP_200_OK)


class UserActivationView(APIView):
    """
    Explicit activation of a user account.
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="Activate User Account",
        description="Re-activates a previously deactivated personnel record.",
        responses={200: UserManageListSerializer}
    )
    def post(self, request, user_id, *args, **kwargs):
        user = scoped_user_queryset(request.user).filter(id=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            updated = UserProvisioningService.set_user_status(
                actor=request.user,
                user=user,
                is_active=True,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserManageListSerializer(updated).data, status=status.HTTP_200_OK)


class UserDeactivationView(APIView):
    """
    Explicit deactivation of a user account with self-deactivation & sole-admin protection.
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="Deactivate User Account",
        description="Deactivates a personnel account, terminating access to laboratory operations.",
        responses={200: UserManageListSerializer}
    )
    def post(self, request, user_id, *args, **kwargs):
        user = scoped_user_queryset(request.user).filter(id=user_id).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            updated = UserProvisioningService.set_user_status(
                actor=request.user,
                user=user,
                is_active=False,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except serializers.ValidationError as e:
            detail = e.detail
            if isinstance(detail, dict) and "detail" in detail:
                return Response(detail, status=status.HTTP_400_BAD_REQUEST)
            return Response(detail if isinstance(detail, (dict, list)) else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserManageListSerializer(updated).data, status=status.HTTP_200_OK)


class DirectMembershipDetailView(APIView):
    """
    Direct PATCH and DELETE by membership ID:
    PATCH  /api/v1/admin/memberships/{id}/
    DELETE /api/v1/admin/memberships/{id}/
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="Update Membership Attributes",
        description="Updates primary status, active status, or changes assigned role/area.",
        request=MembershipUpdateSerializer,
        responses={200: OrganizationMembershipSerializer}
    )
    def patch(self, request, membership_id, *args, **kwargs):
        membership = OrganizationMembership.objects.filter(id=membership_id, organization_id__in=admin_organization_ids(request.user)).select_related('user', 'role', 'organization', 'facility').first()
        if not membership:
            return Response({"detail": "Membership not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.id == membership.user_id:
            return Response(
                {"detail": "Security Violation: Users cannot alter or elevate their own roles."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = MembershipUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        target_role = membership.role
        if 'role_id' in data:
            new_role = Role.objects.filter(id=data['role_id']).first()
            if not new_role:
                return Response({"detail": "Specified role not found."}, status=status.HTTP_404_NOT_FOUND)
            if new_role.id != membership.role_id:
                return Response({'detail': 'Use a controlled revoke-and-assign workflow to change roles.'}, status=status.HTTP_400_BAD_REQUEST)
            target_role = new_role

        fac = membership.facility
        if 'facility_id' in data:
            fac = Facility.objects.filter(id=data['facility_id']).first() if data['facility_id'] else None

        lab_area = membership.laboratory_area
        if 'laboratory_area_id' in data:
            lab_area = LaboratoryArea.objects.filter(id=data['laboratory_area_id']).first() if data['laboratory_area_id'] else None

        is_primary = data.get('is_primary', membership.is_primary)
        justification = data.get('approval_justification', '')

        try:
            updated_mem = UserProvisioningService.assign_membership(
                actor=request.user,
                user=membership.user,
                role=target_role,
                organization=membership.organization,
                facility=fac,
                laboratory_area=lab_area,
                is_primary=is_primary,
                approval_justification=justification,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            if 'is_active' in data:
                updated_mem.is_active = bool(data['is_active'])
                updated_mem.save(update_fields=['is_active'])
        except serializers.ValidationError as e:
            detail = e.detail
            if isinstance(detail, list) and len(detail) == 1:
                return Response({"detail": str(detail[0])}, status=status.HTTP_400_BAD_REQUEST)
            if isinstance(detail, dict) and "approval_justification" in detail:
                msg = detail["approval_justification"]
                msg_str = msg[0] if isinstance(msg, list) else msg
                return Response({"detail": str(msg_str)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(detail if isinstance(detail, (dict, list)) else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            if hasattr(e, 'status_code'):
                return Response({"detail": str(getattr(e, 'detail', e))}, status=e.status_code)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(OrganizationMembershipSerializer(updated_mem).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Delete Membership Directly",
        description="Permanently deletes the specified membership record.",
        responses={200: inline_serializer(name="DeleteMemOk", fields={"detail": serializers.CharField()})}
    )
    def delete(self, request, membership_id, *args, **kwargs):
        membership = OrganizationMembership.objects.filter(id=membership_id, organization_id__in=admin_organization_ids(request.user)).first()
        if not membership:
            return Response({"detail": "Membership not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.id == membership.user_id:
            return Response(
                {"detail": "Security Violation: Users cannot alter or revoke their own roles."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            UserProvisioningService.revoke_membership(
                actor=request.user,
                user=membership.user,
                membership_id=membership.id,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Role membership was revoked."}, status=status.HTTP_200_OK)


class OrganizationDirectoryAdminView(APIView):
    """
    GET /api/v1/admin/organizations/
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="Administrative Organization Directory",
        description="Returns list of all active enterprise organizations with facility counts.",
        responses={200: OrganizationDetailSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        orgs = Organization.objects.filter(id__in=admin_organization_ids(request.user)).order_by('name')
        data = [
            {
                'id': org.id,
                'name': org.name,
                'org_type': org.org_type,
                'country': org.country,
                'address': org.address,
                'accreditation_number': org.accreditation_number,
                'is_active': org.is_active,
                'facilities_count': org.facilities.count(),
            }
            for org in orgs
        ]
        return Response(data, status=status.HTTP_200_OK)


class FacilityDirectoryAdminView(APIView):
    """
    GET /api/v1/admin/facilities/
    """
    permission_classes = [CanManageUsers]

    @extend_schema(
        summary="Administrative Facility Directory",
        description="Returns all registered testing facilities with organization metadata.",
        responses={200: FacilityDetailSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        facs = Facility.objects.select_related('organization').filter(organization_id__in=admin_organization_ids(request.user)).order_by('name')
        return Response(FacilityDetailSerializer(facs, many=True).data, status=status.HTTP_200_OK)


class CurrentUserPermittedScopeView(APIView):
    """
    Returns the calling user's permitted roles, facilities, and ISO/IEC 17025 capabilities.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Current User Permitted Scope & Capabilities",
        description="Returns caller's active roles, testing facilities, and verified authority flags.",
        responses={200: inline_serializer(name="PermittedScopeResponse", fields={
            "user_id": serializers.CharField(),
            "email": serializers.CharField(),
            "roles": serializers.ListField(),
            "facilities": serializers.ListField(),
            "capabilities": serializers.DictField(),
        })}
    )
    def get(self, request, *args, **kwargs):
        scope = UserProvisioningService.get_user_permitted_scope(request.user)
        return Response(scope, status=status.HTTP_200_OK)


