from django.urls import path
from home.views import student_login, student_classes

urlpatterns = [
    path('login/', student_login),
    path('classes/', student_classes),
]