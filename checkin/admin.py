from django.contrib import admin
from .models import (
    CheckInRecord,
    SystemSetting,
    UserProfile,
    UserFaceProfile
)


@admin.register(CheckInRecord)
class CheckInRecordAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'action',
        'status',
        'created_at',
        'distance'
    )

    list_filter = (
        'action',
        'status',
        'created_at'
    )

    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name'
    )


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = (
        'checkin_start_time',
        'late_time',
        'return_deadline',
        'updated_at'
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'phone_number',
        'company'
    )

    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name',
        'phone_number'
    )

    list_filter = (
        'company',
    )


@admin.register(UserFaceProfile)
class UserFaceProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'face_registered_at'
    )

    search_fields = (
        'user__username',
    )