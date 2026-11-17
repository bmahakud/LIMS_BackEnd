from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SampleViewSet, SpecimenViewSet

router = DefaultRouter()
router.register(r'samples', SampleViewSet, basename='sample')
router.register(r'specimens', SpecimenViewSet, basename='specimen')

urlpatterns = [
    path('', include(router.urls)),
]
