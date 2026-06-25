from django.urls import path
from .views import index, contact, student_login_web, dashboard,comingsoon,findsub,maca,accounts_login_redirect

urlpatterns = [
    path('', index, name='home'),
    path('login/', student_login_web, name='login'),
    path('dashboard/', dashboard, name='dashboard'),
    path('contact/', contact, name='contact'),
    path('comingsoon/', comingsoon, name='comingsoon'),
    path('findsub/', findsub, name='findsub'),
    path('maca/', maca, name='maca'),
    path('accounts/login/', accounts_login_redirect),

]