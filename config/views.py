from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers


class HealthCheckView(APIView):
    """
    Public health check endpoint providing non-sensitive operational status.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Service Health Check",
        description="Returns service availability, timestamp, and database connectivity status.",
        responses={
            200: inline_serializer(
                name="HealthResponse",
                fields={
                    "status": serializers.CharField(),
                    "service": serializers.CharField(),
                    "version": serializers.CharField(),
                    "database": serializers.CharField(),
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        db_status = "healthy"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            db_status = "unavailable"

        return Response({
            "status": "ok" if db_status == "healthy" else "degraded",
            "service": "Danieli Corus Refractory Laboratory LIMS API",
            "version": "1.0.0",
            "database": db_status
        })
