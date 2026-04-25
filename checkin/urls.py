from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('history/', views.history_view, name='history'),
    path('checkin/', views.checkin_view, name='checkin'),

    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('time-settings/', views.time_settings_view, name='time_settings'),

    # ✅ Export
    path('export-excel/', views.export_excel, name='export_excel'),
    path('export-pdf/', views.export_pdf, name='export_pdf'),

    path('profile/', views.profile_view, name='profile'),

    path('face-register/', views.face_register_page, name='face_register'),
    path('save-face-descriptor/', views.save_face_descriptor, name='save_face_descriptor'),
    path('face-verify/', views.face_verify_page, name='face_verify'),
]