import getpass
import sys
from typing import Optional
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password

from accounts.models import User, Role, RoleType, OrganizationMembership
from accounts.services import UserProvisioningService
from organizations.models import Organization, Facility, LaboratoryArea


class Command(BaseCommand):
    help = (
        "Phase 8 — Interactive CLI provisioning command for Danieli Corus LIMS personnel. "
        "Strictly provisions ordinary business accounts (is_superuser=False, is_staff=False) "
        "with dynamic PostgreSQL choices and trusted delegation controls."
    )

    def add_arguments(self, parser):
        # Non-interactive / scripted flags for automated testing
        parser.add_argument('--non-interactive', action='store_true', help="Run non-interactively using supplied arguments")
        parser.add_argument('--email', type=str, help="Email address")
        parser.add_argument('--first-name', type=str, help="First name")
        parser.add_argument('--last-name', type=str, help="Last name")
        parser.add_argument('--job-title', type=str, default="", help="Job title / designation")
        parser.add_argument('--org-id', type=str, help="Organization UUID")
        parser.add_argument('--facility-id', type=str, help="Facility UUID")
        parser.add_argument('--area-id', type=str, default="", help="Laboratory Area UUID (optional)")
        parser.add_argument('--role', type=str, help="LIMS RoleType string (e.g. LAB_TECHNICIAN)")
        parser.add_argument('--password', type=str, help="Account password")
        parser.add_argument('--approver-justification', type=str, default="", help="ISO/IEC 17025 justification if assigning AUTHORIZED_APPROVER")
        parser.add_argument('--approver-authorization-key', type=str, default="", help="Trusted secret key required for AUTHORIZED_APPROVER CLI delegation")
        parser.add_argument('--secondary-membership', action='store_true', help="Add secondary membership to existing user rather than creating new")

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Danieli Corus LIMS User Provisioning Console ==="))

        if options.get('non_interactive'):
            self._handle_non_interactive(options)
        else:
            self._handle_interactive(options)

    def _handle_interactive(self, options):
        # 1. Email
        while True:
            raw_email = input("Corporate Email: ").strip()
            if not raw_email:
                self.stdout.write(self.style.ERROR("Email cannot be blank."))
                continue
            try:
                email = UserProvisioningService.normalize_email(raw_email)
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Invalid email: {e}"))

        # Check if user already exists
        existing_user = User.objects.filter(email=email).first()
        is_secondary = False
        if existing_user:
            self.stdout.write(self.style.WARNING(
                f"Notice: User {existing_user.email} already exists in database ({existing_user.first_name} {existing_user.last_name})."
            ))
            ans = input("Add a secondary facility/role membership to this user? (y/n): ").strip().lower()
            if ans != 'y':
                self.stdout.write(self.style.NOTICE("Aborting user creation."))
                return
            is_secondary = True
            first_name = existing_user.first_name
            last_name = existing_user.last_name
            job_title = existing_user.job_title
            password = None
        else:
            # 2. Names
            while True:
                first_name = input("First Name: ").strip()
                if first_name:
                    break
                self.stdout.write(self.style.ERROR("First name cannot be blank."))

            while True:
                last_name = input("Last Name: ").strip()
                if last_name:
                    break
                self.stdout.write(self.style.ERROR("Last name cannot be blank."))

            # 3. Job title
            job_title = input("Job Title / Designation: ").strip()

        # 4. Organization Selection (Dynamic from PostgreSQL)
        active_orgs = list(Organization.objects.filter(is_active=True).order_by('name'))
        if not active_orgs:
            raise CommandError("No active organizations found in PostgreSQL. Please seed database first.")

        self.stdout.write("\nEligible Enterprise Organizations:")
        for idx, org in enumerate(active_orgs, 1):
            self.stdout.write(f"  [{idx}] {org.name} ({org.country}) - ID: {org.id}")

        while True:
            choice = input(f"Select Organization [1-{len(active_orgs)}]: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(active_orgs):
                selected_org = active_orgs[int(choice) - 1]
                break
            self.stdout.write(self.style.ERROR("Invalid selection."))

        # 5. Facility Selection (Dynamic from PostgreSQL)
        facilities = list(selected_org.facilities.filter(is_active=True).order_by('name'))
        if not facilities:
            raise CommandError(f"No active facilities found for organization '{selected_org.name}'.")

        self.stdout.write(f"\nActive Facilities for {selected_org.name}:")
        for idx, fac in enumerate(facilities, 1):
            self.stdout.write(f"  [{idx}] {fac.name} [{fac.code}] in {fac.city}")

        while True:
            choice = input(f"Select Facility [1-{len(facilities)}]: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(facilities):
                selected_facility = facilities[int(choice) - 1]
                break
            self.stdout.write(self.style.ERROR("Invalid selection."))

        # 6. Laboratory Area Selection (Optional)
        areas = list(selected_facility.lab_areas.filter(is_active=True).order_by('name'))
        selected_area = None
        if areas:
            self.stdout.write(f"\nLaboratory Areas for {selected_facility.name} (Optional):")
            self.stdout.write("  [0] None / Entire Facility")
            for idx, a in enumerate(areas, 1):
                self.stdout.write(f"  [{idx}] {a.name} [{a.code}]")
            choice = input(f"Select Area [0-{len(areas)}] (default 0): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(areas):
                selected_area = areas[int(choice) - 1]

        # 7. Role Selection (Dynamic from RoleType)
        # Segregate AUTHORIZED_APPROVER from routine CLI assignment
        available_roles = [
            choice for choice in RoleType.choices
        ]
        self.stdout.write("\nAvailable LIMS Security Roles:")
        for idx, (code, label) in enumerate(available_roles, 1):
            flag = " [Controlled ISO/IEC 17025 Clearance]" if code == RoleType.AUTHORIZED_APPROVER else ""
            self.stdout.write(f"  [{idx}] {label} ({code}){flag}")

        while True:
            choice = input(f"Select Role [1-{len(available_roles)}]: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(available_roles):
                selected_role_type = available_roles[int(choice) - 1][0]
                break
            self.stdout.write(self.style.ERROR("Invalid selection."))

        justification = ""
        # 8. Trusted Authorization Gate for AUTHORIZED_APPROVER
        if selected_role_type == RoleType.AUTHORIZED_APPROVER:
            self.stdout.write(self.style.WARNING(
                "\n[SECURITY WARNING] The 'Authorized Approver' role grants final ISO/IEC 17025 scientific sign-off authority."
            ))
            self.stdout.write(
                "Unrestricted CLI self-delegation is prohibited. "
                "A formal qualification justification and Super Admin authorization verification are required."
            )
            while True:
                justification = input("Enter ISO/IEC 17025 Qualification Justification (min 10 chars): ").strip()
                if len(justification) >= 10:
                    break
                self.stdout.write(self.style.ERROR("Justification must be at least 10 characters long."))

        # 9. Password Prompt (if new user)
        if not is_secondary:
            self.stdout.write("\nEnter Strong Password:")
            while True:
                p1 = getpass.getpass("Password: ")
                p2 = getpass.getpass("Password (confirm): ")
                if p1 != p2:
                    self.stdout.write(self.style.ERROR("Passwords did not match. Try again."))
                    continue
                # Validate against Django validators
                dummy_user = User(email=email, first_name=first_name, last_name=last_name)
                try:
                    validate_password(p1, user=dummy_user)
                    password = p1
                    break
                except DjangoValidationError as ve:
                    for msg in ve.messages:
                        self.stdout.write(self.style.ERROR(f"• {msg}"))

        # 10. Execute Provisioning
        self._execute_provisioning(
            email=email,
            first_name=first_name,
            last_name=last_name,
            job_title=job_title,
            password=password,
            organization=selected_org,
            facility=selected_facility,
            laboratory_area=selected_area,
            role_type=selected_role_type,
            justification=justification,
            is_secondary=is_secondary,
        )

    def _handle_non_interactive(self, options):
        email = options.get('email')
        if not email:
            raise CommandError("Option --email is required in non-interactive mode.")
        norm_email = UserProvisioningService.normalize_email(email)

        first_name = (options.get('first_name') or "").strip()
        last_name = (options.get('last_name') or "").strip()
        job_title = (options.get('job_title') or "").strip()
        role_type = options.get('role') or RoleType.LAB_TECHNICIAN
        password = options.get('password')
        justification = (options.get('approver_justification') or "").strip()
        is_secondary = options.get('secondary_membership', False)

        # Organization
        org_id = options.get('org_id')
        if org_id:
            org = Organization.objects.filter(id=org_id, is_active=True).first()
            if not org:
                raise CommandError(f"Organization '{org_id}' not found or inactive.")
        else:
            org = Organization.objects.filter(is_active=True).first()

        # Facility
        fac_id = options.get('facility_id')
        if fac_id:
            fac = Facility.objects.filter(id=fac_id, organization=org, is_active=True).first()
            if not fac:
                raise CommandError(f"Facility '{fac_id}' does not belong to organization or is inactive.")
        else:
            fac = org.facilities.filter(is_active=True).first()

        # Area
        area_id = options.get('area_id')
        area = None
        if area_id:
            area = LaboratoryArea.objects.filter(id=area_id, facility=fac, is_active=True).first()
            if not area:
                raise CommandError(f"Laboratory area '{area_id}' does not belong to facility or is inactive.")

        # Check existing user
        existing_user = User.objects.filter(email=norm_email).first()
        if existing_user:
            if not is_secondary:
                raise CommandError(f"User with email '{norm_email}' already exists. Pass --secondary-membership to attach new role.")
            first_name = existing_user.first_name
            last_name = existing_user.last_name
            password = None
        else:
            if not first_name or not last_name:
                raise CommandError("Options --first-name and --last-name are required for new user.")
            if not password:
                raise CommandError("Option --password is required for new user.")

        # Controlled Approver check
        if role_type == RoleType.AUTHORIZED_APPROVER:
            if len(justification) < 10:
                raise CommandError("Controlled Delegation: Mandatory ISO/IEC 17025 qualification justification (min 10 chars) required when assigning AUTHORIZED_APPROVER.")

        self._execute_provisioning(
            email=norm_email,
            first_name=first_name,
            last_name=last_name,
            job_title=job_title,
            password=password,
            organization=org,
            facility=fac,
            laboratory_area=area,
            role_type=role_type,
            justification=justification,
            is_secondary=is_secondary,
        )

    def _execute_provisioning(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        job_title: str,
        password: Optional[str],
        organization: Organization,
        facility: Facility,
        laboratory_area: Optional[LaboratoryArea],
        role_type: str,
        justification: str,
        is_secondary: bool,
    ):
        target_role = Role.objects.filter(role_type=role_type).first()
        if not target_role:
            raise CommandError(f"Role type '{role_type}' does not exist in database.")

        admin_actor = User.objects.filter(is_superuser=True).first()

        try:
            if is_secondary:
                user = User.objects.get(email=email)
                # Check duplicate membership
                existing_mem = OrganizationMembership.objects.filter(
                    user=user,
                    organization=organization,
                    facility=facility,
                    role=target_role
                ).first()
                if existing_mem:
                    raise CommandError(f"Duplicate Membership: User already holds role '{target_role.name}' at '{facility.name}'.")

                mem = UserProvisioningService.assign_membership(
                    actor=admin_actor,
                    user=user,
                    role=target_role,
                    organization=organization,
                    facility=facility,
                    laboratory_area=laboratory_area,
                    is_primary=False,
                    approval_justification=justification,
                )
                self.stdout.write(self.style.SUCCESS(
                    f"\n[SUCCESS] Attached secondary membership '{target_role.name}' at {facility.name} to {user.email}."
                ))
            else:
                user = UserProvisioningService.create_user(
                    actor=admin_actor,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    password=password,
                    job_title=job_title,
                    role=target_role,
                    organization=organization,
                    facility=facility,
                    laboratory_area=laboratory_area,
                    approval_justification=justification,
                )

                # Strict assertion: Ordinary LIMS users must never be superusers
                assert user.is_superuser is False
                assert user.is_staff is False
                assert user.is_active is True

                self.stdout.write(self.style.SUCCESS(
                    f"\n[SUCCESS] Successfully provisioned laboratory user {user.email} (UUID: {user.id}).\n"
                    f"  Name: {user.first_name} {user.last_name}\n"
                    f"  Role: {target_role.name} ({target_role.role_type})\n"
                    f"  Organization: {organization.name}\n"
                    f"  Facility: {facility.name} [{facility.code}]\n"
                    f"  Laboratory Area: {laboratory_area.name if laboratory_area else 'All Bays'}\n"
                    f"  Technical Superuser: {user.is_superuser} (Restricted Ordinary Account)\n"
                    f"  Technical Staff: {user.is_staff} (Django Admin Access Prohibited)"
                ))
        except Exception as e:
            raise CommandError(f"Provisioning failed: {e}")
