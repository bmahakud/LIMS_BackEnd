import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from accounts.models import User, Role, RoleType, OrganizationMembership
from organizations.models import Organization, OrganizationType, Facility
from projects.models import Client, Vendor, Project, Material, MaterialLot, MaterialType
from test_catalogue.models import TestDefinition, TestCategory, TestMethod, SpecificationSet, SpecificationLimit
from laboratory.models import Laboratory, Instrument
from samples.models import Sample, SampleStatus, Specimen
from work_orders.models import WorkOrder, TestAssignment
from results.models import TestRun, Result, ComparisonQualifier, VerificationStatus
from results.services import CalculationRegistry
from quality.models import SpecificationEvaluationStatus, FinalDecisionOutcome
from quality.services import SpecificationService
from reports.services import ReportingService


@pytest.fixture
def qa_lab_setup(db):
    org = Organization.objects.create(name='Danieli Corus B.V. IJmuiden', org_type=OrganizationType.DANIELI_CORUS, country='NL')
    facility = Facility.objects.create(organization=org, name='Refractory Testing Centre', code='DC-IJM-01', city='Velsen-Noord')
    lab = Laboratory.objects.create(facility=facility, name='High-Temperature Laboratory')
    furnace = Instrument.objects.create(asset_tag='EQ-FURN-01', name='High-Temp Furnace', laboratory=lab, manufacturer='Netzsch', model_number='421E', serial_number='SN-001', max_temperature_c=1700)

    # Users
    approver_role, _ = Role.objects.get_or_create(role_type=RoleType.AUTHORIZED_APPROVER, defaults={'name': 'Approver', 'can_sign_certificates': True, 'can_verify_results': True})
    tech_role, _ = Role.objects.get_or_create(role_type=RoleType.LAB_TECHNICIAN, defaults={'name': 'Technician', 'can_input_results': True})

    approver = User.objects.create_user(email='approver@danieli-corus.com', password='Password123!', first_name='Elena', last_name='Rostova')
    tech = User.objects.create_user(email='tech@danieli-corus.com', password='Password123!', first_name='Rajiv', last_name='Sharma')
    unauth_user = User.objects.create_user(email='unauth@danieli-corus.com', password='Password123!', first_name='Unauth', last_name='User')

    OrganizationMembership.objects.create(user=approver, organization=org, facility=facility, role=approver_role, is_primary=True)
    OrganizationMembership.objects.create(user=tech, organization=org, facility=facility, role=tech_role, is_primary=True)

    # Project, Lot, Sample
    client_org = Organization.objects.create(name='Tata Steel', org_type=OrganizationType.STEELMAKER_CLIENT, country='NL')
    client = Client.objects.create(organization=client_org)
    vendor_org = Organization.objects.create(name='RHI Magnesita', org_type=OrganizationType.REFRACTORY_MANUFACTURER, country='AT')
    vendor = Vendor.objects.create(organization=vendor_org, vendor_code='VEND-RHI')

    project = Project.objects.create(code='BF6-2026', name='BF-6 Campaign', client=client, plant_asset='BF6', start_date='2026-01-01')
    material = Material.objects.create(name='Mullite-Bonded Corundum', code='MAT-MBC', category=MaterialType.SHAPED_DENSE)
    lot = MaterialLot.objects.create(lot_number='Lot #P004934-M2', project=project, material=material, vendor=vendor, quantity_units=1000)
    sample = Sample.objects.create(sample_code='DC-SMP-2026-0842', material_lot=lot, current_facility=facility, quantity_bricks=10, sampling_date='2026-01-15', sampled_by='Rajiv', status=SampleStatus.RECEIVED)
    specimen = Specimen.objects.create(specimen_code='DC-SMP-2026-0842-SP01', parent_sample=sample, sub_index=1, geometry='Cylinder 50x50mm')

    # Test Definition, Method & Specifications
    ccs_def, _ = TestDefinition.objects.get_or_create(code=TestCategory.CCS, defaults={'name': 'Cold Crushing Strength', 'discipline': 'MECHANICAL', 'default_unit': 'MPa'})
    ccs_method, _ = TestMethod.objects.get_or_create(test_definition=ccs_def, standard_code='ISO 10059-1', applicable_product_category='Dense Shaped', defaults={'title': 'CCS', 'organization': 'ISO'})
    
    spec_set, _ = SpecificationSet.objects.get_or_create(code='DC-SPEC R-01', defaults={'title': 'Acceptance Spec', 'revision': 'Rev 4.2'})
    ccs_limit, _ = SpecificationLimit.objects.get_or_create(specification_set=spec_set, test_definition=ccs_def, material_grade='Mullite-Bonded Corundum', defaults={'min_value': Decimal('85.0'), 'unit': 'MPa', 'is_critical': True})

    # Assignment & Run
    wo = WorkOrder.objects.create(order_number='WO-2026-999', laboratory=lab, created_by=approver, target_completion_date='2026-02-01')
    assignment = TestAssignment.objects.create(work_order=wo, specimen=specimen, test_method=ccs_method, instrument=furnace, assigned_technician=tech)
    test_run = TestRun.objects.create(assignment=assignment, technician=tech, instrument=furnace, started_at='2026-01-20T10:00:00Z')

    return {
        'org': org, 'facility': facility, 'approver': approver, 'tech': tech, 'unauth_user': unauth_user,
        'sample': sample, 'specimen': specimen, 'ccs_def': ccs_def, 'ccs_method': ccs_method,
        'spec_set': spec_set, 'ccs_limit': ccs_limit, 'assignment': assignment, 'test_run': test_run
    }


@pytest.mark.django_db
def test_calculation_registry_parsing_and_decimal_precision():
    # Never treats '>1600' as exact 1600
    num, qual = CalculationRegistry.parse_qualified_input('>1680.5')
    assert num == Decimal('1680.5')
    assert qual == ComparisonQualifier.GREATER_THAN

    num_lt, qual_lt = CalculationRegistry.parse_qualified_input('<0.05')
    assert num_lt == Decimal('0.05')
    assert qual_lt == ComparisonQualifier.LESS_THAN

    # Exact decimal
    num_ex, qual_ex = CalculationRegistry.parse_qualified_input('108.40')
    assert num_ex == Decimal('108.40')
    assert qual_ex == ComparisonQualifier.NONE

    # Verified CCS formula
    ccs = CalculationRegistry.calculate_cold_crushing_strength(
        peak_load_n=Decimal('212800.0'),
        area_mm2=Decimal('1963.5')
    )
    assert ccs == Decimal('108.4')


@pytest.mark.django_db
def test_specification_evaluation_service(qa_lab_setup):
    setup = qa_lab_setup

    # Case 1: Conforming result (108.4 MPa >= 85.0 MPa) -> PASS
    res_pass = Result(
        test_run=setup['test_run'], test_method=setup['ccs_method'],
        parameter_code='CCS', raw_input_text='108.4',
        numeric_value=Decimal('108.4'), qualifier=ComparisonQualifier.NONE,
        unit='MPa', technician=setup['tech']
    )
    status_p, delta, _ = SpecificationService.evaluate_result(res_pass, setup['ccs_limit'])
    assert status_p == SpecificationEvaluationStatus.PASS

    # Case 2: Non-conforming result (72.0 MPa < 85.0 MPa) -> DEVIATION
    res_fail = Result(
        test_run=setup['test_run'], test_method=setup['ccs_method'],
        parameter_code='CCS', raw_input_text='72.0',
        numeric_value=Decimal('72.0'), qualifier=ComparisonQualifier.NONE,
        unit='MPa', technician=setup['tech']
    )
    status_f, delta_f, _ = SpecificationService.evaluate_result(res_fail, setup['ccs_limit'])
    assert status_f == SpecificationEvaluationStatus.DEVIATION

    # Case 3: Ambiguous qualified observation (>70 MPa against min 85 MPa) -> INDETERMINATE
    res_indet = Result(
        test_run=setup['test_run'], test_method=setup['ccs_method'],
        parameter_code='CCS', raw_input_text='>70',
        numeric_value=Decimal('70.0'), qualifier=ComparisonQualifier.GREATER_THAN,
        unit='MPa', technician=setup['tech']
    )
    status_i, _, _ = SpecificationService.evaluate_result(res_indet, setup['ccs_limit'])
    assert status_i == SpecificationEvaluationStatus.INDETERMINATE


@pytest.mark.django_db
def test_report_issuance_blocked_on_unverified_results(qa_lab_setup):
    setup = qa_lab_setup
    sample = setup['sample']

    # Record unverified result
    Result.objects.create(
        test_run=setup['test_run'], test_method=setup['ccs_method'],
        parameter_code='CCS', raw_input_text='108.4',
        numeric_value=Decimal('108.4'), unit='MPa',
        technician=setup['tech'], verification_status=VerificationStatus.UNVERIFIED
    )

    # Attempting report issuance must raise ValidationError
    with pytest.raises(ValidationError) as exc:
        ReportingService.issue_laboratory_report(
            sample=sample,
            approver=setup['approver'],
            outcome=FinalDecisionOutcome.ACCORDING_TO_SPEC,
            decision_notes='Approved for relining installation.',
            specification_set=setup['spec_set']
        )
    assert 'not been verified' in str(exc.value)


@pytest.mark.django_db
def test_unauthorized_qa_decision_rejected(qa_lab_setup):
    setup = qa_lab_setup
    sample = setup['sample']

    Result.objects.create(
        test_run=setup['test_run'], test_method=setup['ccs_method'],
        parameter_code='CCS', raw_input_text='108.4',
        numeric_value=Decimal('108.4'), unit='MPa',
        technician=setup['tech'], verification_status=VerificationStatus.VERIFIED
    )

    # Unauthorized user attempting to finalize report
    with pytest.raises(ValidationError) as exc:
        ReportingService.issue_laboratory_report(
            sample=sample,
            approver=setup['unauth_user'],
            outcome=FinalDecisionOutcome.ACCORDING_TO_SPEC,
            decision_notes='Should fail due to permissions.',
            specification_set=setup['spec_set']
        )
    assert 'Unauthorized' in str(exc.value)


@pytest.mark.django_db
def test_report_issuance_and_pdf_generation(qa_lab_setup):
    setup = qa_lab_setup
    sample = setup['sample']

    Result.objects.create(
        test_run=setup['test_run'], test_method=setup['ccs_method'],
        parameter_code='CCS', raw_input_text='108.4',
        numeric_value=Decimal('108.4'), unit='MPa',
        technician=setup['tech'], verification_status=VerificationStatus.VERIFIED
    )

    report = ReportingService.issue_laboratory_report(
        sample=sample,
        approver=setup['approver'],
        outcome=FinalDecisionOutcome.ACCORDING_TO_SPEC,
        decision_notes='Material conforms to DC-SPEC R-01 Rev 4.2 acceptance standards.',
        specification_set=setup['spec_set']
    )

    assert report.id is not None
    assert report.status == 'ISSUED'
    assert report.sha256_hash != ''
    sample.refresh_from_db()
    assert sample.status == SampleStatus.REPORT_ISSUED

    # Test PDF generation
    pdf_buffer = ReportingService.generate_pdf_buffer(report.report_snapshot_json)
    pdf_bytes = pdf_buffer.getvalue()
    assert pdf_bytes.startswith(b'%PDF')
    assert len(pdf_bytes) > 1000

@pytest.mark.django_db
def test_facility_scoped_operational_endpoints(qa_lab_setup):
    """An authenticated technician cannot read another facility's samples."""
    from rest_framework.test import APIClient
    from rest_framework import status as http
    infra = qa_lab_setup
    other = Facility.objects.create(
        organization=infra['org'], name='Other Lab', code='DC-OTHER-SECURITY',
        city='Rotterdam'
    )
    other_sample = Sample.objects.create(
        sample_code='DC-SMP-FOREIGN-SECURITY',
        material_lot=infra['sample'].material_lot,
        current_facility=other, quantity_bricks=2, sampling_date='2026-01-21',
        sampled_by='External Inspector'
    )
    client = APIClient()
    client.force_authenticate(user=infra['tech'])
    listing = client.get('/api/v1/samples/samples/')
    assert listing.status_code == http.HTTP_200_OK
    sample_ids = [x['id'] for x in listing.json().get('results', [])] if isinstance(listing.json(), dict) else [x['id'] for x in listing.json()]
    assert str(infra['sample'].id) in sample_ids
    assert str(other_sample.id) not in sample_ids
    detail = client.get(f'/api/v1/samples/samples/{other_sample.id}/')
    assert detail.status_code == http.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_dashboard_rejects_foreign_facility_and_scopes_totals(qa_lab_setup):
    from rest_framework.test import APIClient
    from rest_framework import status as http
    infra = qa_lab_setup
    other = Facility.objects.create(
        organization=infra['org'], name='Other Lab', code='DC-OTHER-DASH',
        city='Rotterdam'
    )
    Sample.objects.create(
        sample_code='DC-SMP-FOREIGN-DASH', material_lot=infra['sample'].material_lot,
        current_facility=other, quantity_bricks=2, sampling_date='2026-01-21',
        sampled_by='External Inspector'
    )
    client = APIClient()
    client.force_authenticate(user=infra['tech'])
    res = client.get('/api/v1/laboratory/dashboard/stats/')
    assert res.status_code == http.HTTP_200_OK
    assert res.json()['samples']['total'] == 1
    forbidden = client.get(f'/api/v1/laboratory/dashboard/stats/?facility_id={other.id}')
    assert forbidden.status_code == http.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_non_approver_cannot_create_final_decision(qa_lab_setup):
    from rest_framework.test import APIClient
    from rest_framework import status as http
    infra = qa_lab_setup
    client = APIClient()
    client.force_authenticate(user=infra['tech'])
    response = client.post('/api/v1/quality/decisions/', {
        'sample': str(infra['sample'].id),
        'specification_set': str(infra['spec_set'].id),
        'outcome': FinalDecisionOutcome.ACCORDING_TO_SPEC,
        'decision_notes': 'Unauthorized action must not proceed.'
    }, format='json')
    assert response.status_code == http.HTTP_403_FORBIDDEN
    client.force_authenticate(user=infra['unauth_user'])
    assert client.get('/api/v1/quality/decisions/').status_code == http.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_issued_report_cannot_be_issued_twice(qa_lab_setup):
    infra = qa_lab_setup
    Result.objects.create(
        test_run=infra['test_run'], test_method=infra['ccs_method'],
        parameter_code='CCS', raw_input_text='108.4', numeric_value=Decimal('108.4'),
        unit='MPa', technician=infra['tech'], verification_status=VerificationStatus.VERIFIED
    )
    report = ReportingService.issue_laboratory_report(
        sample=infra['sample'], approver=infra['approver'],
        outcome=FinalDecisionOutcome.ACCORDING_TO_SPEC,
        decision_notes='First authorized certificate.',
        specification_set=infra['spec_set'],
    )
    original_hash = report.sha256_hash
    with pytest.raises(ValidationError, match='immutable'):
        ReportingService.issue_laboratory_report(
            sample=infra['sample'], approver=infra['approver'],
            outcome=FinalDecisionOutcome.ACCORDING_TO_SPEC,
            decision_notes='Attempt to silently overwrite issued certificate.',
            specification_set=infra['spec_set'],
        )
    report.refresh_from_db()
    assert report.sha256_hash == original_hash


@pytest.mark.django_db
def test_cross_facility_signing_is_rejected(qa_lab_setup):
    infra = qa_lab_setup
    other = Facility.objects.create(
        organization=infra['org'], name='Unassigned Lab',
        code='DC-FOREIGN-APPROVAL', city='Rotterdam'
    )
    external_sample = Sample.objects.create(
        sample_code='DC-SMP-APPROVE-FOREIGN', material_lot=infra['sample'].material_lot,
        current_facility=other, quantity_bricks=2, sampling_date='2026-01-21',
        sampled_by='External Inspector'
    )
    with pytest.raises(ValidationError, match='Unauthorized'):
        ReportingService.issue_laboratory_report(
            sample=external_sample, approver=infra['approver'],
            outcome=FinalDecisionOutcome.ACCORDING_TO_SPEC,
            decision_notes='Must fail outside facility scope.',
            specification_set=infra['spec_set'],
        )

@pytest.mark.django_db
def test_instrument_update_requires_facility_manager_or_lab_manager(qa_lab_setup):
    """Technicians can read their facility's instrument, not change its calibration data."""
    from rest_framework.test import APIClient
    from rest_framework import status as http
    infra = qa_lab_setup
    instrument = Instrument.objects.get(laboratory__facility=infra['facility'])
    client = APIClient()
    client.force_authenticate(user=infra['tech'])
    detail = client.get(f'/api/v1/laboratory/instruments/{instrument.id}/')
    assert detail.status_code == http.HTTP_200_OK
    denied = client.patch(
        f'/api/v1/laboratory/instruments/{instrument.id}/',
        {'is_operational': False}, format='json'
    )
    assert denied.status_code == http.HTTP_403_FORBIDDEN
    instrument.refresh_from_db()
    assert instrument.is_operational is True


@pytest.mark.django_db
def test_instrument_from_foreign_facility_is_hidden(qa_lab_setup):
    from rest_framework.test import APIClient
    from rest_framework import status as http
    infra = qa_lab_setup
    other = Facility.objects.create(
        organization=infra['org'], name='Other Instrument Lab',
        code='DC-OTHER-INST', city='Rotterdam'
    )
    from laboratory.models import Laboratory
    other_lab = Laboratory.objects.create(facility=other, name='Foreign Instrument Lab')
    foreign = Instrument.objects.create(
        asset_tag='EQ-FOREIGN-TEST', name='Foreign Furnace', laboratory=other_lab,
        manufacturer='Test Maker', model_number='FN-1', serial_number='SN-FN-001',
    )
    client = APIClient()
    client.force_authenticate(user=infra['tech'])
    denied = client.get(f'/api/v1/laboratory/instruments/{foreign.id}/')
    assert denied.status_code == http.HTTP_404_NOT_FOUND
