import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import User, Role, RoleType, OrganizationMembership
from organizations.models import Organization, OrganizationType, Facility


class Command(BaseCommand):
    help = "Idempotently repairs existing accounts and assigns RBAC memberships without altering passwords or deleting records."

    ACCOUNT_ROLE_MAPPING = {
        'superadmin@gmail.com': {
            'role_type': RoleType.SUPER_ADMIN,
            'job_title': 'Enterprise LIMS System Administrator',
            'phone': '+31 251 499111',
            'first_name': 'Super',
            'last_name': 'Admin',
        },
        'authorized.approver@gmail.com': {
            'role_type': RoleType.AUTHORIZED_APPROVER,
            'job_title': 'Principal Refractory Metallurgist & Sign-off Authority',
            'phone': '+31 251 499201',
            'first_name': 'Authorized',
            'last_name': 'Approver',
        },
        'sample.clerk@gmail.com': {
            'role_type': RoleType.SAMPLE_CLERK,
            'job_title': 'Specimen Receiving & Chain-of-Custody Clerk',
            'phone': '+31 251 499202',
            'first_name': 'Sample',
            'last_name': 'Clerk',
        },
        'report.coordinator@gmail.com': {
            'role_type': RoleType.REPORT_COORDINATOR,
            'job_title': 'Technical Dossier & Report Coordinator',
            'phone': '+31 251 499203',
            'first_name': 'Report',
            'last_name': 'Coordinator',
        },
        'storage.custodian@gmail.com': {
            'role_type': RoleType.STORAGE_CUSTODIAN,
            'job_title': 'Archive Vault & Refractory Specimen Custodian',
            'phone': '+31 251 499204',
            'first_name': 'Storage',
            'last_name': 'Custodian',
        },
        'inspector@gmail.com': {
            'role_type': RoleType.INSPECTOR,
            'job_title': 'Third-Party Refractory Inspector',
            'phone': '+31 251 499205',
            'first_name': 'Inspector',
            'last_name': 'General',
        },
        'facility.manager@gmail.com': {
            'role_type': RoleType.FACILITY_MANAGER,
            'job_title': 'IJmuiden Works Refractory Facility Director',
            'phone': '+31 251 499206',
            'first_name': 'Facility',
            'last_name': 'Manager',
        },
        'lab.manager@gmail.com': {
            'role_type': RoleType.LAB_MANAGER,
            'job_title': 'Refractory Testing Laboratory Operations Manager',
            'phone': '+31 251 499207',
            'first_name': 'Lab',
            'last_name': 'Manager',
        },
        'qa.reviewer@gmail.com': {
            'role_type': RoleType.QA_REVIEWER,
            'job_title': 'Senior Refractory Quality Assurance Reviewer',
            'phone': '+31 251 499208',
            'first_name': 'QA',
            'last_name': 'Reviewer',
        },
        'lab.technician@gmail.com': {
            'role_type': RoleType.LAB_TECHNICIAN,
            'job_title': 'Refractory Testing Technician (Thermal & Mechanical)',
            'phone': '+31 251 499209',
            'first_name': 'Lab',
            'last_name': 'Technician',
        },
        'e.rostova@danieli-corus.com': {
            'role_type': RoleType.AUTHORIZED_APPROVER,
            'job_title': 'Head of Technical Governance & Sign-off Authority',
            'phone': '+31 251 499015',
            'first_name': 'Dr. Elena',
            'last_name': 'Rostova',
        },
        'r.sharma@danieli-corus.com': {
            'role_type': RoleType.LAB_TECHNICIAN,
            'job_title': 'Senior Refractory Testing Specialist',
            'phone': '+31 251 499022',
            'first_name': 'Rajiv',
            'last_name': 'Sharma',
        },
    }

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== DANIELI CORUS LIMS: REPAIRING USER ACCOUNTS & RBAC ==="))

        with transaction.atomic():
            # 1. Resolve or create Danieli Corus Primary Organization
            org, _ = Organization.objects.get_or_create(
                name="Danieli Corus B.V. IJmuiden",
                defaults={
                    'org_type': OrganizationType.DANIELI_CORUS,
                    'country': 'NL',
                    'address': 'Rooswijkweg 291, 1951 ME Velsen-Noord, Netherlands',
                    'accreditation_number': 'TEST-NL-17025-091',
                    'is_active': True,
                }
            )

            # 2. Resolve or create IJmuiden Primary Facility
            facility, _ = Facility.objects.get_or_create(
                code="DC-IJM-01",
                defaults={
                    'organization': org,
                    'name': 'Refractory Technology Centre IJmuiden',
                    'city': 'IJmuiden',
                    'is_primary': True,
                    'is_active': True,
                }
            )
            if facility.organization != org:
                facility.organization = org
                facility.save(update_fields=['organization'])

            # 3. Ensure All Role instances exist with exact authority flags
            roles_spec = [
                {
                    'role_type': RoleType.SUPER_ADMIN,
                    'name': 'Super Admin',
                    'description': 'Full administrative control over LIMS configurations, user management, and security governance.',
                    'can_manage_facility': True,
                    'can_manage_samples': True,
                },
                {
                    'role_type': RoleType.FACILITY_MANAGER,
                    'name': 'Facility Manager',
                    'description': 'Operational direction of testing facilities, equipment availability, and environmental monitoring.',
                    'can_manage_facility': True,
                },
                {
                    'role_type': RoleType.LAB_MANAGER,
                    'name': 'Lab Manager',
                    'description': 'Supervises laboratory personnel, dispatches work orders, and oversees sample progress.',
                    'can_manage_samples': True,
                    'can_verify_results': True,
                },
                {
                    'role_type': RoleType.SAMPLE_CLERK,
                    'name': 'Sample Clerk',
                    'description': 'Responsible for refractory sample registration, physical receiving, inspection for transit damage, and barcode labeling.',
                    'can_manage_samples': True,
                },
                {
                    'role_type': RoleType.INSPECTOR,
                    'name': 'Inspector',
                    'description': 'Conducts dimensional visual examination, intake checklists, and specimen preparation sign-off.',
                    'can_manage_samples': True,
                },
                {
                    'role_type': RoleType.LAB_TECHNICIAN,
                    'name': 'Lab Technician',
                    'description': 'Executes standardized thermal, physical, and chemical refractory test runs according to Procedure R-01.',
                    'can_input_results': True,
                    'can_manage_samples': True,
                },
                {
                    'role_type': RoleType.QA_REVIEWER,
                    'name': 'QA Reviewer',
                    'description': 'Performs metrological data verification, standard deviation analysis, and compliance checks against R-01 thresholds.',
                    'can_verify_results': True,
                },
                {
                    'role_type': RoleType.AUTHORIZED_APPROVER,
                    'name': 'Authorized Approver',
                    'description': 'Final technical and scientific authority legally certified to approve and digitally seal Certificate of Refractory Conformance (CRC) reports.',
                    'can_sign_certificates': True,
                    'can_verify_results': True,
                },
                {
                    'role_type': RoleType.REPORT_COORDINATOR,
                    'name': 'Report Coordinator',
                    'description': 'Compiles technical dossiers, customer certificates, and historical test report archives.',
                },
                {
                    'role_type': RoleType.STORAGE_CUSTODIAN,
                    'name': 'Storage Custodian',
                    'description': 'Manages archive storage racks, environmental retention vaults, and counter-sample custody tracking.',
                    'can_manage_storage': True,
                },
            ]

            roles_map = {}
            for spec in roles_spec:
                rtype = spec['role_type']
                role_obj, _ = Role.objects.get_or_create(
                    role_type=rtype,
                    defaults=spec
                )
                # Ensure permission flags are current
                updated = False
                for k, v in spec.items():
                    if getattr(role_obj, k) != v:
                        setattr(role_obj, k, v)
                        updated = True
                if updated:
                    role_obj.save()
                roles_map[rtype] = role_obj

            # 4. Repair each account
            repaired_count = 0
            for email, meta in self.ACCOUNT_ROLE_MAPPING.items():
                user = User.objects.filter(email=email).first()
                if not user:
                    self.stdout.write(self.style.WARNING(f"  [-] User {email} not found in database. Skipping."))
                    continue

                # Update metadata if blank or generic
                save_fields = []
                if not user.job_title or user.job_title != meta['job_title']:
                    user.job_title = meta['job_title']
                    save_fields.append('job_title')
                if not user.phone_number:
                    user.phone_number = meta['phone']
                    save_fields.append('phone_number')
                if not user.is_active:
                    user.is_active = True
                    save_fields.append('is_active')
                if save_fields:
                    user.save(update_fields=save_fields)

                target_role = roles_map[meta['role_type']]

                # Link or update OrganizationMembership
                membership, created = OrganizationMembership.objects.get_or_create(
                    user=user,
                    organization=org,
                    facility=facility,
                    role=target_role,
                    defaults={
                        'is_primary': True,
                        'is_active': True,
                    }
                )

                if not created and (not membership.is_active or not membership.is_primary):
                    membership.is_active = True
                    membership.is_primary = True
                    membership.save(update_fields=['is_active', 'is_primary'])

                repaired_count += 1
                status_str = "CREATED" if created else "ALREADY ACTIVE"
                self.stdout.write(self.style.SUCCESS(
                    f"  [+] {user.email:<32} -> {target_role.name:<24} [{status_str}]"
                ))

            # 5. Check if any other user has no membership
            orphan_users = User.objects.filter(memberships__isnull=True)
            for orphan in orphan_users:
                # Default orphan users to LAB_TECHNICIAN so they are never broken
                tech_role = roles_map[RoleType.LAB_TECHNICIAN]
                OrganizationMembership.objects.get_or_create(
                    user=orphan,
                    organization=org,
                    facility=facility,
                    role=tech_role,
                    defaults={'is_primary': True, 'is_active': True}
                )
                self.stdout.write(self.style.SUCCESS(
                    f"  [+] Fixed orphan user {orphan.email} -> Lab Technician"
                ))

        self.stdout.write(self.style.SUCCESS(f"\nAccount repair completed successfully! Repaired {repaired_count} users."))
