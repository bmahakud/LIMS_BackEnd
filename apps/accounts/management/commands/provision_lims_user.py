import getpass
from django.core.management.base import BaseCommand, CommandError
from accounts.models import User, Role, RoleType
from accounts.services import UserProvisioningService
from organizations.models import Organization, Facility


class Command(BaseCommand):
    help = "Provisions a new LIMS laboratory user via the shared UserProvisioningService with interactive password prompt."

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, required=True, help="User's email address")
        parser.add_argument('--first-name', type=str, required=True, help="First name")
        parser.add_argument('--last-name', type=str, required=True, help="Last name")
        parser.add_argument('--role', type=str, default='LAB_TECHNICIAN', choices=[c[0] for c in RoleType.choices], help="Assigned role type")
        parser.add_argument('--job-title', type=str, default='', help="Job title / position")
        parser.add_argument('--phone', type=str, default='', help="Contact phone number")
        parser.add_argument('--justification', type=str, default='', help="Justification if assigning AUTHORIZED_APPROVER")

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        first_name = options['first_name'].strip()
        last_name = options['last_name'].strip()
        role_type = options['role']
        job_title = options['job_title'].strip()
        phone = options['phone'].strip()
        justification = options['justification'].strip()

        self.stdout.write(self.style.NOTICE(f"\n--- Provisioning Laboratory User: {email} ---"))

        # Interactive password prompt for secure local development
        password = None
        while not password:
            p1 = getpass.getpass("Enter password (min 10 characters): ")
            p2 = getpass.getpass("Confirm password: ")
            if p1 != p2:
                self.stdout.write(self.style.ERROR("Passwords do not match. Please try again."))
                continue
            password = p1

        # Locate administrative actor for audit trail (e.g. superadmin@gmail.com)
        admin_actor = User.objects.filter(is_superuser=True).first()

        try:
            user = UserProvisioningService.create_user(
                actor=admin_actor,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
                job_title=job_title,
                phone_number=phone,
                role_type=role_type,
                approval_justification=justification,
            )
            self.stdout.write(self.style.SUCCESS(
                f"Successfully provisioned user {user.email} (ID: {user.id}) with role {role_type}."
            ))
        except Exception as e:
            raise CommandError(f"User provisioning failed: {e}")
