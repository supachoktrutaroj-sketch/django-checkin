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
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='present')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.created_at:%Y-%m-%d %H:%M:%S}"