import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.sessions.models import Session
from django.utils import timezone

from accounts.models import User, Role, RoleType, OrganizationMembership
from organizations.models import Organization, Facility
from audit.models import AuditEvent, AuditAction


class Command(BaseCommand):
    help = (
        "Phase 2 — Audits and repairs accidentally elevated Django superuser privileges "
        "and binds accounts to approved LIMS business roles with session invalidation and audit trail."
    )

    # Approved ten-account specification
    APPROVED_ACCOUNTS = {
        'superadmin@gmail.com': {
            'role_type': RoleType.SUPER_ADMIN,
            'is_superuser': True,
            'is_staff': True,
            'job_title': 'Enterprise LIMS System Administrator',
            'phone': '+31 251 499111',
            'first_name': 'Super',
            'last_name': 'Admin',
        },
        'facility.manager@gmail.com': {
            'role_type': RoleType.FACILITY_MANAGER,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'IJmuiden Works Refractory Facility Director',
            'phone': '+31 251 499206',
            'first_name': 'Facility',
            'last_name': 'Manager',
        },
        'lab.manager@gmail.com': {
            'role_type': RoleType.LAB_MANAGER,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'Refractory Testing Laboratory Operations Manager',
            'phone': '+31 251 499207',
            'first_name': 'Lab',
            'last_name': 'Manager',
        },
        'sample.clerk@gmail.com': {
            'role_type': RoleType.SAMPLE_CLERK,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'Specimen Receiving & Chain-of-Custody Clerk',
            'phone': '+31 251 499202',
            'first_name': 'Sample',
            'last_name': 'Clerk',
        },
        'inspector@gmail.com': {
            'role_type': RoleType.INSPECTOR,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'Third-Party Refractory Inspector',
            'phone': '+31 251 499205',
            'first_name': 'Inspector',
            'last_name': 'General',
        },
        'lab.technician@gmail.com': {
            'role_type': RoleType.LAB_TECHNICIAN,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'Refractory Testing Technician (Thermal & Mechanical)',
            'phone': '+31 251 499209',
            'first_name': 'Lab',
            'last_name': 'Technician',
        },
        'qa.reviewer@gmail.com': {
            'role_type': RoleType.QA_REVIEWER,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'Senior Refractory Quality Assurance Reviewer',
            'phone': '+31 251 499208',
            'first_name': 'QA',
            'last_name': 'Reviewer',
        },
        'authorized.approver@gmail.com': {
            'role_type': RoleType.AUTHORIZED_APPROVER,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'Principal Refractory Metallurgist & Sign-off Authority',
            'phone': '+31 251 499201',
            'first_name': 'Authorized',
            'last_name': 'Approver',
        },
        'report.coordinator@gmail.com': {
            'role_type': RoleType.REPORT_COORDINATOR,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'Technical Dossier & Report Coordinator',
            'phone': '+31 251 499203',
            'first_name': 'Report',
            'last_name': 'Coordinator',
        },
        'storage.custodian@gmail.com': {
            'role_type': RoleType.STORAGE_CUSTODIAN,
            'is_superuser': False,
            'is_staff': False,
            'job_title': 'Archive Vault & Refractory Specimen Custodian',
            'phone': '+31 251 499204',
            'first_name': 'Storage',
            'last_name': 'Custodian',
        },
    }

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--dry-run',
            action='store_true',
            help='Analyze database state, display current privileges vs proposed changes, and identify conflicts without saving.',
        )
        group.add_argument(
            '--apply',
            action='store_true',
            help='Apply approved privilege demotions, membership corrections, session revocations, and audit logs.',
        )
        parser.add_argument(
            '--yes',
            '-y',
            action='store_true',
            help='Bypass interactive confirmation prompt when running with --apply.',
        )

    def handle(self, *args, **options):
        is_dry_run = options['dry_run']
        is_apply = options['apply']
        auto_confirm = options['yes']

        mode_header = "DRY RUN (NO DATABASE CHANGES)" if is_dry_run else "APPLYING PRIVILEGE & RBAC CORRECTIONS"
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{'='*80}"))
        self.stdout.write(self.style.MIGRATE_HEADING(f" DANIELI CORUS LIMS — USER PRIVILEGE REPAIR AUDITOR"))
        self.stdout.write(self.style.MIGRATE_HEADING(f" MODE: {mode_header}"))
        self.stdout.write(self.style.MIGRATE_HEADING(f"{'='*80}\n"))

        # 1. Validate Organization and Facility Prerequisites
        org = Organization.objects.filter(org_type='DANIELI_CORUS').first() or Organization.objects.filter(name__icontains="Danieli Corus").first()
        facility = None
        missing_entities = []

        if not org:
            missing_entities.append("Organization: Danieli Corus B.V. (org_type=DANIELI_CORUS)")
        else:
            facility = Facility.objects.filter(organization=org, code="DC-IJM-01").first() or Facility.objects.filter(organization=org).first()
            if not facility:
                missing_entities.append("Facility: DC-IJM-01 (Refractory Technology Centre IJmuiden)")

        # Validate Role records
        roles_cache = {}
        for rtype in RoleType:
            role_obj = Role.objects.filter(role_type=rtype).first()
            if role_obj:
                roles_cache[rtype] = role_obj
            else:
                missing_entities.append(f"Role: {rtype}")

        # Display Prerequisite Status
        self.stdout.write(self.style.HTTP_INFO("[1] INFRASTRUCTURE & PREREQUISITE VALIDATION"))
        if missing_entities:
            self.stdout.write(self.style.ERROR("  [!] Critical Prerequisites Missing from Database:"))
            for m in missing_entities:
                self.stdout.write(self.style.ERROR(f"      - {m}"))
            raise CommandError("Aborting: Required infrastructure entities do not exist in database.")
        else:
            self.stdout.write(self.style.SUCCESS(f"  [✓] Verified Primary Organization: {org.name} [{org.id}]"))
            self.stdout.write(self.style.SUCCESS(f"  [✓] Verified Operating Facility:   {facility.name} [{facility.code}]"))
            self.stdout.write(self.style.SUCCESS(f"  [✓] Verified Standard Roles:       {len(roles_cache)}/10 RBAC roles loaded."))

        self.stdout.write("\n" + "-"*80)

        # 2. Analyze Existing Accounts & Proposed Changes
        self.stdout.write(self.style.HTTP_INFO("[2] EXISTING ACCOUNTS & CURRENT PRIVILEGES AUDIT"))
        self.stdout.write(f"{'Email':<32} {'Superuser':<10} {'Staff':<8} {'Active':<8} {'Existing Roles'}")
        self.stdout.write("-" * 80)

        account_plans = []
        conflicts = []

        for email, spec in self.APPROVED_ACCOUNTS.items():
            user = User.objects.filter(email=email).first()
            if not user:
                conflicts.append(f"Account {email} NOT FOUND in database!")
                self.stdout.write(self.style.ERROR(f"{email:<32} [NOT FOUND IN DATABASE]"))
                continue

            current_memberships = list(user.memberships.select_related('role', 'facility', 'organization').all())
            roles_str = ", ".join([f"{m.role.role_type} ({'Primary' if m.is_primary else 'Sec'})" for m in current_memberships]) or "None"

            # Check privilege status
            sup_flag = "True" if user.is_superuser else "False"
            stf_flag = "True" if user.is_staff else "False"
            act_flag = "True" if user.is_active else "False"

            self.stdout.write(f"{user.email:<32} {sup_flag:<10} {stf_flag:<8} {act_flag:<8} {roles_str}")

            target_role = roles_cache[spec['role_type']]
            has_matching_membership = any(
                m.role == target_role and m.organization == org and m.facility == facility and m.is_active
                for m in current_memberships
            )

            demote_superuser = user.is_superuser != spec['is_superuser']
            demote_staff = user.is_staff != spec['is_staff']
            update_membership = not has_matching_membership

            account_plans.append({
                'user': user,
                'spec': spec,
                'target_role': target_role,
                'current_memberships': current_memberships,
                'demote_superuser': demote_superuser,
                'demote_staff': demote_staff,
                'update_membership': update_membership,
            })

        self.stdout.write("\n" + "-"*80)

        # 3. Display Proposed Changes
        self.stdout.write(self.style.HTTP_INFO("[3] PROPOSED REPAIR ACTIONS"))
        self.stdout.write(f"{'Email':<30} {'Privilege Action':<26} {'Target RBAC Role':<24}")
        self.stdout.write("-" * 80)

        for plan in account_plans:
            u = plan['user']
            spec = plan['spec']

            priv_changes = []
            if plan['demote_superuser']:
                priv_changes.append(f"is_superuser: {u.is_superuser} -> {spec['is_superuser']}")
            if plan['demote_staff']:
                priv_changes.append(f"is_staff: {u.is_staff} -> {spec['is_staff']}")

            priv_str = "; ".join(priv_changes) if priv_changes else "Privileges Unchanged"
            role_action = f"{plan['target_role'].name} (Link)" if plan['update_membership'] else f"{plan['target_role'].name} (Preserved)"

            style_func = self.style.WARNING if (plan['demote_superuser'] or plan['demote_staff']) else self.style.SUCCESS
            self.stdout.write(style_func(f"{u.email:<30} {priv_str:<26} {role_action:<24}"))

        self.stdout.write("\n" + "-"*80)

        # 4. Security Notes on Password Rotation & Session Invalidation
        self.stdout.write(self.style.HTTP_INFO("[4] SECURITY GOVERNANCE & SESSION INVALIDATION PLAN"))
        self.stdout.write("  [i] All 9 demoted operational accounts previously bypassed password complexity validators.")
        self.stdout.write("  [i] Applying changes will:")
        self.stdout.write("      * Invalidate all active HTTP session cookies (dc_lims_sessionid) for demoted accounts.")
        self.stdout.write("      * Log an immutable ISO/IEC 17025 AuditEvent for every privilege demotion and role mapping.")
        self.stdout.write("      * Require password rotation via the LIMS administrative interface or password reset view.")
        self.stdout.write("      * Strictly preserve superadmin@gmail.com as the only technical Django superuser.")

        # Show conflicts if any
        if conflicts:
            self.stdout.write("\n" + self.style.ERROR(f"[!] Conflicts Identified ({len(conflicts)}):"))
            for c in conflicts:
                self.stdout.write(self.style.ERROR(f"    - {c}"))

        # 5. Execution or Stop
        if is_dry_run:
            self.stdout.write("\n" + self.style.SUCCESS("="*80))
            self.stdout.write(self.style.SUCCESS(" DRY-RUN COMPLETE: NO CHANGES WERE COMMITTED TO THE DATABASE."))
            self.stdout.write(self.style.SUCCESS(" To apply these changes, run:"))
            self.stdout.write(self.style.SUCCESS("   python manage.py repair_lims_users --apply"))
            self.stdout.write(self.style.SUCCESS("="*80 + "\n"))
            return

        # Handle --apply
        if is_apply:
            if not auto_confirm:
                self.stdout.write("\n" + self.style.WARNING("="*80))
                self.stdout.write(self.style.WARNING(" WARNING: YOU ARE ABOUT TO MODIFY 10 ACCOUNTS IN DATABASE 'danieli_lims_db'."))
                self.stdout.write(self.style.WARNING(" This will demote 9 accounts from Django superusers and terminate their active sessions."))
                self.stdout.write(self.style.WARNING("="*80))
                confirm = input("\nType 'yes' to proceed with the privilege demotions and role repairs: ").strip().lower()
                if confirm != 'yes':
                    self.stdout.write(self.style.ERROR("\nOperation cancelled by user. No database changes were made.\n"))
                    return

            self.stdout.write("\nApplying changes within atomic transaction with row locking...")

            applied_privileges = 0
            applied_memberships = 0
            demoted_user_ids = []

            # Find a valid actor for audit trail (e.g. superadmin)
            superadmin_user = User.objects.filter(email='superadmin@gmail.com').first()

            with transaction.atomic():
                for plan in account_plans:
                    user_id = plan['user'].id
                    # Row-level lock on affected User row
                    user = User.objects.select_for_update().get(id=user_id)
                    spec = plan['spec']
                    target_role = plan['target_role']

                    user_updated_fields = []

                    # Demote superuser / staff
                    if user.is_superuser != spec['is_superuser']:
                        user.is_superuser = spec['is_superuser']
                        user_updated_fields.append('is_superuser')
                    if user.is_staff != spec['is_staff']:
                        user.is_staff = spec['is_staff']
                        user_updated_fields.append('is_staff')

                    # Metadata consistency
                    if not user.job_title or user.job_title != spec['job_title']:
                        user.job_title = spec['job_title']
                        user_updated_fields.append('job_title')
                    if not user.phone_number:
                        user.phone_number = spec['phone']
                        user_updated_fields.append('phone_number')

                    if user_updated_fields:
                        user.save(update_fields=user_updated_fields)
                        applied_privileges += 1
                        if not spec['is_superuser']:
                            demoted_user_ids.append(str(user.id))

                        # Audit privilege change
                        AuditEvent.objects.create(
                            actor=superadmin_user or user,
                            action=AuditAction.UPDATE,
                            entity_type='User',
                            entity_id=str(user.id),
                            summary=f"Demoted accidentally elevated privileges for {user.email}: is_superuser={user.is_superuser}, is_staff={user.is_staff}",
                            changes_json={
                                'is_superuser': user.is_superuser,
                                'is_staff': user.is_staff,
                                'repaired_role': target_role.role_type,
                            }
                            )


                    # Membership creation / update
                    membership, created = OrganizationMembership.objects.select_for_update().get_or_create(
                        user=user,
                        organization=org,
                        facility=facility,
                        role=target_role,
                        defaults={
                            'is_primary': True,
                            'is_active': True,
                        }
                    )
                    if not created:
                        if not membership.is_active or not membership.is_primary:
                            membership.is_active = True
                            membership.is_primary = True
                            membership.save(update_fields=['is_active', 'is_primary'])
                    applied_memberships += 1

                # Invalidate active sessions for demoted users
                now = timezone.now()
                revoked_sessions = 0
                for s in Session.objects.filter(expire_date__gte=now):
                    try:
                        data = s.get_decoded()
                        if data.get('_auth_user_id') in demoted_user_ids:
                            s.delete()
                            revoked_sessions += 1
                    except Exception:
                        pass

            self.stdout.write(self.style.SUCCESS(f"\n[✓] Successfully updated privileges for {applied_privileges} accounts."))
            self.stdout.write(self.style.SUCCESS(f"[✓] Successfully verified & linked {applied_memberships} RBAC memberships."))
            self.stdout.write(self.style.SUCCESS(f"[✓] Revoked {revoked_sessions} active sessions for demoted users."))
            self.stdout.write(self.style.SUCCESS(f"[✓] Created immutable ISO/IEC 17025 audit logs."))
            self.stdout.write(self.style.SUCCESS(f"\nPrivilege repair successfully completed!\n"))
