from django.db import models
from django.contrib.auth.models import User

class CheckInRecord(models.Model):

    ACTION_CHOICES = [
        ('checkin', 'Check In'),
        ('checkout', 'Check Out'),
    ]

    STATUS_CHOICES = [
        ('present', 'Present'),
        ('late', 'Late'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    action = models.CharField(
        max_length=10,
        choices=ACTION_CHOICES
    )

    latitude = models.FloatField()

    longitude = models.FloatField()

    # 🛠️ แก้ไข: เปลี่ยนชื่อเพื่อให้ตรงกับ views.py ที่ส่งมาเป็น distance_meters
    distance_meters = models.FloatField(
        default=0
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='present'
    )

    # 🛠️ เพิ่มใหม่: ฟิลด์เก็บประเภทการยืนยันตัวตน (เช่น 'face')
    verification_method = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default='face'
    )

    # 🛠️ เพิ่มใหม่: ฟิลด์เก็บคะแนนความมั่นใจใบหน้าจากการสแกน
    confidence_score = models.FloatField(
        default=0.0,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.created_at:%Y-%m-%d %H:%M:%S}"


class SystemSetting(models.Model):

    checkin_start_time = models.TimeField(
        default="08:00"
    )

    late_time = models.TimeField(
        default="08:30"
    )

    return_deadline = models.TimeField(
        default="18:00"
    )

    # 📍 เพิ่มฟิลด์พิกัดศูนย์กลางหน่วยงาน (กำหนดพิกัดเริ่มต้นเป็น บก.ทบ. เพื่อไม่ให้ฐานข้อมูลว่าง)
    latitude = models.FloatField(
        default=13.819810,
        verbose_name="ละติจูดที่ตั้งหน่วย"
    )

    longitude = models.FloatField(
        default=100.529614,
        verbose_name="ลองจิจูดที่ตั้งหน่วย"
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return "System Setting"

    class Meta:
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"


class UserProfile(models.Model):

    COMPANY_CHOICES = [
        ('1', 'กองร้อย 1'),
        ('2', 'กองร้อย 2'),
        ('3', 'กองร้อย 3'),
        ('4', 'กองร้อย 4'),
        ('5', 'กองร้อยสนับสนุน'),
    ]

    PERSON_STATUS_CHOICES = [
        ('normal', 'ปกติ'),
        ('leave', 'ลาพัก'),
        ('mission', 'ไปราชการ'),
        ('home', 'กลับบ้าน'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    company = models.CharField(
        max_length=10,
        choices=COMPANY_CHOICES,
        default='1'
    )

    person_status = models.CharField(
        max_length=20,
        choices=PERSON_STATUS_CHOICES,
        default='normal'
    )

    return_date = models.DateField(
        blank=True,
        null=True
    )

    note = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    def get_company_display_thai(self):
        return dict(self.COMPANY_CHOICES).get(self.company)

    def get_status_display_thai(self):
        return dict(self.PERSON_STATUS_CHOICES).get(self.person_status)

    def is_returned(self):
        return self.person_status == 'home'

    def is_on_leave(self):
        return self.person_status == 'leave'

    def is_on_mission(self):
        return self.person_status == 'mission'

    def is_normal(self):
        return self.person_status == 'normal'

    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}"

    def __str__(self):
        return f"{self.full_name} ({self.get_company_display_thai()})"


class UserFaceProfile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='face_profile'
    )

    face_descriptor = models.TextField(
        blank=True,
        null=True
    )

    face_registered_at = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    def has_face_registered(self):
        return bool(self.face_descriptor)

    def __str__(self):
        return f"FaceProfile({self.user.username})"