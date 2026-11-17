from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Sample, SampleStatus, SampleReceipt, PackagingCondition, Specimen, SpecimenStatus


class SampleLifecycleService:
    """
    Encapsulates atomic state transitions and business validations for the R-01 Sample Journey.
    """

    ALLOWED_TRANSITIONS = {
        SampleStatus.REGISTERED: [SampleStatus.DISPATCHED, SampleStatus.RECEIVED, SampleStatus.HELD_DAMAGED],
        SampleStatus.DISPATCHED: [SampleStatus.RECEIVED, SampleStatus.HELD_DAMAGED],
        SampleStatus.RECEIVED: [SampleStatus.PREPARATION, SampleStatus.HELD_DAMAGED, SampleStatus.REJECTED],
        SampleStatus.HELD_DAMAGED: [SampleStatus.RECEIVED, SampleStatus.REJECTED],
        SampleStatus.PREPARATION: [SampleStatus.TESTING, SampleStatus.REJECTED],
        SampleStatus.TESTING: [SampleStatus.QA_REVIEW],
        SampleStatus.QA_REVIEW: [SampleStatus.REPORT_ISSUED, SampleStatus.TESTING],
        SampleStatus.REPORT_ISSUED: [SampleStatus.STORED],
        SampleStatus.STORED: [],
        SampleStatus.REJECTED: [],
    }

    @classmethod
    @transaction.atomic
    def record_receipt(
        cls,
        sample: Sample,
        user,
        packaging_condition: str,
        moisture_barrier_intact: bool,
        heat_numbers_verified: bool,
        remarks: str = ""
    ) -> SampleReceipt:
        """
        Processes formal intake receipt. If packaging is damaged or moisture compromised,
        transitions to HELD_DAMAGED rather than advancing to preparation.
        """
        is_damaged = (
            packaging_condition != PackagingCondition.INTACT
            or not moisture_barrier_intact
        )

        receipt = SampleReceipt.objects.create(
            sample=sample,
            received_by=user,
            packaging_condition=packaging_condition,
            moisture_barrier_intact=moisture_barrier_intact,
            heat_numbers_verified=heat_numbers_verified,
            is_accepted=not is_damaged,
            discrepancy_remarks=remarks
        )

        if is_damaged:
            sample.status = SampleStatus.HELD_DAMAGED
        else:
            sample.status = SampleStatus.RECEIVED

        sample.save()
        return receipt

    @classmethod
    @transaction.atomic
    def advance_status(cls, sample: Sample, new_status: SampleStatus) -> Sample:
        """
        Enforces atomic validation of legal status transitions.
        """
        current = sample.status
        allowed = cls.ALLOWED_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Illegal state transition: Cannot change sample status from '{current}' to '{new_status}'."
            )

        sample.status = new_status
        sample.save()
        return sample

    @classmethod
    @transaction.atomic
    def prepare_child_specimens(
        cls,
        sample: Sample,
        count: int,
        geometry: str,
        dimensions: dict = None
    ) -> list[Specimen]:
        """
        Generates child specimens from parent sample maintaining parent-child genealogy.
        """
        if sample.status not in [SampleStatus.RECEIVED, SampleStatus.PREPARATION]:
            raise ValidationError("Specimens can only be prepared after formal receipt acknowledgement.")

        existing_max = sample.specimens.count()
        created_specimens = []

        for i in range(1, count + 1):
            sub_index = existing_max + i
            specimen_code = f"{sample.sample_code}-SP{sub_index:02d}"
            sp = Specimen.objects.create(
                specimen_code=specimen_code,
                parent_sample=sample,
                sub_index=sub_index,
                geometry=geometry,
                length_mm=dimensions.get('length') if dimensions else None,
                width_mm=dimensions.get('width') if dimensions else None,
                height_mm=dimensions.get('height') if dimensions else None,
                planarity_checked=True,
                status=SpecimenStatus.PREPARED
            )
            created_specimens.append(sp)

        if sample.status != SampleStatus.PREPARATION:
            sample.status = SampleStatus.PREPARATION
            sample.save()

        return created_specimens
