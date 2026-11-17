import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from test_catalogue.models import SpecificationSet, SpecificationLimit
from samples.models import Sample
from results.models import Result


class SpecificationEvaluationStatus(models.TextChoices):
    PASS = 'PASS', 'Meets Specification'
    DEVIATION = 'DEVIATION', 'Technical Deviation'
    FAIL = 'FAIL', 'Specification Failed'
    INDETERMINATE = 'INDETERMINATE', 'Indeterminate (Qualified Value Ambiguity)'
    NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs Senior Metallurgist Review'
    MISSING_DATA = 'MISSING_DATA', 'Missing Data'


class QAReview(models.Model):
    """
    Evaluation of a Result against an approved SpecificationLimit.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result = models.ForeignKey(Result, on_delete=models.CASCADE, related_name='qa_reviews')
    specification_limit = models.ForeignKey(SpecificationLimit, on_delete=models.PROTECT, related_name='reviews')
    evaluation_status = models.CharField(
        max_length=30, choices=SpecificationEvaluationStatus.choices, default=SpecificationEvaluationStatus.NEEDS_REVIEW
    )
    delta_from_limit = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    evaluation_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reviewed_at']

    def __str__(self):
        return f"{self.result.parameter_code}: {self.evaluation_status} against {self.specification_limit}"


class DeviationSeverity(models.TextChoices):
    MINOR = 'MINOR', 'Minor Dimensional / Cosmetic'
    MAJOR = 'MAJOR', 'Major Mechanical / Thermal Margin'
    CRITICAL = 'CRITICAL', 'Critical Service Failure Risk'


class Deviation(models.Model):
    """
    Formal record when a property deviates from DC-SPEC acceptance criteria.
    Requires justification for acceptance or rejection.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qa_review = models.OneToOneField(QAReview, on_delete=models.CASCADE, related_name='deviation')
    severity = models.CharField(max_length=30, choices=DeviationSeverity.choices, default=DeviationSeverity.MAJOR)
    deviation_description = models.TextField()
    technical_justification = models.TextField(help_text="Mandatory engineering rationale explaining why deviation is acceptable or rejected.")
    is_acceptable = models.BooleanField(default=False)
    justified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='justified_deviations')
    created_at = models.DateTimeField(auto_now_add=True)


class FinalDecisionOutcome(models.TextChoices):
    ACCORDING_TO_SPEC = 'APPROVED_SPEC', 'According to Specification — Approved'
    DEVIATION_ACCEPTABLE = 'APPROVED_DEVIATION', 'Deviation Acceptable — Approved'
    DEVIATION_NOT_ACCEPTABLE = 'NOT_APPROVED', 'Deviation Not Acceptable — Not Approved'


class FinalDecision(models.Model):
    """
    Authorized QA final release decision for a Sample Lot.
    Only designated Authorized Approvers can finalize decisions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.OneToOneField(Sample, on_delete=models.PROTECT, related_name='final_qa_decision')
    specification_set = models.ForeignKey(SpecificationSet, on_delete=models.PROTECT)
    outcome = models.CharField(max_length=40, choices=FinalDecisionOutcome.choices)
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='final_decisions')
    decision_notes = models.TextField(help_text="Engineering summary & release justification.")
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-decided_at']

    def __str__(self):
        return f"{self.sample.sample_code}: {self.get_outcome_display()} by {self.approver.email}"
