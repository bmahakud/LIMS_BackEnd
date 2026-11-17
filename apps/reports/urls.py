from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LaboratoryReportViewSet, ConsolidatedReportViewSet

router = DefaultRouter()
router.register(r'reports', LaboratoryReportViewSet, basename='laboratory-report')
router.register(r'crc', ConsolidatedReportViewSet, basename='consolidated-report')

urlpatterns = [
    path('', include(router.urls)),
]
