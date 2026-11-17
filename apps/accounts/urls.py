from django.urls import path
from .views import (
    LoginView,
    LogoutView,
    CurrentUserView,
    CSRFTokenView,
    UserManagementListView,
    UserManagementDetailView,
    UserPasswordResetView,
    UserMembershipManagementView,
    UserActivationView,
    UserDeactivationView,
    DirectMembershipDetailView,
    OrganizationDirectoryAdminView,
    FacilityDirectoryAdminView,
    RoleDirectoryView,
    FacilityDirectoryView,
    UserAccessHistoryView,
    UserInvitationView,
    CurrentUserPermittedScopeView,
)

urlpatterns = [
    # Session Authentication & Clearance
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', CurrentUserView.as_view(), name='auth-me'),
    path('me/scope/', CurrentUserPermittedScopeView.as_view(), name='auth-me-scope'),
    path('csrf/', CSRFTokenView.as_view(), name='auth-csrf'),

    # Enterprise Personnel & RBAC Management
    path('users/', UserManagementListView.as_view(), name='user-list-create'),
    path('users/<uuid:user_id>/', UserManagementDetailView.as_view(), name='user-detail-update'),
    path('users/<uuid:user_id>/activate/', UserActivationView.as_view(), name='user-activate'),
    path('users/<uuid:user_id>/deactivate/', UserDeactivationView.as_view(), name='user-deactivate'),
    path('users/<uuid:user_id>/reset-password/', UserPasswordResetView.as_view(), name='user-password-reset'),
    path('users/<uuid:user_id>/invite/', UserInvitationView.as_view(), name='user-invite'),
    path('users/<uuid:user_id>/history/', UserAccessHistoryView.as_view(), name='user-access-history'),
    path('users/<uuid:user_id>/memberships/', UserMembershipManagementView.as_view(), name='user-membership-list-create'),
    path('users/<uuid:user_id>/memberships/<uuid:membership_id>/', UserMembershipManagementView.as_view(), name='user-membership-detail'),

    # Direct membership route
    path('memberships/<uuid:membership_id>/', DirectMembershipDetailView.as_view(), name='admin-membership-direct'),

    # Meta Directories & Admin Lists
    path('roles/', RoleDirectoryView.as_view(), name='roles-directory'),
    path('organizations/', OrganizationDirectoryAdminView.as_view(), name='organizations-directory'),
    path('facilities/', FacilityDirectoryView.as_view(), name='facilities-directory'),
    path('facilities-admin/', FacilityDirectoryAdminView.as_view(), name='facilities-directory-admin'),
]
