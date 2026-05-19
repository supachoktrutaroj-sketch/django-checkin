from django.apps import AppConfig
from django.db.models.signals import post_migrate

def create_superuser_after_migrate(sender, **kwargs):
    """
    ฟังก์ชันสร้าง Superuser อัตโนมัติหลังจากระบบ Migrate และพร้อมใช้งานแล้ว
    """
    from django.contrib.auth.models import User
    try:
        if not User.objects.filter(username='admin_railway').exists():
            User.objects.create_superuser('admin_railway', 'admin@example.com', '12345678a')
            print("✅ [Railway Auto-Setup] สร้างบัญชี admin_railway สำเร็จ!")
    except Exception as e:
        print("🔴 ไม่สามารถสร้างแอดมินได้:", str(e))

class CheckinConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'checkin'  # ตรงนี้ถ้าในไฟล์เดิมของคุณเป็นชื่ออื่น ให้ใช้ชื่อเดิมของคุณนะครับ

    def ready(self):
        # ใช้ Signal คอยจับว่าถ้าระบบโหลดเสร็จแล้ว ให้รันฟังก์ชันสร้างแอดมินทันที
        post_migrate.connect(create_superuser_after_migrate, sender=self)