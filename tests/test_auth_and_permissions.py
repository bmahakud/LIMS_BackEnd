import pytest
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User, Role, RoleType, OrganizationMembership
from organizations.models import Organization, OrganizationType, Facility
from communications.models import Inquiry


@pytest.fixture
def api_client():
    client = APIClient(enforce_csrf_checks=True)
    return client


@pytest.fixture
def approver_role(db):
    role, _ = Role.objects.get_or_create(
        role_type=RoleType.AUTHORIZED_APPROVER,
        defaults={
            'name': 'Authorized Approver',
            'can_sign_certificates': True,
            'can_verify_results': True
        }
    )
    return role


@pytest.fixture
def superadmin_role(db):
    role, _ = Role.objects.get_or_create(
        role_type=RoleType.SUPER_ADMIN,
        defaults={
            'name': 'Super Admin',
            'can_manage_facility': True
        }
    )
    return role


@pytest.fixture
def auth_user(db, approver_role):
    user = User.objects.create_user(
        email='lead.approver@danieli-corus.com',
        password='StrongPassword123!',
        first_name='Dr. Elena',
        last_name='Rostova',
        job_title='QA Director'
    )
    org = Organization.objects.create(
        name='Danieli Corus IJmuiden',
        org_type=OrganizationType.DANIELI_CORUS,
        country='NL'
    )
    facility = Facility.objects.create(
        organization=org,
        name='Refractory Testing Lab',
        code='DC-LAB-01',
        city='Velsen-Noord'
    )
    OrganizationMembership.objects.create(
        user=user,
        organization=org,
        facility=facility,
        role=approver_role,
        is_primary=True
    )
    return user


@pytest.fixture
def superadmin_user(db, superadmin_role):
    user = User.objects.create_superuser(
        email='sysadmin@danieli-corus.com',
        password='AdminPassword123!',
        first_name='System',
        last_name='Administrator'
    )
    org = Organization.objects.create(
        name='Danieli Corus IT Global',
        org_type=OrganizationType.DANIELI_CORUS,
        country='NL'
    )
    OrganizationMembership.objects.create(
        user=user,
        organization=org,
        role=superadmin_role,
        is_primary=True
    )
    return user


@pytest.mark.django_db
def test_csrf_cookie_endpoint(api_client):
    response = api_client.get('/api/v1/auth/csrf/')
    assert response.status_code == status.HTTP_200_OK
    assert 'csrfToken' in response.data
    assert 'csrftoken' in response.cookies


@pytest.mark.django_db
def test_login_successful_and_me_profile(api_client, auth_user):
    # 1. Fetch CSRF token
    csrf_res = api_client.get('/api/v1/auth/csrf/')
    csrf_token = csrf_res.data['csrfToken']

    # 2. Login
    login_res = api_client.post(
        '/api/v1/auth/login/',
        {'email': 'lead.approver@danieli-corus.com', 'password': 'StrongPassword123!'},
        HTTP_X_CSRFTOKEN=csrf_token
    )
    assert login_res.status_code == status.HTTP_200_OK
    assert login_res.data['email'] == 'lead.approver@danieli-corus.com'
    assert len(login_res.data['memberships']) == 1
    assert login_res.data['memberships'][0]['role']['role_type'] == 'AUTHORIZED_APPROVER'
    assert 'dc_lims_sessionid' in api_client.cookies

    # Use rotated post-login CSRF token
    post_login_csrf = login_res.data['csrfToken']

    # 3. Verify /me endpoint
    me_res = api_client.get('/api/v1/auth/me/')
    assert me_res.status_code == status.HTTP_200_OK
    assert me_res.data['email'] == 'lead.approver@danieli-corus.com'

    # 4. Logout using rotated token
    logout_res = api_client.post('/api/v1/auth/logout/', HTTP_X_CSRFTOKEN=post_login_csrf)
    assert logout_res.status_code == status.HTTP_200_OK

    # 5. Verify /me is now forbidden
    me_after_logout = api_client.get('/api/v1/auth/me/')
    assert me_after_logout.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_login_invalid_credentials_returns_generic_error(api_client, auth_user):
    csrf_res = api_client.get('/api/v1/auth/csrf/')
    csrf_token = csrf_res.data['csrfToken']

    # Wrong password
    bad_res = api_client.post(
        '/api/v1/auth/login/',
        {'email': 'lead.approver@danieli-corus.com', 'password': 'WrongPassword!'},
        HTTP_X_CSRFTOKEN=csrf_token
    )
    assert bad_res.status_code == status.HTTP_401_UNAUTHORIZED
    assert bad_res.data['detail'] == 'Invalid email or password.'

    # Non-existent user
    non_existent = api_client.post(
        '/api/v1/auth/login/',
        {'email': 'unknown@danieli-corus.com', 'password': 'SomePassword!'},
        HTTP_X_CSRFTOKEN=csrf_token
    )
    assert non_existent.status_code == status.HTTP_401_UNAUTHORIZED
    assert non_existent.data['detail'] == 'Invalid email or password.'


@pytest.mark.django_db
def test_inactive_user_rejected(api_client, auth_user):
    auth_user.is_active = False
    auth_user.save()

    csrf_res = api_client.get('/api/v1/auth/csrf/')
    csrf_token = csrf_res.data['csrfToken']

    res = api_client.post(
        '/api/v1/auth/login/',
        {'email': 'lead.approver@danieli-corus.com', 'password': 'StrongPassword123!'},
        HTTP_X_CSRFTOKEN=csrf_token
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert 'inactive' in res.data['detail'].lower()


@pytest.mark.django_db
def test_csrf_failure_on_unsafe_post(api_client, auth_user):
    # Attempt login without CSRF token
    res = api_client.post(
        '/api/v1/auth/login/',
        {'email': 'lead.approver@danieli-corus.com', 'password': 'StrongPassword123!'}
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_superadmin_cannot_approve_scientific_certificates(superadmin_user, auth_user):
    from accounts.permissions import IsAuthorizedApprover
    from types import SimpleNamespace

    perm = IsAuthorizedApprover()

    # SuperAdmin request
    req_admin = SimpleNamespace(user=superadmin_user)
    assert perm.has_permission(req_admin, None) is False

    # Authorized Approver request
    req_approver = SimpleNamespace(user=auth_user)
    assert perm.has_permission(req_approver, None) is True


@pytest.mark.django_db
def test_public_inquiry_submission(api_client):
    res = api_client.post(
        '/api/v1/communications/inquiries/',
        {
            'name': 'Hans Mulder',
            'organization': 'Tata Steel IJmuiden',
            'email': 'h.mulder@tatasteel.com',
            'phone': '+31 251 491111',
            'sampleType': 'Dense Mullite Bricks',
            'timeline': 'Within 2 weeks',
            'message': 'Need R-01 creep in compression tests for BF-7 relining.',
            'testRequirements': ['Creep in Compression', 'Cold Crushing Strength']
        }
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert Inquiry.objects.filter(email='h.mulder@tatasteel.com').exists()
