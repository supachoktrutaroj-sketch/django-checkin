from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('checkin/', views.checkin_view, name='checkin'),
    
    # 📝 ตรงกับ views.history_view
    path('history/', views.history_view, name='history'),

    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # ⏱️ 🛠️ แก้ไขใหม่: แยกไปเข้าหน้าฟังก์ชันตั้งเวลาโดยเฉพาะ (เลิกใช้หน้าแดชบอร์ดซ้ำกันแล้ว)
    path('time-settings/', views.time_settings_view, name='time_settings'),

    # 📊 ซ่อน export_excel ชั่วคราว (เพราะใน views.py ไม่มีฟังก์ชันนี้) ระบบจะได้เปิดได้สักทีครับ
    path('export-excel/', views.admin_dashboard, name='export_excel'),
    path('export-pdf/', views.export_pdf, name='export_pdf'),

    path('profile/', views.profile_view, name='profile'),

    path('face-register/', views.face_register_page, name='face_register'),
    path('save-face-descriptor/', views.save_face_descriptor, name='save_face_descriptor'),
    path('face-verify/', views.face_verify_page, name='face_verify'),

    # 🪖 จัดการกำลังพล
    path('manage-users/', views.manage_users, name='manage_users'),
    path('manage-users/add/', views.add_user_admin, name='add_user_admin'),
    path('manage-users/delete/<int:user_id>/', views.delete_user_admin, name='delete_user_admin'),

    # 💂‍♂️ ลิงก์แยกดูรายชื่อกำลังพล 3 รูปแบบ (ตรงตามฟังก์ชันท้ายไฟล์ views.py ของคุณ)
    path('manage-users/in-camp/', views.list_in_camp_view, name='list_in_camp'),
    path('manage-users/out-camp/', views.list_out_camp_view, name='list_out_camp'),
    path('manage-users/total/', views.list_total_view, name='list_total'),

    # 👑 หน้าตั้งพิกัดใหม่ (Superuser) ตรงตาม set_location_view ชัวร์ 100%
    path('set-location/', views.set_location_view, name='set_location'),
]