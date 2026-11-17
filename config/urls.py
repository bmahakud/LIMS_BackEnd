from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from config.views import HealthCheckView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Health Check API
    path('api/v1/health/', HealthCheckView.as_view(), name='api-health-check'),

    # Real Authentication & Session APIs
    path('api/v1/auth/', include('accounts.urls')),
    path('api/v1/users/', include('accounts.urls')),
    path('api/v1/admin/', include('accounts.urls')),

    # Public Communications & Enquiries
    path('api/v1/communications/', include('communications.urls')),

    # Step 4: Master Data, Projects, Catalogue & Workflows
    path('api/v1/projects/', include('projects.urls')),
    path('api/v1/catalogue/', include('test_catalogue.urls')),
    path('api/v1/laboratory/', include('laboratory.urls')),
    path('api/v1/samples/', include('samples.urls')),
    path('api/v1/work-orders/', include('work_orders.urls')),

    # Step 5: Results, QA Decisions, & Consolidated Reports
    path('api/v1/results/', include('results.urls')),
    path('api/v1/quality/', include('quality.urls')),
    path('api/v1/reports/', include('reports.urls')),

    # OpenAPI Schema & Documentation
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
