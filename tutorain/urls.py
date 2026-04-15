"""
URL configuration for tutorain project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from home.views import index
from django.http import HttpResponse



def robots_txt(request):
    return HttpResponse(
        "User-agent: *\nAllow: /\nSitemap: https://tutorain.com/sitemap.xml",
        content_type="text/plain"
    )



urlpatterns = [
    path('admin/', admin.site.urls),

    # 🌐 WEBSITE
    path('', include('home.urls')),

    # 📱 API
    path('api/', include('api.urls')),

        # 🤖 robots.txt
    path('robots.txt', robots_txt),
]
