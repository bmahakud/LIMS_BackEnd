import os
import hashlib
import json
from decimal import Decimal
from io import BytesIO
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .models import LaboratoryReport, ConsolidatedReport, ReportStatus
from quality.models import FinalDecision, FinalDecisionOutcome
from samples.models import Sample, SampleStatus
from results.models import Result, VerificationStatus
from audit.models import AuditEvent, AuditAction
from accounts.operational_access import role_in_facility
from accounts.models import RoleType


class ReportingService:
    """
    Orchestrates atomic report issuance, snapshot freezing, and PDF rendering.
    Enforces four-eyes approval and prevents report issuance when tests remain unverified.
    """

    @classmethod
    @transaction.atomic
    def issue_laboratory_report(
        cls,
        sample: Sample,
        approver,
        outcome: FinalDecisionOutcome,
        decision_notes: str,
        specification_set
    ) -> LaboratoryReport:
        # Check permissions: approver must have can_sign_certificates
        is_authorized = role_in_facility(approver, (RoleType.AUTHORIZED_APPROVER,), sample.current_facility_id) and approver.memberships.filter(
            is_active=True, role__role_type=RoleType.AUTHORIZED_APPROVER,
            role__can_sign_certificates=True, facility_id=sample.current_facility_id
        ).exists()
        if not is_authorized:
            raise ValidationError("Unauthorized: Only designated Authorized Approvers can finalize QA decisions and issue reports.")

        # Require justification for deviations or rejections
        if outcome in [FinalDecisionOutcome.DEVIATION_ACCEPTABLE, FinalDecisionOutcome.DEVIATION_NOT_ACCEPTABLE]:
            if not decision_notes or len(decision_notes.strip()) < 10:
                raise ValidationError("Mandatory justification required for technical deviations or rejection decisions.")

        # Check that results exist and are verified
        sample_results = Result.objects.filter(
            test_run__assignment__specimen__parent_sample=sample,
            is_latest=True
        )
        if not sample_results.exists():
            raise ValidationError("Cannot issue report: No scientific results recorded for this sample.")

        unverified = sample_results.exclude(verification_status=VerificationStatus.VERIFIED)
        if unverified.exists():
            raise ValidationError(f"Cannot issue report: {unverified.count()} test results have not been verified by a Lead Metallurgist.")

        # Segregate the measuring technician from the final scientific approver.
        if sample_results.filter(technician_id=approver.id).exists():
            raise ValidationError('The recording technician cannot approve their own scientific results.')

        # Lock the sample and prevent overwriting an issued certificate.
        sample = Sample.objects.select_for_update().get(id=sample.id)
        if LaboratoryReport.objects.filter(sample=sample, status=ReportStatus.ISSUED).exists():
            raise ValidationError('An issued report is immutable; use the controlled revision process.')

        # Create or update FinalDecision
        final_decision, _ = FinalDecision.objects.update_or_create(
            sample=sample,
            defaults={
                'specification_set': specification_set,
                'outcome': outcome,
                'approver': approver,
                'decision_notes': decision_notes
            }
        )

        report_number = f"DC-REP-{timezone.now().year}-{sample.sample_code.split('-')[-1]}"

        # Assemble snapshot payload
        results_data = []
        for r in sample_results:
            results_data.append({
                'parameter': r.parameter_code,
                'standard': r.test_method.standard_code,
                'raw_value': r.raw_input_text,
                'numeric_value': str(r.numeric_value) if r.numeric_value is not None else None,
                'qualifier': r.qualifier,
                'unit': r.unit,
                'technician': r.technician.get_full_name(),
                'verified': r.verification_status == VerificationStatus.VERIFIED
            })

        snapshot = {
            'report_number': report_number,
            'issue_date': timezone.now().strftime('%Y-%m-%d'),
            'sample_code': sample.sample_code,
            'lot_number': sample.material_lot.lot_number,
            'material_name': sample.material_lot.material.name,
            'project_code': sample.material_lot.project.code,
            'client_name': sample.material_lot.project.client.organization.name,
            'specification': specification_set.code,
            'outcome': outcome,
            'approver_name': approver.get_full_name(),
            'approver_email': approver.email,
            'decision_notes': decision_notes,
            'results': results_data
        }

        # Calculate SHA-256 hash of immutable snapshot
        snapshot_bytes = json.dumps(snapshot, sort_keys=True).encode('utf-8')
        sha256 = hashlib.sha256(snapshot_bytes).hexdigest()

        lab_report, _ = LaboratoryReport.objects.update_or_create(
            sample=sample,
            defaults={
                'report_number': report_number,
                'final_decision': final_decision,
                'status': ReportStatus.ISSUED,
                'report_snapshot_json': snapshot,
                'sha256_hash': sha256,
                'issued_by': approver,
                'issued_at': timezone.now()
            }
        )

        sample.status = SampleStatus.REPORT_ISSUED
        sample.save()

        # Audit log event
        AuditEvent.objects.create(
            actor=approver,
            action=AuditAction.ISSUE_REPORT,
            entity_type='LaboratoryReport',
            entity_id=str(lab_report.id),
            summary=f"Issued Inspection Certificate {report_number} with verdict {outcome}."
        )

        return lab_report

    @classmethod
    def generate_pdf_buffer(cls, report_snapshot: dict) -> BytesIO:
        """
        Renders vector ISO/IEC 17025 accredited Inspection Certificate via ReportLab.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            'HeaderTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#11161d')
        )
        meta_style = ParagraphStyle(
            'MetaText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#4a5568')
        )

        story = []

        # Company Header
        story.append(Paragraph("<b>DANIELI CORUS REFRACTORY TESTING LABORATORY</b>", header_style))
        story.append(Paragraph("Procedure R-01 Refractory Acceptance Certificate • ISO/IEC 17025 Accredited", meta_style))
        story.append(Spacer(1, 15))

        # Overview Table
        overview_data = [
            ["Report Number:", report_snapshot.get('report_number', ''), "Issue Date:", report_snapshot.get('issue_date', '')],
            ["Sample Code:", report_snapshot.get('sample_code', ''), "Material Lot:", report_snapshot.get('lot_number', '')],
            ["Refractory Grade:", report_snapshot.get('material_name', ''), "Campaign Project:", report_snapshot.get('project_code', '')],
            ["Client:", report_snapshot.get('client_name', ''), "Governing Spec:", report_snapshot.get('specification', '')],
            ["QA Verdict:", report_snapshot.get('outcome', ''), "Authorized Approver:", report_snapshot.get('approver_name', '')],
        ]
        overview_table = Table(overview_data, colWidths=[110, 150, 110, 150])
        overview_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1a202c')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ]))
        story.append(overview_table)
        story.append(Spacer(1, 15))

        # Scientific Results Table
        results_rows = [["Property / Parameter", "Method Standard", "Measured Value", "Unit", "Verification"]]
        for r in report_snapshot.get('results', []):
            results_rows.append([
                r.get('parameter', ''),
                r.get('standard', ''),
                r.get('raw_value', ''),
                r.get('unit', ''),
                "VERIFIED" if r.get('verified') else "UNVERIFIED"
            ])

        results_table = Table(results_rows, colWidths=[140, 140, 100, 60, 80])
        results_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d75d36')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ]))
        story.append(results_table)
        story.append(Spacer(1, 15))

        # Engineering notes & SHA-256 seal
        notes = f"<b>Engineering Notes:</b> {report_snapshot.get('decision_notes', 'N/A')}<br/><br/><b>Digital Cryptographic Seal (SHA-256):</b><br/>{report_snapshot.get('sha256_hash', 'N/A')}"
        story.append(Paragraph(notes, meta_style))

        doc.build(story)
        buffer.seek(0)
        return buffer
