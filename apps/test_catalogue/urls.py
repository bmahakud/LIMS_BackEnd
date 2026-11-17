from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TestDefinitionViewSet, TestMethodViewSet, SpecificationSetViewSet, TestPlanTemplateViewSet

router = DefaultRouter()
router.register(r'tests', TestDefinitionViewSet, basename='test-definition')
router.register(r'methods', TestMethodViewSet, basename='test-method')
router.register(r'specifications', SpecificationSetViewSet, basename='specification-set')
router.register(r'templates', TestPlanTemplateViewSet, basename='test-plan-template')

urlpatterns = [
    path('', include(router.urls)),
]
