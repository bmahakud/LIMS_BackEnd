from accounts.operational_access import ScopedOperationalMixin, role_in_facility
from accounts.models import RoleType
from rest_framework.exceptions import PermissionDenied
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from .models import QAReview, Deviation, FinalDecision, FinalDecisionOutcome
from .serializers import QAReviewSerializer, DeviationSerializer, FinalDecisionSerializer
from .services import SpecificationService
from results.models import Result
from test_catalogue.models import SpecificationLimit


class QAReviewViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = QAReview.objects.select_related('result', 'specification_limit', 'deviation').all()
    serializer_class = QAReviewSerializer
    facility_lookup = "result__test_run__assignment__work_order__laboratory__facility_id"
    facility_attr = "result.test_run.assignment.work_order.laboratory.facility_id"
    final_sample_attr = "result.test_run.assignment.specimen.parent_sample"
    write_roles = {"create": (RoleType.QA_REVIEWER,), "evaluate": (RoleType.QA_REVIEWER,)}
    permission_classes = ScopedOperationalMixin.permission_classes

    @action(detail=False, methods=['post'], url_path='evaluate-result')
    def evaluate(self, request):
        result_id = request.data.get('result_id')
        limit_id = request.data.get('limit_id')

        try:
            result = Result.objects.get(id=result_id)
            limit = SpecificationLimit.objects.get(id=limit_id)
        except Exception:
            return Response({"detail": "Result or SpecificationLimit not found."}, status=status.HTTP_404_NOT_FOUND)

        facility_id = result.test_run.assignment.work_order.laboratory.facility_id
        if not role_in_facility(request.user, (RoleType.QA_REVIEWER,), facility_id):
            raise PermissionDenied("QA evaluation requires clearance in the result's facility.")
        if result.test_run.assignment.specimen.parent_sample.status in ('REPORT_ISSUED', 'STORED'):
            raise PermissionDenied("Issued results cannot be evaluated again.")
        eval_status, delta, notes = SpecificationService.evaluate_result(result, limit)

        review, _ = QAReview.objects.update_or_create(
            result=result,
            specification_limit=limit,
            defaults={
                'evaluation_status': eval_status,
                'delta_from_limit': delta,
                'evaluation_notes': notes
            }
        )
        return Response(QAReviewSerializer(review).data, status=status.HTTP_200_OK)


class DeviationViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = Deviation.objects.select_related('qa_review', 'justified_by').all()
    serializer_class = DeviationSerializer
    facility_lookup = "qa_review__result__test_run__assignment__work_order__laboratory__facility_id"
    facility_attr = "qa_review.result.test_run.assignment.work_order.laboratory.facility_id"
    final_sample_attr = "qa_review.result.test_run.assignment.specimen.parent_sample"
    write_roles = {"create": (RoleType.QA_REVIEWER,), "update": (RoleType.QA_REVIEWER,), "partial_update": (RoleType.QA_REVIEWER,)}
    permission_classes = ScopedOperationalMixin.permission_classes

    def perform_create(self, serializer):
        self.ensure_write_scope(serializer)
        serializer.save(justified_by=self.request.user)


class FinalDecisionViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = FinalDecision.objects.select_related('sample', 'specification_set', 'approver').all()
    serializer_class = FinalDecisionSerializer
    facility_lookup = "sample__current_facility_id"
    facility_attr = "sample.current_facility_id"
    final_sample_attr = "sample"
    write_roles = {"create": (RoleType.AUTHORIZED_APPROVER,)}
    permission_classes = ScopedOperationalMixin.permission_classes

    def perform_create(self, serializer):
        self.ensure_write_scope(serializer)
        # Strict permission: must have can_sign_certificates
        sample_facility_id = serializer.validated_data['sample'].current_facility_id
        is_approver = role_in_facility(
            self.request.user, (RoleType.AUTHORIZED_APPROVER,), sample_facility_id
        ) and self.request.user.memberships.filter(
            is_active=True, facility_id=sample_facility_id,
            role__role_type=RoleType.AUTHORIZED_APPROVER,
            role__can_sign_certificates=True,
        ).exists()
        if not is_approver:
            raise PermissionDenied("Authorized Approver qualification and signing capability required.")

        outcome = serializer.validated_data.get('outcome')
        notes = serializer.validated_data.get('decision_notes', '')

        if outcome in [FinalDecisionOutcome.DEVIATION_ACCEPTABLE, FinalDecisionOutcome.DEVIATION_NOT_ACCEPTABLE]:
            if not notes or len(notes.strip()) < 10:
                raise ValidationError("Mandatory technical justification required for deviations or rejections.")

        serializer.save(approver=self.request.user)
