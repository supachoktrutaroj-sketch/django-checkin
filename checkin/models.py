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

    distance_meters = models.FloatField(
        default=0
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='present'
    )

    verification_method = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default='face'
    )

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

    # 🟢 1. เอา 'กองร้อยกองบังคับการ' ออก เหลือเพียง กองร้อย 1-5 อย่างเป็นทางการครับ
    COMPANY_CHOICES = [
        ('1', 'กองร้อยที่ 1'),
        ('2', 'กองร้อยที่ 2'),
        ('3', 'กองร้อยที่ 3'),
        ('4', 'กองร้อยที่ 4'),
        ('5', 'กองร้อยที่ 5'), 
    ]

    PERSON_STATUS_CHOICES = [
        ('normal', 'ปกติ (อยู่ในค่าย)'),
        ('leave', 'ลาพัก'),
        ('mission', 'ไปราชการ'),
        ('official', 'ปฏิบัติภารกิจนอกค่าย'),
        ('home', 'กลับบ้าน / ออกกรม'),
    ]

    RETURN_STATUS_CHOICES = [
        ('PENDING', 'ยังไม่รายงานตัว ⏳'),
        ('ON_TIME', 'กลับทันเวลา ✅'),
        ('LATE', 'กลับไม่ทันเวลา ❌'),
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

    # 🟢 2. เปลี่ยนค่า default เป็น '1' (เพราะเอา บก. ออกแล้ว) และขยาย max_length เผื่อรองรับข้อความเก่า
    company = models.CharField(
        max_length=50,
        choices=COMPANY_CHOICES,
        default='1'
    )

    person_status = models.CharField(
        max_length=20,
        choices=PERSON_STATUS_CHOICES,
        default='normal'
    )

    start_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="วันที่เริ่มต้นออกกรม"
    )

    individual_return_deadline = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="วันและเวลากลับเข้ากรมรายบุคคล"
    )

    return_status = models.CharField(
        max_length=20,
        choices=RETURN_STATUS_CHOICES,
        default='PENDING',
        verbose_name="สถานะการกลับรายงานตัว"
    )

    note = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    # 🟢 3. เคลียร์ฟังก์ชันแสดงผลภาษาไทย ให้คลีนและกรองได้แม่นยำขึ้น ดักจับค่าเดิมให้เปลี่ยนเป็น กองร้อยที่ 1-5 ทั้งหมด
    def get_company_display_thai(self):
        if self.company:
            # ดักจับกลุ่มกองร้อย 5 (สนับสนุนเดิม)
            if self.company in ['5', 'กองร้อยสนับสนุน', 'สนน.', 'สนน']:
                return "กองร้อยที่ 5"
            # ดักจับกลุ่มเลขเดี่ยว
            if self.company == '1': return "กองร้อยที่ 1"
            if self.company == '2': return "กองร้อยที่ 2"
            if self.company == '3': return "กองร้อยที่ 3"
            if self.company == '4': return "กองร้อยที่ 4"
            
            # หากใน DB มีข้อความภาษาไทยเดิมหลงเหลืออยู่ ให้ดึงจากเงื่อนไขตามตัวเลือก หรือแสดงตามจริง
            if self.company in dict(self.COMPANY_CHOICES):
                return dict(self.COMPANY_CHOICES).get(self.company)
            return self.company
        return "-"

    def get_status_display_thai(self):
        if self.person_status and self.person_status in dict(self.PERSON_STATUS_CHOICES):
            return dict(self.PERSON_STATUS_CHOICES).get(self.person_status)
        return "ปกติ"

    def get_return_status_display_thai(self):
        if self.return_status and self.return_status in dict(self.RETURN_STATUS_CHOICES):
            return dict(self.RETURN_STATUS_CHOICES).get(self.return_status)
        return "ยังไม่รายงานตัว ⏳"

    def get_days_remaining(self):
        from datetime import date

        if self.individual_return_deadline:
            target_date = self.individual_return_deadline.date()
            today = date.today()
            delta = target_date - today

            if delta.days > 0:
                return f"เหลืออีก {delta.days} วัน"
            elif delta.days == 0:
                return "ครบกำหนดกลับวันนี้"
            else:
                return f"เกินกำหนด {abs(delta.days)} วัน"

        return "-"

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
        if self.user.first_name or self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}".strip()

        return self.user.username

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