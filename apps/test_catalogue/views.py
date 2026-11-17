from rest_framework import viewsets, permissions, filters
from .models import TestDefinition, TestMethod, SpecificationSet, SpecificationLimit, TestPlanTemplate
from .serializers import (
    TestDefinitionSerializer, TestMethodSerializer,
    SpecificationSetSerializer, SpecificationLimitSerializer,
    TestPlanTemplateSerializer
)


class TestDefinitionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestDefinition.objects.prefetch_related('methods').all()
    serializer_class = TestDefinitionSerializer
    permission_classes = [permissions.AllowAny]  # Public catalogue preview
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['code', 'name', 'discipline']


class TestMethodViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestMethod.objects.select_related('test_definition').all()
    serializer_class = TestMethodSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['standard_code', 'title', 'applicable_product_category']


class SpecificationSetViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SpecificationSet.objects.prefetch_related('limits__test_definition').all()
    serializer_class = SpecificationSetSerializer
    permission_classes = [permissions.IsAuthenticated]


class TestPlanTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestPlanTemplate.objects.prefetch_related('methods').all()
    serializer_class = TestPlanTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
