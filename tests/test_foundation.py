import pytest
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User, Role, RoleType, OrganizationMembership
from organizations.models import Organization, OrganizationType, Facility, LaboratoryArea


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_health_check_endpoint(api_client):
    """
    Ensure the health check API returns 200 OK and reports healthy database.
    """
    response = api_client.get('/api/v1/health/')
    assert response.status_code == status.HTTP_200_OK
    assert response.data['status'] == 'ok'
    assert response.data['database'] == 'healthy'
    assert 'Danieli Corus' in response.data['service']


@pytest.mark.django_db
def test_openapi_schema_endpoint(api_client):
    """
    Ensure Swagger OpenAPI schema generation functions properly.
    """
    response = api_client.get('/api/v1/schema/')
    assert response.status_code == status.HTTP_200_OK
    assert 'openapi' in response.data or 'info' in response.data


@pytest.mark.django_db
def test_custom_user_creation():
    """
    Ensure custom user creation works with UUID and email without username field.
    """
    user = User.objects.create_user(
        email='m.vanderbeek@danieli-corus.com',
        first_name='Michiel',
        last_name='van der Beek',
        job_title='Lead Refractory Metallurgist'
    )
    assert user.id is not None
    assert user.email == 'm.vanderbeek@danieli-corus.com'
    assert not hasattr(user, 'username') or user.username is None


@pytest.mark.django_db
def test_organization_and_membership_relationship():
    """
    Ensure users can be securely assigned roles via OrganizationMembership.
    """
    org = Organization.objects.create(
        name='Danieli Corus B.V. IJmuiden',
        org_type=OrganizationType.DANIELI_CORUS,
        country='NL',
        accreditation_number='ISO/IEC 17025:2017 RvA L-184'
    )
    facility = Facility.objects.create(
        organization=org,
        name='Refractory Testing Technology Centre',
        code='DC-IJM-LAB',
        city='Velsen-Noord',
        is_primary=True
    )
    area = LaboratoryArea.objects.create(
        facility=facility,
        code='FURN-BAY-A',
        name='High-Temperature Dilatometry & Firing Bay'
    )
    role, _ = Role.objects.get_or_create(
        role_type=RoleType.AUTHORIZED_APPROVER,
        defaults={
            'name': 'Authorized Approver',
            'can_sign_certificates': True,
            'can_verify_results': True
        }
    )
    user = User.objects.create_user(
        email='metallurgist@danieli-corus.com',
        first_name='Senior',
        last_name='Scientist'
    )
    membership = OrganizationMembership.objects.create(
        user=user,
        organization=org,
        facility=facility,
        role=role,
        is_primary=True
    )

    assert membership.id is not None
    assert membership.role.can_sign_certificates is True
    assert area.facility == facility
