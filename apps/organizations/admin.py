from django.contrib import admin
from .models import Organization, Facility, LaboratoryArea

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'org_type', 'country', 'accreditation_number', 'is_active', 'created_at')
    list_filter = ('org_type', 'is_active', 'country')
    search_fields = ('name', 'accreditation_number')

@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'organization', 'city', 'is_primary', 'is_active')
    list_filter = ('organization', 'is_active')
    search_fields = ('name', 'code', 'city')

@admin.register(LaboratoryArea)
class LaboratoryAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'facility', 'is_temperature_controlled', 'is_active')
    list_filter = ('facility', 'is_temperature_controlled', 'is_active')
    search_fields = ('name', 'code')
