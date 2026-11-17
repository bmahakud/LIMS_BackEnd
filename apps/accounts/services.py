import re
from typing import Optional, Dict, Any, List, Tuple
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from rest_framework.exceptions import ValidationError as DRFValidationError, PermissionDenied, NotFound

from accounts.models import User, Role, RoleType, OrganizationMembership
from organizations.models import Organization, Facility, LaboratoryArea
from audit.models import AuditEvent, AuditAction
from .permissions import validate_membership_scope


class UserProvisioningService:
    """
    Unified, enterprise-grade provisioning and identity lifecycle service for
    Danieli Corus Refractory Laboratory Information Management System.

    Shared by REST endpoints, management commands, and system workflows.
    Ensures strict validation, password rules, hierarchical scope verification,
    audit event logging, and transaction boundaries.
    """

    @staticmethod
    def normalize_email(email: str) -> str:
        """
        Consistently normalizes email addresses by stripping whitespace and lowercasing.
        """
        if not email or not isinstance(email, str):
            raise DRFValidationError({"email": "Email address is required."})
        normalized = email.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise DRFValidationError({"email": "Invalid email address format."})
        return normalized

    @classmethod
    def create_user(
        cls,
        *,
        actor: Optional[User],
        email: str,
        first_name: str,
        last_name: str,
        password: Optional[str] = None,
        job_title: str = "",
        phone_number: str = "",
        is_active: bool = True,
        role: Optional[Role] = None,
        role_type: Optional[str] = None,
        role_id: Optional[Any] = None,
        organization: Optional[Organization] = None,
        organization_id: Optional[Any] = None,
        facility: Optional[Facility] = None,
        facility_id: Optional[Any] = None,
        laboratory_area: Optional[LaboratoryArea] = None,
        laboratory_area_id: Optional[Any] = None,
        is_primary: bool = True,
        approval_justification: str = "",
        ip_address: Optional[str] = None,
    ) -> User:
        """
        Provisions a new laboratory user and sets up initial membership.
        """
        norm_email = cls.normalize_email(email)

        # Name validation
        first_name = (first_name or "").strip()
        last_name = (last_name or "").strip()
        if not first_name:
            raise DRFValidationError({"first_name": "First name is mandatory and cannot be blank."})
        if not last_name:
            raise DRFValidationError({"last_name": "Last name is mandatory and cannot be blank."})

        # Reject duplicates
        if User.objects.filter(email=norm_email).exists():
            raise DRFValidationError({"email": "A user with this email address already exists."})

        # Resolve role
        target_role = role
        if not target_role:
            if role_id:
                target_role = Role.objects.filter(id=role_id).first()
                if not target_role:
                    raise DRFValidationError({"role_id": "Specified role does not exist."})
            elif role_type:
                target_role = Role.objects.filter(role_type=role_type).first()
                if not target_role:
                    raise DRFValidationError({"role_type": f"Role type '{role_type}' does not exist."})
            else:
                target_role = Role.objects.filter(role_type=RoleType.LAB_TECHNICIAN).first()

        # Resolve Organization
        target_org = organization
        if not target_org:
            if organization_id:
                target_org = Organization.objects.filter(id=organization_id).first()
                if not target_org:
                    raise DRFValidationError({"organization_id": "Specified organization does not exist."})
            else:
                target_org = Organization.objects.filter(org_type='DANIELI_CORUS').first() or Organization.objects.first()

        if actor is not None and target_org is not None:
            from .permissions import admin_organization_ids
            if str(target_org.id) not in admin_organization_ids(actor):
                raise PermissionDenied('Provisioning outside the admin organization is forbidden.')

        # Resolve Facility
        target_facility = facility
        if not target_facility:
            if facility_id:
                target_facility = Facility.objects.filter(id=facility_id).first()
                if not target_facility:
                    raise DRFValidationError({"facility_id": "Specified facility does not exist."})
            elif target_org:
                target_facility = target_org.facilities.filter(is_primary=True).first() or target_org.facilities.first()

        # Resolve Laboratory Area
        target_area = laboratory_area
        if not target_area and laboratory_area_id:
            target_area = LaboratoryArea.objects.filter(id=laboratory_area_id).first()
            if not target_area:
                raise DRFValidationError({"laboratory_area_id": "Specified laboratory area does not exist."})

        # Free-text justification is not an independent scientific qualification approval.
        if target_role and target_role.role_type == RoleType.AUTHORIZED_APPROVER:
            raise PermissionDenied('Authorized Approver provisioning requires a separate verified approval workflow.')

        with transaction.atomic():
            # Validate password against Django validators if supplied
            user = User(
                email=norm_email,
                first_name=first_name,
                last_name=last_name,
                job_title=(job_title or "").strip(),
                phone_number=(phone_number or "").strip(),
                is_active=bool(is_active),
                is_staff=False,
                is_superuser=False,
            )

            if password:
                try:
                    validate_password(password, user=user)
                except DjangoValidationError as ve:
                    raise DRFValidationError({"password": list(ve.messages)})
                user.set_password(password)
            else:
                user.set_unusable_password()

            user.save()

            # Hierarchical scope validation
            if target_org:
                validate_membership_scope(user, target_org, target_facility, target_area)

            # Create initial membership
            if target_role and target_org:
                OrganizationMembership.objects.create(
                    user=user,
                    organization=target_org,
                    facility=target_facility,
                    laboratory_area=target_area,
                    role=target_role,
                    is_primary=is_primary,
                    is_active=True,
                )

            # Record audit event
            cls._log_audit(
                actor=actor or user,
                action=AuditAction.CREATE,
                entity_type="User",
                entity_id=str(user.id),
                summary=f"Provisioned personnel {user.email} with role {target_role.name if target_role else 'None'}",
                changes_json={
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": target_role.role_type if target_role else None,
                    "organization": target_org.name if target_org else None,
                    "facility": target_facility.name if target_facility else None,
                    "laboratory_area": target_area.name if target_area else None,
                    "is_active": user.is_active,
                },
                ip_address=ip_address,
        )

        return user

    @classmethod
    def update_user_profile(
        cls,
        *,
        actor: User,
        user: User,
        data: Dict[str, Any],
        ip_address: Optional[str] = None,
    ) -> User:
        """
        Updates permitted personnel profile attributes (first_name, last_name, job_title, phone_number, is_active).
        Enforces self-deactivation protection and last-admin protection.
        """
        disallowed = {'is_superuser', 'is_staff', 'groups', 'user_permissions', 'can_sign_certificates', 'password'}
        attempted = disallowed.intersection(data.keys())
        if attempted:
            raise DRFValidationError(f"Security Violation: Field(s) {list(attempted)} cannot be modified via profile update.")

        with transaction.atomic():
            changes: Dict[str, Any] = {}

            if 'first_name' in data:
                fn = data['first_name'].strip()
                if not fn:
                    raise DRFValidationError({"first_name": "First name cannot be blank."})
                if fn != user.first_name:
                    changes['first_name'] = {'old': user.first_name, 'new': fn}
                    user.first_name = fn

            if 'last_name' in data:
                ln = data['last_name'].strip()
                if not ln:
                    raise DRFValidationError({"last_name": "Last name cannot be blank."})
                if ln != user.last_name:
                    changes['last_name'] = {'old': user.last_name, 'new': ln}
                    user.last_name = ln

            if 'job_title' in data:
                jt = data['job_title'].strip()
                if jt != user.job_title:
                    changes['job_title'] = {'old': user.job_title, 'new': jt}
                    user.job_title = jt

            if 'phone_number' in data:
                pn = data['phone_number'].strip()
                if pn != user.phone_number:
                    changes['phone_number'] = {'old': user.phone_number, 'new': pn}
                    user.phone_number = pn

            if 'is_active' in data:
                new_active = bool(data['is_active'])
                if new_active != user.is_active:
                    if not new_active:
                        # Prevent self-deactivation
                        if actor and actor.id == user.id:
                            raise DRFValidationError({"detail": "Security violation: Administrators cannot deactivate their own active session."})
                        # Prevent sole superadmin deactivation
                        active_admins = User.objects.filter(
                            is_active=True,
                            memberships__role__role_type=RoleType.SUPER_ADMIN
                        ).exclude(id=user.id).count()
                        if active_admins == 0 and user.memberships.filter(role__role_type=RoleType.SUPER_ADMIN).exists():
                            raise DRFValidationError({"detail": "Cannot deactivate the sole remaining active Super Administrator in the system."})
                    changes['is_active'] = {'old': user.is_active, 'new': new_active}
                    user.is_active = new_active

            user.save()

            if changes:
                cls._log_audit(
                    actor=actor,
                    action=AuditAction.UPDATE,
                    entity_type="User",
                    entity_id=str(user.id),
                    summary=f"Updated personnel profile for {user.email}",
                    changes_json=changes,
                    ip_address=ip_address,
                )

        return user

    @classmethod
    def set_user_status(
        cls,
        *,
        actor: User,
        user: User,
        is_active: bool,
        ip_address: Optional[str] = None,
    ) -> User:
        """
        Activates or deactivates a user.
        """
        return cls.update_user_profile(
            actor=actor,
            user=user,
            data={'is_active': is_active},
            ip_address=ip_address,
        )

    @classmethod
    def assign_membership(
        cls,
        *,
        actor: User,
        user: User,
        role: Role,
        organization: Optional[Organization] = None,
        facility: Optional[Facility] = None,
        laboratory_area: Optional[LaboratoryArea] = None,
        is_primary: bool = False,
        approval_justification: str = "",
        ip_address: Optional[str] = None,
    ) -> OrganizationMembership:
        """
        Assigns or updates an organization/facility role membership for a user.
        """
        if actor and actor.id == user.id:
            raise DRFValidationError({"detail": "Security Violation: Users cannot assign or elevate their own roles."})

        # Do not allow a free-text justification to grant signing authority.
        if role.role_type == RoleType.AUTHORIZED_APPROVER:
            raise PermissionDenied('Authorized Approver assignment requires separate qualification approval.')

        org = organization or Organization.objects.filter(org_type='DANIELI_CORUS').first() or Organization.objects.first()
        if actor is not None:
            from .permissions import admin_organization_ids
            if org is None or str(org.id) not in admin_organization_ids(actor):
                raise PermissionDenied('Cannot assign an LIMS role outside an administrator-owned organization.')
        fac = facility or (org.facilities.filter(is_primary=True).first() if org else None) or (org.facilities.first() if org else None)

        validate_membership_scope(user, org, fac, laboratory_area)

        with transaction.atomic():
            if is_primary:
                user.memberships.filter(is_primary=True).update(is_primary=False)

            membership, created = OrganizationMembership.objects.get_or_create(
                user=user,
                organization=org,
                facility=fac,
                role=role,
                defaults={
                    'laboratory_area': laboratory_area,
                    'is_primary': is_primary,
                    'is_active': True,
                }
            )

            if not created:
                membership.is_active = True
                membership.is_primary = is_primary
                if laboratory_area:
                    membership.laboratory_area = laboratory_area
                membership.save()

            cls._log_audit(
                actor=actor,
                action=AuditAction.UPDATE,
                entity_type="User",
                entity_id=str(user.id),
                summary=f"Assigned role {role.name} to {user.email}",
                changes_json={
                    "membership_id": str(membership.id),
                    "role": role.role_type,
                    "organization": org.name if org else None,
                    "facility": fac.name if fac else None,
                    "laboratory_area": laboratory_area.name if laboratory_area else None,
                    "is_primary": is_primary,
                },
                ip_address=ip_address,
            )

        return membership

    @classmethod
    def revoke_membership(
        cls,
        *,
        actor: User,
        user: User,
        membership_id: Any,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Revokes a role membership from a user.
        """
        if actor and actor.id == user.id:
            raise DRFValidationError({"detail": "Security Violation: Users cannot alter or revoke their own roles."})

        membership = OrganizationMembership.objects.filter(id=membership_id, user=user).first()
        if not membership:
            raise NotFound("Membership not found.")

        role_name = membership.role.name
        with transaction.atomic():
            membership.is_active = False
            membership.is_primary = False
            membership.save(update_fields=['is_active', 'is_primary'])

            cls._log_audit(
                actor=actor,
                action=AuditAction.UPDATE,
                entity_type="User",
                entity_id=str(user.id),
                summary=f"Revoked membership role {role_name} from user {user.email}",
                changes_json={"revoked_membership_id": str(membership_id), "role_name": role_name},
                ip_address=ip_address,
            )

    @classmethod
    def reset_password(
        cls,
        *,
        actor: User,
        user: User,
        new_password: str,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Administrative password reset enforcing Django validators.
        """
        if not new_password:
            raise DRFValidationError({"new_password": "New password is required."})

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as ve:
            raise DRFValidationError({"new_password": list(ve.messages)})

        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=['password'])

            cls._log_audit(
                actor=actor,
                action=AuditAction.UPDATE,
                entity_type="User",
                entity_id=str(user.id),
                summary=f"Administrative password reset performed for {user.email}",
                changes_json={"action": "password_reset"},
                ip_address=ip_address,
            )

    @classmethod
    def get_access_history(cls, user_id: Any) -> List[Dict[str, Any]]:
        """
        Retrieves the audit trail events targeting the specified user.
        """
        events = AuditEvent.objects.filter(
            entity_type="User",
            entity_id=str(user_id)
        ).select_related('actor').order_by('-timestamp')[:50]

        return [
            {
                "id": str(e.id),
                "timestamp": e.timestamp.isoformat(),
                "actor_email": e.actor.email if e.actor else "System",
                "action": e.action,
                "summary": e.summary,
                "changes": e.changes_json,
                "ip_address": e.ip_address,
            }
            for e in events
        ]

    @classmethod
    def get_user_permitted_scope(cls, user: User) -> Dict[str, Any]:
        """
        Inspects the current user's permitted roles, facilities, and ISO/IEC 17025 authority flags.
        """
        active_memberships = user.memberships.filter(
            is_active=True,
            organization__is_active=True
        ).select_related('role', 'organization', 'facility', 'laboratory_area')

        roles = []
        facilities = []
        capabilities = {
            "can_sign_certificates": False,
            "can_verify_results": False,
            "can_input_results": False,
            "can_manage_samples": False,
            "can_manage_storage": False,
            "can_manage_facility": False,
            "is_superadmin": user.is_superuser,
        }

        for m in active_memberships:
            r = m.role
            roles.append({
                "id": str(r.id),
                "role_type": r.role_type,
                "name": r.name,
                "is_primary": m.is_primary,
            })
            if r.role_type == RoleType.SUPER_ADMIN:
                capabilities["is_superadmin"] = True
            if r.can_sign_certificates:
                capabilities["can_sign_certificates"] = True
            if r.can_verify_results:
                capabilities["can_verify_results"] = True
            if r.can_input_results:
                capabilities["can_input_results"] = True
            if r.can_manage_samples:
                capabilities["can_manage_samples"] = True
            if r.can_manage_storage:
                capabilities["can_manage_storage"] = True
            if r.can_manage_facility:
                capabilities["can_manage_facility"] = True

            if m.facility and m.facility.is_active:
                facilities.append({
                    "id": str(m.facility.id),
                    "name": m.facility.name,
                    "code": m.facility.code,
                    "is_primary": m.is_primary,
                    "laboratory_area": {
                        "id": str(m.laboratory_area.id),
                        "name": m.laboratory_area.name,
                        "code": m.laboratory_area.code,
                    } if m.laboratory_area and m.laboratory_area.is_active else None
                })

        return {
            "user_id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "is_staff": user.is_staff,
            "roles": roles,
            "facilities": facilities,
            "capabilities": capabilities,
        }

    @classmethod
    def initiate_invitation_or_reset(cls, *, actor: User, user: User) -> Dict[str, Any]:
        """
        Secure invitation / password reset initiation flow.
        Adheres to rule: If email delivery is not configured, do not simulate successful emails.
        Does not log tokens or secrets.
        """
        from django.conf import settings
        email_backend = getattr(settings, 'EMAIL_BACKEND', '')
        # Check if real email delivery is explicitly configured
        email_enabled = getattr(settings, 'EMAIL_DELIVERY_ENABLED', False)
        is_live_email = bool(
            email_enabled and
            getattr(settings, 'EMAIL_HOST', None) and
            email_backend not in [
                'django.core.mail.backends.dummy.EmailBackend',
                'django.core.mail.backends.console.EmailBackend',
                'django.core.mail.backends.locmem.EmailBackend',
            ]
        )

        if not is_live_email:
            cls._log_audit(
                actor=actor,
                action=AuditAction.UPDATE,
                entity_type="User",
                entity_id=str(user.id),
                summary=f"Invitation/password reset requested for {user.email} (Email delivery unconfigured: interactive reset required)",
                changes_json={"action": "invitation_unconfigured_delivery"},
            )
            return {
                "delivered": False,
                "channel": "NONE",
                "message": (
                    "Email delivery is not configured in this environment. "
                    "In accordance with security rules, automated messages will not be simulated. "
                    "Use the administrative password reset endpoint or management command."
                )
            }

        # A configured SMTP host is not proof of a delivered invitation.
        # Do not claim successful delivery until a real send operation exists.
        cls._log_audit(
            actor=actor, action=AuditAction.UPDATE, entity_type="User",
            entity_id=str(user.id),
            summary=f"Invitation requested for {user.email}; sending is not implemented",
            changes_json={"action": "invitation_not_sent"},
        )
        return {
            "delivered": False,
            "channel": "NONE",
            "message": "Invitation not sent. Email delivery is not implemented; use secure password reset.",
        }

    @staticmethod
    def _log_audit(
        *,
        actor: User,
        action: str,
        entity_type: str,
        entity_id: str,
        summary: str,
        changes_json: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        # Never suppress compliance audit failures.
        AuditEvent.objects.create(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            changes_json=changes_json or {},
            ip_address=ip_address,
            )
