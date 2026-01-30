from django.urls import path
from home.views import index
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from home.views import LoginDetailViewSet

router = DefaultRouter()
router.register(r'login', LoginDetailViewSet, basename='login')

urlpatterns = [
    path('index/', index,name='index'),
    path('', include(router.urls)),  # All ViewSet URLs are included
]