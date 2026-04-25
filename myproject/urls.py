from django.contrib import admin
from django.urls import path, include
from checkin import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # 👉 route หลักทั้งหมดไปที่ checkin
    path('', include('checkin.urls')),

    # 👉 LINE webhook
    path('line-webhook/', views.line_webhook, name='line_webhook'),
]