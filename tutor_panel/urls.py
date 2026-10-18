from django.urls import path
from . import views

app_name = "tutor_panel"

urlpatterns = [
    path("", views.login_page, name="login"),
    path("firebase-login/", views.firebase_login, name="firebase_login"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("logout/", views.logout_page, name="logout"),
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("manage-tutors/", views.manage_tutors, name="manage_tutors"),
    path("set-password/", views.set_password_page, name="set_password"),
    path(
    "password-setup-complete/",
    views.password_setup_complete,
    name="password_setup_complete",
),
    path("notify-admin/", views.notify_admin, name="notify_admin"),
]