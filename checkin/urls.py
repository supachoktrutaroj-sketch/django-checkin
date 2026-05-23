from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('checkin/', views.checkin_view, name='checkin'),
    
    # 📝 ประวัติการรายงานตัว
    path('history/', views.history_view, name='history'),

    # 🛠️ แดชบอร์ดผู้ดูแลระบบ
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # ⏱️ หน้าตั้งค่าเวลากลางประจำหน่วย
    path('time-settings/', views.time_settings_view, name='time_settings'),

    # 📊 จัดการส่งออกข้อมูล (แก้ไขจุดนี้เพื่อป้องกัน NoReverseMatch จากหน้าอื่น)
    path('export-excel/', views.admin_dashboard, name='export_excel'),
    path('export-pdf/', views.export_pdf, {'company_name': 'ALL'}, name='export_pdf'),              # 👈 รองรับการเรียกแบบไม่มีพารามิเตอร์ {% url 'export_pdf' %} (ให้ค่าเริ่มต้นเป็น ALL)
    path('export-pdf/<str:company_name>/', views.export_pdf, name='export_pdf_by_company'),  # 👈 รองรับการเรียกแบบแยกกองร้อยจากหน้าแดชบอร์ดแอดมิน

    # 👤 ข้อมูลส่วนตัวและระบบสแกนใบหน้า
    path('profile/', views.profile_view, name='profile'),
    path('face-register/', views.face_register_page, name='face_register'),
    path('save-face-descriptor/', views.save_face_descriptor, name='save_face_descriptor'),
    path('face-verify/', views.face_verify_page, name='face_verify'),

    # 🪖 จัดการกำลังพลรายบุคคล
    path('manage-users/', views.manage_users, name='manage_users'),
    path('manage-users/add/', views.add_user_admin, name='add_user_admin'),
    path('manage-users/delete/<int:user_id>/', views.delete_user_admin, name='delete_user_admin'),

    # ✏️ เส้นทางรองรับป๊อปอัปแก้ไขข้อมูลกำลังพล
    path('manage-users/edit/<int:user_id>/', views.edit_user_admin, name='edit_user_admin'),
    
    # ⏳ เส้นทางรองรับป๊อปอัปตั้งค่าวันลาและคำนวณวันขากลับ
    path('manage-users/save-leave/<int:user_id>/', views.save_leave_settings, name='save_leave_settings'),

    # 💂‍♂️ ตัวกรองและลิงก์แยกดูรายชื่อกำลังพลตามประเภทสถานะ
    path('manage-users/in-camp/', views.list_in_camp_view, name='list_in_camp'),
    path('manage-users/out-camp/', views.list_out_camp_view, name='list_out_camp'),
    path('manage-users/total/', views.list_total_view, name='list_total'),

    # 👑 หน้าตั้งพิกัดหมุดพื้นที่สำหรับ Superuser
    path('set-location/', views.set_location_view, name='set_location'),
]