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

    # 🪖 ปรับตรงนี้ลบ _view ออก ให้เหลือ views.manage_users ชัวร์กว่าครับ
    path('manage-users/', views.manage_users, name='manage_users'),
    path('manage-users/add/', views.add_user_admin, name='add_user_admin'),
    path('manage-users/edit/<int:user_id>/', views.edit_user_admin, name='edit_user_admin'),
    path('manage-users/delete/<int:user_id>/', views.delete_user_admin, name='delete_user_admin'),

    # ลิงก์แยกหน้าดูรายชื่อกำลังพล 3 รูปแบบ ปรับให้วิ่งไปที่ฟังก์ชันหลักทั้งหมดเพื่อไม่ให้ล่ม
    path('manage-users/in-camp/', views.manage_users, name='list_in_camp'),
    path('manage-users/out-camp/', views.manage_users, name='list_out_camp'),
    path('manage-users/total/', views.manage_users, name='list_total'),
]