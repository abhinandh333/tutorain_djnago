from django.urls import path
from . import views
from .views import index, contact, student_login_web, dashboard,comingsoon,findsub,maca,accounts_login_redirect,download,auto_login,free_classes
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', index, name='home'),
    path('login/', student_login_web, name='login'),
    path('dashboard/', dashboard, name='dashboard'),
    path('contact/', contact, name='contact'),
    path('comingsoon/', comingsoon, name='comingsoon'),
    path('findsub/', findsub, name='findsub'),
    path('maca/', maca, name='maca'),
    path('accounts/login/', accounts_login_redirect),
    path('download/', download, name='download'),
    path('free_classes/', free_classes, name='free_classes'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('auto-login', auto_login, name='auto_login'),
    path("meet/<str:username>/", views.meet_redirect),
    path(
    "free_classes/<str:class_name>/",
    views.class_subjects,
    name="class_subjects"
),
    path(
    "free_classes/<str:class_name>/<str:subject>/",
    views.subject_details,
    name="subject_details"
),
    

]