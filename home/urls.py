from django.urls import path

from .views import student_login

urlpatterns = [

    #path('login/', login_view, name='login-page'),  # for browser
    path('login/', student_login), # for Flutter app
]


