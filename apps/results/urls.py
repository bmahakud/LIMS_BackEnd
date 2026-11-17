from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TestRunViewSet, ResultViewSet, RetestRequestViewSet

router = DefaultRouter()
router.register(r'runs', TestRunViewSet, basename='test-run')
router.register(r'entries', ResultViewSet, basename='result')
router.register(r'retests', RetestRequestViewSet, basename='retest-request')

urlpatterns = [
    path('', include(router.urls)),
]
