from uuid import UUID
from rest_framework.exceptions import PermissionDenied, ValidationError
from accounts.operational_access import authorized_facility_ids
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.models import User, RoleType
from accounts.permissions import HasActiveLimsAccess
from samples.models import Sample, SampleStatus
from work_orders.models import WorkOrder, WorkOrderStatus
from quality.models import FinalDecision, QAReview, Deviation, SpecificationEvaluationStatus
from reports.models import LaboratoryReport, ReportStatus
from audit.models import AuditEvent


class DashboardStatsView(APIView):
    """
    Returns authentic database-calculated statistics for active LIMS operations
    tailored to the caller's authorized role and facility context.
    Zero fabricated metrics.
    """
    permission_classes = [HasActiveLimsAccess]

    def get(self, request, *args, **kwargs):
        user = request.user
        facility_id = request.query_params.get('facility_id')
        allowed_facilities = authorized_facility_ids(user)
        if not allowed_facilities:
            raise PermissionDenied("An active facility membership is required.")
        if facility_id:
            try:
                selected = str(UUID(facility_id))
            except (TypeError, ValueError):
                raise ValidationError({"facility_id": "Invalid facility identifier."})
            if selected not in allowed_facilities:
                raise PermissionDenied("Facility is outside your authorized scope.")
            allowed_facilities = {selected}

        sample_qs = Sample.objects.filter(current_facility_id__in=allowed_facilities)
        wo_qs = WorkOrder.objects.filter(laboratory__facility_id__in=allowed_facilities)

        # Operational metrics
        total_samples = sample_qs.count()
        samples_received = sample_qs.filter(status=SampleStatus.RECEIVED).count()
        samples_testing = sample_qs.filter(status__in=[SampleStatus.PREPARATION, SampleStatus.TESTING]).count()
        samples_held = sample_qs.filter(status=SampleStatus.HELD_DAMAGED).count()
        samples_approved = sample_qs.filter(status=SampleStatus.REPORT_ISSUED).count()
        samples_stored = sample_qs.filter(status=SampleStatus.STORED).count()
        samples_registered = sample_qs.filter(status=SampleStatus.REGISTERED).count()

        active_work_orders = wo_qs.exclude(status=WorkOrderStatus.COMPLETED).count()
        reports_issued = LaboratoryReport.objects.filter(status=ReportStatus.ISSUED, sample__current_facility_id__in=allowed_facilities).count()
        deviations_count = Deviation.objects.filter(qa_review__result__test_run__assignment__work_order__laboratory__facility_id__in=allowed_facilities).count()

        # Role-specific real query stats
        role_stats = {
            "users_total": 0,
            "users_active": 0,
            "audit_events_recent": 0,
            "results_pending_qa": QAReview.objects.filter(evaluation_status=SpecificationEvaluationStatus.NEEDS_REVIEW, result__test_run__assignment__work_order__laboratory__facility_id__in=allowed_facilities).count(),
            "decisions_pending_approver": sample_qs.filter(final_qa_decision__isnull=True, status=SampleStatus.TESTING).count(),
            "draft_reports": LaboratoryReport.objects.filter(status=ReportStatus.DRAFT, sample__current_facility_id__in=allowed_facilities).count(),
            "samples_in_storage": samples_stored,
            "technician_assigned_wos": wo_qs.filter(assignments__assigned_technician=user).distinct().exclude(status=WorkOrderStatus.COMPLETED).count(),
        }

        if user.memberships.filter(is_active=True, role__role_type=RoleType.SUPER_ADMIN, organization__is_active=True, facility_id__in=allowed_facilities).exists():
            orgs = user.memberships.filter(is_active=True, role__role_type=RoleType.SUPER_ADMIN).values_list('organization_id', flat=True)
            role_stats["users_total"] = User.objects.filter(memberships__organization_id__in=orgs).distinct().count()
            role_stats["users_active"] = User.objects.filter(is_active=True, memberships__organization_id__in=orgs).distinct().count()
            role_stats["audit_events_recent"] = AuditEvent.objects.filter(actor__memberships__organization_id__in=orgs).distinct().count()

        return Response({
            "samples": {
                "total": total_samples,
                "awaiting_receipt": samples_registered,
                "received": samples_received,
                "in_testing": samples_testing,
                "held_damaged": samples_held,
                "approved": samples_approved,
                "archived": samples_stored
            },
            "work_orders": {
                "active": active_work_orders,
                "total": wo_qs.count()
            },
            "quality": {
                "deviations_recorded": deviations_count,
                "reports_issued": reports_issued
            },
            "role_stats": role_stats
        })
