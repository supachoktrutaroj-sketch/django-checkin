from django.contrib import admin
from django.urls import path, include
from checkin import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('checkin.urls')),
    path('line-webhook/', views.line_webhook, name='line_webhook'),
]