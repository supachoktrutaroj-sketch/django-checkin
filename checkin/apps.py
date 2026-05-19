from django.apps import AppConfig


class CheckinConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'checkin'
# โค้ดสร้างแอดมินอัตโนมัติเมื่อรันบนเซิร์ฟเวอร์จริง
from django.contrib.auth.models import User
try:
    if not User.objects.filter(username='admin_railway').exists():
        User.objects.create_superuser('admin_railway', 'admin@example.com', '12345678a')
        print("✅ สร้างบัญชีแอดมินหลักสำเร็จแล้ว!")
except Exception as e:
    pass