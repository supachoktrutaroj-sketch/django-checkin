from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('history/', views.history_view, name='history'),
    path('checkin/', views.checkin_view, name='checkin'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('export-excel/', views.export_excel, name='export_excel'),
]