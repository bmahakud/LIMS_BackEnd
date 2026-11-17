from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WorkOrderViewSet, TestAssignmentViewSet

router = DefaultRouter()
router.register(r'orders', WorkOrderViewSet, basename='work-order')
router.register(r'assignments', TestAssignmentViewSet, basename='test-assignment')

urlpatterns = [
    path('', include(router.urls)),
]
