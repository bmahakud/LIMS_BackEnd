from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClientViewSet, VendorViewSet, ProjectViewSet, MaterialViewSet, MaterialLotViewSet

router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'vendors', VendorViewSet, basename='vendor')
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'materials', MaterialViewSet, basename='material')
router.register(r'lots', MaterialLotViewSet, basename='material-lot')

urlpatterns = [
    path('', include(router.urls)),
]
