from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LaboratoryViewSet, InstrumentViewSet
from .dashboard_views import DashboardStatsView

router = DefaultRouter()
router.register(r'labs', LaboratoryViewSet, basename='laboratory')
router.register(r'instruments', InstrumentViewSet, basename='instrument')

urlpatterns = [
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('', include(router.urls)),
]
