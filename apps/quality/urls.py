from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QAReviewViewSet, DeviationViewSet, FinalDecisionViewSet

router = DefaultRouter()
router.register(r'reviews', QAReviewViewSet, basename='qa-review')
router.register(r'deviations', DeviationViewSet, basename='deviation')
router.register(r'decisions', FinalDecisionViewSet, basename='final-decision')

urlpatterns = [
    path('', include(router.urls)),
]
