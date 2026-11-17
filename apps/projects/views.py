from rest_framework import viewsets, permissions, filters
from .models import Client, Vendor, Project, Material, MaterialLot
from .serializers import (
    ClientSerializer, VendorSerializer, ProjectSerializer,
    MaterialSerializer, MaterialLotSerializer
)


class ClientViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Client.objects.select_related('organization').all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['organization__name', 'contact_person']


class VendorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vendor.objects.select_related('organization').all()
    serializer_class = VendorSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['organization__name', 'vendor_code']


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related('client__organization').all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['code', 'name', 'plant_asset']
    ordering_fields = ['start_date', 'code']


class MaterialViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'name', 'category']


class MaterialLotViewSet(viewsets.ModelViewSet):
    queryset = MaterialLot.objects.select_related('project', 'material', 'vendor__organization').all()
    serializer_class = MaterialLotSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['lot_number', 'material__name', 'project__code']
