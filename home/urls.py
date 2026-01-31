from django.urls import path

from .views import student_login, student_classes

urlpatterns = [

    #path('login/', login_view, name='login-page'),  # for browser
    path('login/', student_login), # for Flutter app
    path('classes/', student_classes),
]


