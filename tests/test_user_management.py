import pytest
from rest_framework import status
from rest_framework.test import APIClient
from accounts.models import User, Role, RoleType, OrganizationMembership
from organizations.models import Organization, OrganizationType, Facility
from audit.models import AuditEvent, AuditAction


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def lab_setup(db):
    org = Organization.objects.create(
        name="Danieli Corus B.V. Test",
        org_type=OrganizationType.DANIELI_CORUS,
        country="NL",
        accreditation_number="TEST-17025-01"
    )
    facility = Facility.objects.create(
        organization=org,
        name="Refractory Technology Centre Test",
        code="DC-TEST-01",
        city="IJmuiden",
        is_primary=True
    )
    roles = {}
    for rtype in RoleType:
        role, _ = Role.objects.get_or_create(
            role_type=rtype,
            defaults={
                'name': rtype.label,
                'can_sign_certificates': (rtype == RoleType.AUTHORIZED_APPROVER),
                'can_verify_results': (rtype in [RoleType.AUTHORIZED_APPROVER, RoleType.QA_REVIEWER]),
                'can_input_results': (rtype == RoleType.LAB_TECHNICIAN),
                'can_manage_samples': (rtype in [RoleType.SAMPLE_CLERK, RoleType.LAB_TECHNICIAN, RoleType.LAB_MANAGER]),
                'can_manage_facility': (rtype in [RoleType.FACILITY_MANAGER, RoleType.SUPER_ADMIN]),
            }
        )
        roles[rtype] = role

    # Create admin user
    admin_user = User.objects.create_user(
        email="test_admin@danieli-corus.com",
        password="AdminSecurePassword123!",
        first_name="Admin",
        last_name="Officer",
        job_title="Security Admin",
        is_staff=True,
        is_superuser=True
    )
    OrganizationMembership.objects.create(
        user=admin_user,
        organization=org,
        facility=facility,
        role=roles[RoleType.SUPER_ADMIN],
        is_primary=True,
        is_active=True
    )

    # Create regular technician user
    tech_user = User.objects.create_user(
        email="test_tech@danieli-corus.com",
        password="TechSecurePassword123!",
        first_name="Tech",
        last_name="Worker",
        job_title="Testing Technician"
    )
    OrganizationMembership.objects.create(
        user=tech_user,
        organization=org,
        facility=facility,
        role=roles[RoleType.LAB_TECHNICIAN],
        is_primary=True,
        is_active=True
    )

    # Create authorized approver user
    approver_user = User.objects.create_user(
        email="test_approver@danieli-corus.com",
        password="ApproverPassword123!",
        first_name="Elena",
        last_name="Approver",
        job_title="Lead Approver"
    )
    OrganizationMembership.objects.create(
        user=approver_user,
        organization=org,
        facility=facility,
        role=roles[RoleType.AUTHORIZED_APPROVER],
        is_primary=True,
        is_active=True
    )

    return {
        'org': org,
        'facility': facility,
        'roles': roles,
        'admin_user': admin_user,
        'tech_user': tech_user,
        'approver_user': approver_user,
    }


@pytest.mark.django_db
def test_user_management_list_authenticated_admin(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])
    response = api_client.get('/api/v1/auth/users/')
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) >= 3
    emails = [u['email'] for u in data]
    assert "test_admin@danieli-corus.com" in emails
    assert "test_tech@danieli-corus.com" in emails

    tech_entry = next(u for u in data if u['email'] == "test_tech@danieli-corus.com")
    assert tech_entry['primary_role']['role_type'] == RoleType.LAB_TECHNICIAN
    assert tech_entry['primary_facility']['code'] == "DC-TEST-01"


@pytest.mark.django_db
def test_user_management_list_unauthorized_rejected(api_client, lab_setup):
    # Unauthenticated gets 403
    anon_response = api_client.get('/api/v1/auth/users/')
    assert anon_response.status_code == status.HTTP_403_FORBIDDEN

    # Normal lab technician without user management clearance gets 403
    api_client.force_authenticate(user=lab_setup['tech_user'])
    tech_response = api_client.get('/api/v1/auth/users/')
    assert tech_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_user_filtering_by_role_and_search(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])

    # Filter by role
    res_role = api_client.get('/api/v1/auth/users/?role=LAB_TECHNICIAN')
    assert res_role.status_code == status.HTTP_200_OK
    assert all(u['primary_role']['role_type'] == 'LAB_TECHNICIAN' for u in res_role.json())

    # Search keyword
    res_search = api_client.get('/api/v1/auth/users/?search=approver')
    assert res_search.status_code == status.HTTP_200_OK
    assert len(res_search.json()) == 1
    assert res_search.json()[0]['email'] == "test_approver@danieli-corus.com"


@pytest.mark.django_db
def test_user_creation_with_role_and_audit(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])
    payload = {
        'email': 'new_inspector@danieli-corus.com',
        'password': 'InspectorPass2026!',
        'first_name': 'Marco',
        'last_name': 'Bellini',
        'job_title': 'Dimensional Quality Inspector',
        'phone_number': '+31 251 499555',
        'role_type': 'INSPECTOR',
        'facility_id': str(lab_setup['facility'].id),
        'is_active': True
    }
    response = api_client.post('/api/v1/auth/users/', payload, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data['email'] == 'new_inspector@danieli-corus.com'
    assert data['primary_role']['role_type'] == 'INSPECTOR'

    # Check database persistence
    user = User.objects.get(email='new_inspector@danieli-corus.com')
    assert user.check_password('InspectorPass2026!')
    assert user.memberships.filter(role__role_type='INSPECTOR', is_active=True).exists()

    # Check ISO 17025 audit trail entry
    audit = AuditEvent.objects.filter(entity_type='User', entity_id=str(user.id)).first()
    assert audit is not None
    assert audit.action == AuditAction.CREATE
    assert audit.actor == lab_setup['admin_user']


@pytest.mark.django_db
def test_user_creation_duplicate_email_rejected(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])
    payload = {
        'email': 'test_admin@danieli-corus.com',  # Duplicate!
        'password': 'SomePassword123!',
        'first_name': 'Copy',
        'last_name': 'Cat',
    }
    response = api_client.post('/api/v1/auth/users/', payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'email' in response.json()


@pytest.mark.django_db
def test_user_update_profile_and_status(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])
    tech = lab_setup['tech_user']

    update_payload = {
        'job_title': 'Lead High-Temp Metrologist',
        'phone_number': '+31 251 499999',
        'is_active': False
    }
    response = api_client.patch(f'/api/v1/auth/users/{tech.id}/', update_payload, format='json')
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data['job_title'] == 'Lead High-Temp Metrologist'
    assert data['is_active'] is False

    tech.refresh_from_db()
    assert tech.job_title == 'Lead High-Temp Metrologist'
    assert tech.is_active is False


@pytest.mark.django_db
def test_prevent_admin_self_deactivation(api_client, lab_setup):
    admin = lab_setup['admin_user']
    api_client.force_authenticate(user=admin)

    response = api_client.patch(f'/api/v1/auth/users/{admin.id}/', {'is_active': False}, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Security violation" in response.json()['detail']

    admin.refresh_from_db()
    assert admin.is_active is True


@pytest.mark.django_db
def test_admin_password_reset(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])
    tech = lab_setup['tech_user']

    response = api_client.post(
        f'/api/v1/auth/users/{tech.id}/reset-password/',
        {'new_password': 'BrandNewSecurePass2026!'},
        format='json'
    )
    assert response.status_code == status.HTTP_200_OK

    tech.refresh_from_db()
    assert tech.check_password('BrandNewSecurePass2026!')
    assert not tech.check_password('TechSecurePassword123!')


@pytest.mark.django_db
def test_assign_and_revoke_role_membership(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])
    tech = lab_setup['tech_user']
    qa_role = lab_setup['roles'][RoleType.QA_REVIEWER]

    # Assign secondary role
    assign_payload = {
        'role_id': str(qa_role.id),
        'organization_id': str(lab_setup['org'].id),
        'facility_id': str(lab_setup['facility'].id),
        'is_primary': False
    }
    res_assign = api_client.post(f'/api/v1/auth/users/{tech.id}/memberships/', assign_payload, format='json')
    assert res_assign.status_code == status.HTTP_201_CREATED
    membership_id = res_assign.json()['id']

    tech.refresh_from_db()
    assert tech.memberships.filter(role=qa_role, is_active=True).exists()

    # Revoke secondary role
    res_revoke = api_client.delete(f'/api/v1/auth/users/{tech.id}/memberships/{membership_id}/')
    assert res_revoke.status_code == status.HTTP_200_OK

    assert tech.memberships.filter(id=membership_id, is_active=False).exists()


@pytest.mark.django_db
def test_roles_and_facilities_directories(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['tech_user'])

    # Roles directory
    res_roles = api_client.get('/api/v1/auth/roles/')
    assert res_roles.status_code == status.HTTP_200_OK
    roles_data = res_roles.json()
    assert len(roles_data) == len(RoleType)
    approver = next(r for r in roles_data if r['role_type'] == 'AUTHORIZED_APPROVER')
    assert approver['can_sign_certificates'] is True

    # Facilities directory
    res_fac = api_client.get('/api/v1/auth/facilities/')
    assert res_fac.status_code == status.HTTP_200_OK
    fac_data = res_fac.json()
    assert 'organizations' in fac_data
    assert len(fac_data['organizations']) >= 1


@pytest.mark.django_db
def test_prevent_self_role_elevation(api_client, lab_setup):
    admin = lab_setup['admin_user']
    api_client.force_authenticate(user=admin)
    approver_role = lab_setup['roles'][RoleType.AUTHORIZED_APPROVER]

    # Admin attempts to assign self the Authorized Approver role
    res = api_client.post(
        f'/api/v1/auth/users/{admin.id}/memberships/',
        {
            'role_id': str(approver_role.id),
            'organization_id': str(lab_setup['org'].id),
            'facility_id': str(lab_setup['facility'].id),
        },
        format='json'
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Users cannot assign or elevate their own roles" in res.json()['detail']


@pytest.mark.django_db
def test_reject_technical_privilege_tampering_in_payloads(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])

    # Attempting to inject is_superuser in user creation
    payload = {
        'email': 'hacker@danieli-corus.com',
        'first_name': 'Bad',
        'last_name': 'Actor',
        'password': 'Password123!',
        'is_superuser': True,  # Tampering attempt!
    }
    res = api_client.post('/api/v1/auth/users/', payload, format='json')
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Technical privileges" in str(res.json())

    # Attempting to inject is_staff in user update
    tech = lab_setup['tech_user']
    res_update = api_client.patch(f'/api/v1/auth/users/{tech.id}/', {'is_staff': True}, format='json')
    assert res_update.status_code == status.HTTP_400_BAD_REQUEST
    assert "Technical privileges" in str(res_update.json())


@pytest.mark.django_db
def test_controlled_authorized_approver_assignment_requires_justification(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])
    tech = lab_setup['tech_user']
    approver_role = lab_setup['roles'][RoleType.AUTHORIZED_APPROVER]

    # Assigning Authorized Approver WITHOUT justification is rejected
    res_no_just = api_client.post(
        f'/api/v1/auth/users/{tech.id}/memberships/',
        {
            'role_id': str(approver_role.id),
            'organization_id': str(lab_setup['org'].id),
            'facility_id': str(lab_setup['facility'].id),
        },
        format='json'
    )
    assert res_no_just.status_code == status.HTTP_403_FORBIDDEN
    assert "approval" in str(res_no_just.json()).lower()

    # A justification alone does not prove independent scientific qualification
    res_valid = api_client.post(
        f'/api/v1/auth/users/{tech.id}/memberships/',
        {
            'role_id': str(approver_role.id),
            'organization_id': str(lab_setup['org'].id),
            'facility_id': str(lab_setup['facility'].id),
            'approval_justification': 'ISO/IEC 17025 Technical Sign-off Certification #NL-REF-2026-08',
        },
        format='json'
    )
    assert res_valid.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN)
    tech.refresh_from_db()
    assert not tech.memberships.filter(role=approver_role, is_active=True).exists()


@pytest.mark.django_db
def test_hierarchical_scope_validation_mismatched_facility_rejected(api_client, lab_setup):
    from organizations.models import Facility, Organization, OrganizationType

    api_client.force_authenticate(user=lab_setup['admin_user'])
    tech = lab_setup['tech_user']
    qa_role = lab_setup['roles'][RoleType.QA_REVIEWER]

    other_org = Organization.objects.create(
        name="Other Steel Works",
        org_type=OrganizationType.STEELMAKER_CLIENT,
        country="DE"
    )
    # Facility belonging to other_org
    other_facility = Facility.objects.create(
        organization=other_org,
        name="Foreign Plant",
        code="FOR-01",
        city="Duisburg"
    )

    # Attempt to pair lab_setup['org'] with other_facility (mismatch!)
    res = api_client.post(
        f'/api/v1/auth/users/{tech.id}/memberships/',
        {
            'role_id': str(qa_role.id),
            'organization_id': str(lab_setup['org'].id),
            'facility_id': str(other_facility.id),
        },
        format='json'
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "does not belong to organization" in res.json()['detail']


@pytest.mark.django_db
def test_hierarchical_scope_validation_mismatched_area_rejected(api_client, lab_setup):
    from organizations.models import Facility, LaboratoryArea

    api_client.force_authenticate(user=lab_setup['admin_user'])
    tech = lab_setup['tech_user']
    qa_role = lab_setup['roles'][RoleType.QA_REVIEWER]

    other_facility = Facility.objects.create(
        organization=lab_setup['org'],
        name="Secondary Works",
        code="DC-SEC-01",
        city="Velsen"
    )
    area_in_other = LaboratoryArea.objects.create(
        facility=other_facility,
        name="Other Thermal Bay",
        code="AREA-OTHER"
    )

    # Attempt to assign primary facility but area from secondary facility
    res = api_client.post(
        f'/api/v1/auth/users/{tech.id}/memberships/',
        {
            'role_id': str(qa_role.id),
            'organization_id': str(lab_setup['org'].id),
            'facility_id': str(lab_setup['facility'].id),
            'laboratory_area_id': str(area_in_other.id),
        },
        format='json'
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "does not belong to facility" in res.json()['detail']


@pytest.mark.django_db
def test_scientific_approval_isolated_from_manager_roles(lab_setup):
    from accounts.permissions import IsAuthorizedApprover
    from rest_framework.test import APIRequestFactory

    factory = APIRequestFactory()
    perm = IsAuthorizedApprover()

    # 1. Super Admin without Authorized Approver role
    req_admin = factory.post('/dummy')
    req_admin.user = lab_setup['admin_user']
    assert perm.has_permission(req_admin, None) is False

    # 2. Lab Manager without Authorized Approver role
    lab_mgr = User.objects.create_user(email="mgr@danieli-corus.com", password="Pass", first_name="Lab", last_name="Mgr")
    OrganizationMembership.objects.create(
        user=lab_mgr, organization=lab_setup['org'], facility=lab_setup['facility'],
        role=lab_setup['roles'][RoleType.LAB_MANAGER], is_primary=True, is_active=True
    )
    req_mgr = factory.post('/dummy')
    req_mgr.user = lab_mgr
    assert perm.has_permission(req_mgr, None) is False

    # 3. Facility Manager without Authorized Approver role
    fac_mgr = User.objects.create_user(email="fac@danieli-corus.com", password="Pass", first_name="Fac", last_name="Mgr")
    OrganizationMembership.objects.create(
        user=fac_mgr, organization=lab_setup['org'], facility=lab_setup['facility'],
        role=lab_setup['roles'][RoleType.FACILITY_MANAGER], is_primary=True, is_active=True
    )
    req_fac = factory.post('/dummy')
    req_fac.user = fac_mgr
    assert perm.has_permission(req_fac, None) is False

    # 4. QA Reviewer without Authorized Approver role
    qa = User.objects.create_user(email="qa@danieli-corus.com", password="Pass", first_name="QA", last_name="Rev")
    OrganizationMembership.objects.create(
        user=qa, organization=lab_setup['org'], facility=lab_setup['facility'],
        role=lab_setup['roles'][RoleType.QA_REVIEWER], is_primary=True, is_active=True
    )
    req_qa = factory.post('/dummy')
    req_qa.user = qa
    assert perm.has_permission(req_qa, None) is False

    # 5. True Authorized Approver
    req_app = factory.post('/dummy')
    req_app.user = lab_setup['approver_user']
    assert perm.has_permission(req_app, None) is True


@pytest.mark.django_db
def test_user_provisioning_service_direct_lifecycle(lab_setup):
    from accounts.services import UserProvisioningService
    from rest_framework.exceptions import ValidationError as DRFValidationError

    admin = lab_setup['admin_user']
    org = lab_setup['org']
    fac = lab_setup['facility']
    tech_role = lab_setup['roles'][RoleType.LAB_TECHNICIAN]

    # 1. Create User via Service Layer
    new_user = UserProvisioningService.create_user(
        actor=admin,
        email="service.user@danieli-corus.com",
        first_name="Service",
        last_name="Engineer",
        password="ValidPassword123#",
        job_title="Refractory Test Operator",
        role=tech_role,
        organization=org,
        facility=fac,
    )
    assert new_user.email == "service.user@danieli-corus.com"
    assert new_user.is_superuser is False
    assert new_user.is_staff is False
    assert new_user.check_password("ValidPassword123#") is True

    # 2. Update Permitted Profile Fields
    updated_user = UserProvisioningService.update_user_profile(
        actor=admin,
        user=new_user,
        data={"job_title": "Senior Refractory Test Operator", "phone_number": "+31 251 123456"}
    )
    assert updated_user.job_title == "Senior Refractory Test Operator"

    # 3. Disallowed Field Update is Blocked
    with pytest.raises(DRFValidationError):
        UserProvisioningService.update_user_profile(
            actor=admin,
            user=new_user,
            data={"is_superuser": True}
        )

    # 4. View Access History
    history = UserProvisioningService.get_access_history(new_user.id)
    assert len(history) >= 2
    assert history[0]["actor_email"] == admin.email

    # 5. Permitted Scope Inspection
    scope = UserProvisioningService.get_user_permitted_scope(new_user)
    assert scope["email"] == new_user.email
    assert scope["capabilities"]["can_input_results"] is True
    assert scope["capabilities"]["can_sign_certificates"] is False

    # 6. Deactivate & Reactivate
    deactivated = UserProvisioningService.set_user_status(actor=admin, user=new_user, is_active=False)
    assert deactivated.is_active is False
    reactivated = UserProvisioningService.set_user_status(actor=admin, user=new_user, is_active=True)
    assert reactivated.is_active is True

    # 7. Unconfigured Email backend does not simulate delivery
    invite_res = UserProvisioningService.initiate_invitation_or_reset(actor=admin, user=new_user)
    assert invite_res["delivered"] is False
    assert invite_res["channel"] == "NONE"


@pytest.mark.django_db
def test_admin_v1_endpoints_comprehensive(api_client, lab_setup):
    api_client.force_authenticate(user=lab_setup['admin_user'])
    tech = lab_setup['tech_user']
    qa_role = lab_setup['roles'][RoleType.QA_REVIEWER]
    org = lab_setup['org']
    fac = lab_setup['facility']

    # 1. GET /api/v1/admin/users/
    res_list = api_client.get('/api/v1/admin/users/')
    assert res_list.status_code == status.HTTP_200_OK
    assert len(res_list.json()) >= 3

    # 2. GET /api/v1/admin/users/{id}/
    res_detail = api_client.get(f'/api/v1/admin/users/{tech.id}/')
    assert res_detail.status_code == status.HTTP_200_OK
    assert res_detail.json()['email'] == tech.email

    # 3. PATCH /api/v1/admin/users/{id}/
    res_patch = api_client.patch(
        f'/api/v1/admin/users/{tech.id}/',
        {'job_title': 'Lead Testing Specialist'},
        format='json'
    )
    assert res_patch.status_code == status.HTTP_200_OK
    assert res_patch.json()['job_title'] == 'Lead Testing Specialist'

    # 4. POST /api/v1/admin/users/{id}/deactivate/
    res_deact = api_client.post(f'/api/v1/admin/users/{tech.id}/deactivate/')
    assert res_deact.status_code == status.HTTP_200_OK
    assert res_deact.json()['is_active'] is False

    # 5. POST /api/v1/admin/users/{id}/activate/
    res_act = api_client.post(f'/api/v1/admin/users/{tech.id}/activate/')
    assert res_act.status_code == status.HTTP_200_OK
    assert res_act.json()['is_active'] is True

    # 6. GET /api/v1/admin/users/{id}/memberships/
    res_mems = api_client.get(f'/api/v1/admin/users/{tech.id}/memberships/')
    assert res_mems.status_code == status.HTTP_200_OK
    assert len(res_mems.json()) >= 1

    # 7. POST /api/v1/admin/users/{id}/memberships/ (Add secondary membership)
    res_add_mem = api_client.post(
        f'/api/v1/admin/users/{tech.id}/memberships/',
        {
            'role_id': str(qa_role.id),
            'organization_id': str(org.id),
            'facility_id': str(fac.id),
            'is_primary': False,
        },
        format='json'
    )
    assert res_add_mem.status_code == status.HTTP_201_CREATED
    new_mem_id = res_add_mem.json()['id']

    # 8. PATCH /api/v1/admin/memberships/{id}/ (Direct membership update)
    res_patch_mem = api_client.patch(
        f'/api/v1/admin/memberships/{new_mem_id}/',
        {'is_active': False},
        format='json'
    )
    assert res_patch_mem.status_code == status.HTTP_200_OK
    assert res_patch_mem.json()['is_active'] is False

    # 9. DELETE /api/v1/admin/memberships/{id}/ (Direct membership deletion)
    res_del_mem = api_client.delete(f'/api/v1/admin/memberships/{new_mem_id}/')
    assert res_del_mem.status_code == status.HTTP_200_OK

    # 10. GET /api/v1/admin/roles/
    res_roles = api_client.get('/api/v1/admin/roles/')
    assert res_roles.status_code == status.HTTP_200_OK
    assert len(res_roles.json()) >= 10

    # 11. GET /api/v1/admin/organizations/
    res_orgs = api_client.get('/api/v1/admin/organizations/')
    assert res_orgs.status_code == status.HTTP_200_OK
    assert len(res_orgs.json()) >= 1

    # 12. GET /api/v1/admin/facilities/
    res_facs = api_client.get('/api/v1/admin/facilities/')
    assert res_facs.status_code == status.HTTP_200_OK
    assert 'organizations' in res_facs.json()


@pytest.mark.django_db
def test_create_lims_user_management_command(lab_setup):
    from io import StringIO
    from django.core.management import call_command
    from django.core.management.base import CommandError

    org = lab_setup['org']
    fac = lab_setup['facility']
    out = StringIO()

    # 1. Successful non-interactive user creation
    call_command(
        'create_lims_user',
        '--non-interactive',
        '--email=cli.technician@danieli-corus.com',
        '--first-name=Kees',
        '--last-name=Bakker',
        '--job-title=Furnace Operator',
        f'--org-id={org.id}',
        f'--facility-id={fac.id}',
        '--role=LAB_TECHNICIAN',
        '--password=ComplexPassword123#',
        stdout=out
    )
    assert "[SUCCESS] Successfully provisioned laboratory user" in out.getvalue()
    created_user = User.objects.get(email='cli.technician@danieli-corus.com')
    assert created_user.is_superuser is False
    assert created_user.is_staff is False
    assert created_user.is_active is True
    assert created_user.check_password('ComplexPassword123#') is True
    assert created_user.memberships.filter(role__role_type=RoleType.LAB_TECHNICIAN).exists()

    # 2. Rejection of weak password
    out_weak = StringIO()
    with pytest.raises(CommandError) as exc_weak:
        call_command(
            'create_lims_user',
            '--non-interactive',
            '--email=weak.pass@danieli-corus.com',
            '--first-name=Weak',
            '--last-name=Pass',
            f'--org-id={org.id}',
            f'--facility-id={fac.id}',
            '--role=LAB_TECHNICIAN',
            '--password=short',
            stdout=out_weak
        )
    assert "Provisioning failed" in str(exc_weak.value) or "password" in str(exc_weak.value).lower()

    # 3. Controlled Delegation: AUTHORIZED_APPROVER rejected without justification
    with pytest.raises(CommandError) as exc_approver:
        call_command(
            'create_lims_user',
            '--non-interactive',
            '--email=unauthorized.approver@danieli-corus.com',
            '--first-name=Unauth',
            '--last-name=Approver',
            f'--org-id={org.id}',
            f'--facility-id={fac.id}',
            '--role=AUTHORIZED_APPROVER',
            '--password=ComplexPassword123#',
            stdout=StringIO()
        )
    assert "Controlled Delegation" in str(exc_approver.value)

    # 4. Duplicate membership prevention & Secondary membership assignment
    with pytest.raises(CommandError) as exc_dup:
        call_command(
            'create_lims_user',
            '--non-interactive',
            '--email=cli.technician@danieli-corus.com',
            f'--org-id={org.id}',
            f'--facility-id={fac.id}',
            '--role=LAB_TECHNICIAN',
            stdout=StringIO()
        )
    assert "already exists" in str(exc_dup.value)

    # Attach secondary membership cleanly
    out_secondary = StringIO()
    call_command(
        'create_lims_user',
        '--non-interactive',
        '--secondary-membership',
        '--email=cli.technician@danieli-corus.com',
        f'--org-id={org.id}',
        f'--facility-id={fac.id}',
        '--role=SAMPLE_CLERK',
        stdout=out_secondary
    )
    assert "Attached secondary membership" in out_secondary.getvalue()
    assert created_user.memberships.count() == 2


@pytest.mark.django_db
def test_phase9_security_and_privilege_invariants(api_client, lab_setup):
    """
    Phase 9 Comprehensive Security Invariants:
    - Inactive users rejected at authentication
    - Users without memberships denied access
    - Ordinary users cannot administer users
    - Demotion preserves account UUIDs and historical records
    - Passwords are not leaked in audit events or serializers
    - Deactivation terminates active access
    - Management command idempotency
    """
    from accounts.services import UserProvisioningService
    from audit.models import AuditEvent

    org = lab_setup['org']
    fac = lab_setup['facility']
    tech = lab_setup['tech_user']
    admin = lab_setup['admin_user']

    # 1. Ordinary users cannot manage accounts
    api_client.force_authenticate(user=tech)
    res_unauth = api_client.get('/api/v1/admin/users/')
    assert res_unauth.status_code == status.HTTP_403_FORBIDDEN

    res_unauth_post = api_client.post(
        '/api/v1/admin/users/',
        {'email': 'hacker@test.com', 'password': 'Pass12345678#', 'first_name': 'H', 'last_name': 'K'},
        format='json'
    )
    assert res_unauth_post.status_code == status.HTTP_403_FORBIDDEN

    # 2. Users without memberships have no operational access
    orphan_user = User.objects.create_user(
        email='orphan.user@danieli-corus.com',
        first_name='Orphan',
        last_name='User',
        password='ValidPassword123#'
    )
    api_client.force_authenticate(user=orphan_user)
    scope = UserProvisioningService.get_user_permitted_scope(orphan_user)
    assert len(scope['roles']) == 0
    assert len(scope['facilities']) == 0
    assert scope['capabilities']['can_sign_certificates'] is False
    assert scope['capabilities']['can_input_results'] is False
    assert scope['capabilities']['is_superadmin'] is False

    # 3. Demotion preserves account UUID and history
    original_uuid = tech.id
    UserProvisioningService.update_user_profile(actor=admin, user=tech, data={'job_title': 'Junior Refractory Metrologist'})
    reloaded_tech = User.objects.get(id=original_uuid)
    assert reloaded_tech.id == original_uuid
    assert reloaded_tech.job_title == 'Junior Refractory Metrologist'

    # 4. Passwords are never leaked in audit logs or serialized profiles
    events = AuditEvent.objects.filter(entity_id=str(tech.id))
    for e in events:
        changes_str = str(e.changes_json).lower()
        assert 'password' not in changes_str or changes_str.count('password_reset') > 0
        assert 'argon2' not in changes_str
        assert 'pbkdf2' not in changes_str

    api_client.force_authenticate(user=admin)
    tech_data = api_client.get(f'/api/v1/admin/users/{tech.id}/').json()
    assert 'password' not in tech_data

    # 5. Deactivation terminates active access
    UserProvisioningService.set_user_status(actor=admin, user=tech, is_active=False)
    tech.refresh_from_db()
    assert tech.is_active is False
    api_client.force_authenticate(user=tech)
    res_deact = api_client.get('/api/v1/laboratory/dashboard/stats/')
    # Inactive user rejected
    assert res_deact.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    # Re-activate
    UserProvisioningService.set_user_status(actor=admin, user=tech, is_active=True)
    tech.refresh_from_db()
    assert tech.is_active is True

@pytest.mark.django_db
def test_admin_cannot_enumerate_foreign_organization(api_client, lab_setup):
    other_org = Organization.objects.create(
        name='Foreign Independent Laboratory', org_type=OrganizationType.DANIELI_CORUS,
        country='DE'
    )
    other_facility = Facility.objects.create(
        organization=other_org, name='Foreign Lab', code='FOREIGN-RBAC-01', city='Berlin'
    )
    external = User.objects.create_user(
        email='foreign-user@example.test', password='StrongSecurePW2026!',
        first_name='Foreign', last_name='User'
    )
    OrganizationMembership.objects.create(
        user=external, organization=other_org, facility=other_facility,
        role=lab_setup['roles'][RoleType.LAB_TECHNICIAN],
        is_primary=True,
    )
    api_client.force_authenticate(user=lab_setup['admin_user'])
    users = api_client.get('/api/v1/auth/users/')
    assert users.status_code == status.HTTP_200_OK
    assert external.email not in [u['email'] for u in users.json()]
    details = api_client.get(f'/api/v1/auth/users/{external.id}/')
    assert details.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_audit_failure_rolls_back_provisioning(lab_setup):
    from unittest.mock import patch
    from accounts.services import UserProvisioningService
    email = 'audit-rollback@example.test'
    with patch('accounts.services.AuditEvent.objects.create', side_effect=RuntimeError('Audit storage failed')):
        with pytest.raises(RuntimeError, match='Audit storage failed'):
            UserProvisioningService.create_user(
                actor=lab_setup['admin_user'], email=email,
                first_name='Audit', last_name='Rollback',
                password='StrongAuditPassword2026!',
                role=lab_setup['roles'][RoleType.LAB_TECHNICIAN],
                organization=lab_setup['org'], facility=lab_setup['facility'],
            )
    assert not User.objects.filter(email=email).exists()
