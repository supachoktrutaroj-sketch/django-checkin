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

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)

    latitude = models.FloatField()
    longitude = models.FloatField()
    distance = models.FloatField(default=0)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='present'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.created_at:%Y-%m-%d %H:%M:%S}"


class SystemSetting(models.Model):
    checkin_start_time = models.TimeField(default='08:00')
    late_time = models.TimeField(default='08:30')
    return_deadline = models.TimeField(default='18:00')

    updated_at = models.DateTimeField(auto_now=True)

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

    def get_company_display_thai(self):
        return dict(self.COMPANY_CHOICES).get(self.company)

    def __str__(self):
        return f"{self.user.username} - {self.get_company_display_thai()}"


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

    def __str__(self):
        return f"FaceProfile({self.user.username})"