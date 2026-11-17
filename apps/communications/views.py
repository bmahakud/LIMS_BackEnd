from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from drf_spectacular.utils import extend_schema
from .serializers import InquiryCreateSerializer


class InquiryRateThrottle(AnonRateThrottle):
    rate = '10/hour'


class PublicInquiryView(APIView):
    """
    Public testing enquiry intake endpoint with spam protection and privacy logging.
    """
    permission_classes = [AllowAny]
    throttle_classes = [InquiryRateThrottle]

    @extend_schema(
        summary="Submit Public Testing Enquiry",
        description="Registers a refractory testing enquiry from prospective clients or project managers.",
        request=InquiryCreateSerializer,
        responses={201: InquiryCreateSerializer}
    )
    def post(self, request, *args, **kwargs):
        serializer = InquiryCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Extract client IP and user agent safely
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        inquiry = serializer.save(ip_address=ip, user_agent=user_agent)

        # Note: Transactional email alerts will be dispatched here once client-approved SMTP settings are configured.
        return Response(
            {
                "id": inquiry.id,
                "detail": "Thank you for reaching out. Your refractory testing inquiry has been registered with Danieli Corus Refractory Laboratory.",
                "created_at": inquiry.created_at
            },
            status=status.HTTP_201_CREATED
        )
