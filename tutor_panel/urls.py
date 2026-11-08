from django.urls import path
from . import views

app_name = "tutor_panel"

urlpatterns = [
    path("", views.login_page, name="login"),
    path("firebase-login/", views.firebase_login, name="firebase_login"),
    path("electron-login/", views.electron_login, name="electron_login"),
    path("electron-session/", views.electron_session, name="electron_session"),
    path("electron-logout/", views.electron_logout, name="electron_logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("logout/", views.logout_page, name="logout"),
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("manage-tutors/", views.manage_tutors, name="manage_tutors"),
    path("set-password/", views.set_password_page, name="set_password"),
    path("password-setup-complete/", views.password_setup_complete, name="password_setup_complete"),
    path("notify-admin/", views.notify_admin, name="notify_admin"),
    path("manage-students/", views.manage_students, name="manage_students"),
    path("students/", views.tutor_students, name="tutor_students"),
    path("attendance/", views.tutor_attendance, name="tutor_attendance"),
    path(
    "attendance-summary/",
    views.attendance_summary,
    name="attendance_summary",
    ),
    path("weekly-reports/", views.weekly_student_reports, name="weekly_student_reports"),
    path("parent/", views.parent_portal, name="parent_portal"),
    path("tutor-payments/", views.tutor_payments, name="tutor_payments"),
    path("weekly-parent-email-trigger/", views.send_weekly_parent_reports, name="weekly_parent_email_trigger"),
    path(
        "student-register/",
        views.student_register_page,
        name="student_register",
    ),
    path(
        "student-register/send-code/",
        views.student_send_registration_code,
        name="student_send_registration_code",
    ),
    path(
        "student-register/complete/",
        views.student_complete_registration,
        name="student_complete_registration",
    ),

    path(
    "class-report-verification/",
    views.class_report_verification,
    name="class_report_verification"
    ),

    #path("electron-login/", views.electron_login, name="electron_login"),

    
]
