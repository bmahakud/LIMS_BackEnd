import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from accounts.models import User, Role, RoleType, OrganizationMembership
from organizations.models import Organization, OrganizationType, Facility
from projects.models import Client, Vendor, Project, Material, MaterialLot, MaterialType
from test_catalogue.models import TestDefinition, TestCategory, TestMethod
from laboratory.models import Laboratory, Instrument
from samples.models import Sample, SampleStatus, PackagingCondition, Specimen, SpecimenStatus
from samples.services import SampleLifecycleService
from work_orders.models import WorkOrder, TestAssignment, WorkOrderStatus


@pytest.fixture
def api_client():
    client = APIClient(enforce_csrf_checks=False)
    return client


@pytest.fixture
def setup_lab_infrastructure(db):
    org = Organization.objects.create(name='Danieli Corus B.V. IJmuiden', org_type=OrganizationType.DANIELI_CORUS, country='NL')
    facility = Facility.objects.create(organization=org, name='Refractory Testing Centre', code='DC-IJM-01', city='Velsen-Noord')
    lab = Laboratory.objects.create(facility=facility, name='High-Temperature Laboratory')
    
    # Instruments
    furnace = Instrument.objects.create(
        asset_tag='EQ-FURN-01', name='High-Temp Dilatometer Furnace',
        laboratory=lab, manufacturer='Netzsch', model_number='RUL 421E',
        serial_number='SN-FURN-8921', max_temperature_c=1700
    )

    # Client & Vendor
    client_org = Organization.objects.create(name='Tata Steel Europe', org_type=OrganizationType.STEELMAKER_CLIENT, country='NL')
    client = Client.objects.create(organization=client_org, contact_person='Dr. Jan de Vries', contact_email='j.devries@tatasteel.com')
    
    vendor_org = Organization.objects.create(name='RHI Magnesita', org_type=OrganizationType.REFRACTORY_MANUFACTURER, country='AT')
    vendor = Vendor.objects.create(organization=vendor_org, vendor_code='VEND-RHIMAG-01')

    # Project & Lot
    project = Project.objects.create(code='BF6-RELINING-2026', name='Tata Steel IJmuiden BF-6 Campaign', client=client, plant_asset='Blast Furnace 6', start_date='2026-01-15')
    material = Material.objects.create(name='Mullite-Bonded Corundum Brick', code='MAT-MBC-01', category=MaterialType.SHAPED_DENSE, nominal_al2o3_pct=76.5)
    lot = MaterialLot.objects.create(lot_number='Lot #P004934-M2', project=project, material=material, vendor=vendor, quantity_units=5000)

    # User & Role
    clerk_role, _ = Role.objects.get_or_create(role_type=RoleType.SAMPLE_CLERK, defaults={'name': 'Sample Clerk', 'can_manage_samples': True})
    user = User.objects.create_user(email='clerk@danieli-corus.com', password='Password123!', first_name='Rajiv', last_name='Sharma')
    OrganizationMembership.objects.create(user=user, organization=org, facility=facility, role=clerk_role, is_primary=True)

    # Create TestDefinition and TestMethod for RUL
    rul_def, _ = TestDefinition.objects.get_or_create(
        code=TestCategory.RUL,
        defaults={'name': 'Refractoriness Under Load (RUL)', 'discipline': 'THERMAL', 'default_unit': '°C'}
    )
    rul_method, _ = TestMethod.objects.get_or_create(
        test_definition=rul_def,
        standard_code='ISO 1893',
        applicable_product_category='Dense Shaped',
        defaults={'title': 'RUL Differential', 'organization': 'ISO'}
    )

    return {
        'org': org, 'facility': facility, 'lab': lab, 'furnace': furnace,
        'client': client, 'vendor': vendor, 'project': project,
        'material': material, 'lot': lot, 'user': user,
        'rul_def': rul_def, 'rul_method': rul_method
    }


@pytest.mark.django_db
def test_sample_creation_and_unique_constraint(setup_lab_infrastructure):
    infra = setup_lab_infrastructure
    sample = Sample.objects.create(
        sample_code='DC-SMP-2026-0001',
        material_lot=infra['lot'],
        current_facility=infra['facility'],
        quantity_bricks=10,
        sampling_date='2026-01-20',
        sampled_by='Rajiv Sharma'
    )
    assert sample.status == SampleStatus.REGISTERED

    # Duplicate code must fail integrity constraint
    with pytest.raises(IntegrityError):
        Sample.objects.create(
            sample_code='DC-SMP-2026-0001',
            material_lot=infra['lot'],
            current_facility=infra['facility'],
            quantity_bricks=5,
            sampling_date='2026-01-20',
            sampled_by='Other'
        )


@pytest.mark.django_db
def test_sample_intake_receipt_acknowledgement(setup_lab_infrastructure):
    infra = setup_lab_infrastructure
    sample = Sample.objects.create(
        sample_code='DC-SMP-2026-0002',
        material_lot=infra['lot'],
        current_facility=infra['facility'],
        quantity_bricks=10,
        sampling_date='2026-01-20',
        sampled_by='Rajiv Sharma'
    )

    receipt = SampleLifecycleService.record_receipt(
        sample=sample,
        user=infra['user'],
        packaging_condition=PackagingCondition.INTACT,
        moisture_barrier_intact=True,
        heat_numbers_verified=True
    )

    assert receipt.is_accepted is True
    assert sample.status == SampleStatus.RECEIVED


@pytest.mark.django_db
def test_sample_intake_damaged_holds_lot(setup_lab_infrastructure):
    infra = setup_lab_infrastructure
    sample = Sample.objects.create(
        sample_code='DC-SMP-2026-0003',
        material_lot=infra['lot'],
        current_facility=infra['facility'],
        quantity_bricks=10,
        sampling_date='2026-01-20',
        sampled_by='Rajiv Sharma'
    )

    receipt = SampleLifecycleService.record_receipt(
        sample=sample,
        user=infra['user'],
        packaging_condition=PackagingCondition.DAMAGED_MOISTURE,
        moisture_barrier_intact=False,
        heat_numbers_verified=True,
        remarks='Moisture barrier punctured during ocean transit; brick corner fractured.'
    )

    assert receipt.is_accepted is False
    assert sample.status == SampleStatus.HELD_DAMAGED


@pytest.mark.django_db
def test_child_specimen_genealogy_and_cutting(setup_lab_infrastructure):
    infra = setup_lab_infrastructure
    sample = Sample.objects.create(
        sample_code='DC-SMP-2026-0004',
        material_lot=infra['lot'],
        current_facility=infra['facility'],
        quantity_bricks=10,
        sampling_date='2026-01-20',
        sampled_by='Rajiv Sharma',
        status=SampleStatus.RECEIVED
    )

    specimens = SampleLifecycleService.prepare_child_specimens(
        sample=sample,
        count=3,
        geometry='Cylinder 50mm dia x 50mm h',
        dimensions={'length': 50.0, 'width': 50.0, 'height': 50.0}
    )

    assert len(specimens) == 3
    assert specimens[0].specimen_code == 'DC-SMP-2026-0004-SP01'
    assert specimens[1].specimen_code == 'DC-SMP-2026-0004-SP02'
    assert specimens[2].specimen_code == 'DC-SMP-2026-0004-SP03'
    assert sample.status == SampleStatus.PREPARATION


@pytest.mark.django_db
def test_invalid_lifecycle_transition_fails(setup_lab_infrastructure):
    infra = setup_lab_infrastructure
    sample = Sample.objects.create(
        sample_code='DC-SMP-2026-0005',
        material_lot=infra['lot'],
        current_facility=infra['facility'],
        quantity_bricks=10,
        sampling_date='2026-01-20',
        sampled_by='Rajiv Sharma',
        status=SampleStatus.REGISTERED
    )

    # Cannot jump directly from REGISTERED to REPORT_ISSUED
    with pytest.raises(ValidationError):
        SampleLifecycleService.advance_status(sample, SampleStatus.REPORT_ISSUED)


@pytest.mark.django_db
def test_work_order_and_test_assignment(setup_lab_infrastructure):
    infra = setup_lab_infrastructure
    sample = Sample.objects.create(
        sample_code='DC-SMP-2026-0006',
        material_lot=infra['lot'],
        current_facility=infra['facility'],
        quantity_bricks=10,
        sampling_date='2026-01-20',
        sampled_by='Rajiv Sharma',
        status=SampleStatus.RECEIVED
    )
    specimens = SampleLifecycleService.prepare_child_specimens(sample=sample, count=1, geometry='Cylinder 50mm dia')
    specimen = specimens[0]

    wo = WorkOrder.objects.create(
        order_number='WO-2026-001',
        laboratory=infra['lab'],
        created_by=infra['user'],
        target_completion_date='2026-02-15'
    )

    assignment = TestAssignment.objects.create(
        work_order=wo,
        specimen=specimen,
        test_method=infra['rul_method'],
        instrument=infra['furnace'],
        assigned_technician=infra['user'],
        test_temperature_c=1680,
        applied_load_mpa=0.200
    )

    assert assignment.id is not None
    assert assignment.test_temperature_c == 1680
    assert assignment.work_order.order_number == 'WO-2026-001'
