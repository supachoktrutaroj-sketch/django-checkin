from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

from .models import (
    CheckInRecord,
    SystemSetting,
    UserProfile,
    UserFaceProfile
)


@admin.register(CheckInRecord)
class CheckInRecordAdmin(admin.ModelAdmin):

    # 🛠️ แก้ไข: เปลี่ยน 'distance' เป็น 'distance_meters' และเพิ่มฟิลด์ตรวจสอบสแกนใบหน้าลงหน้า Admin
    list_display = (
        'user',
        'action',
        'status',
        'distance_meters',
        'verification_method',
        'confidence_score',
        'created_at'
    )

    list_filter = (
        'action',
        'status',
        'verification_method',
        'created_at'
    )

    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name'
    )

    ordering = (
        '-created_at',
    )


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):

    list_display = (
        'checkin_start_time',
        'late_time',
        'return_deadline',
        'updated_at'
    )


class UserProfileInline(admin.StackedInline):

    model = UserProfile

    extra = 0

    can_delete = False

    fields = (
        'phone_number',
        'company',
        'person_status',
        'return_date',
        'note',
        'created_at'
    )

    readonly_fields = (
        'created_at',
    )


class UserFaceProfileInline(admin.StackedInline):

    model = UserFaceProfile

    extra = 0

    can_delete = False

    fields = (
        'face_registered_at',
        'created_at'
    )

    readonly_fields = (
        'face_registered_at',
        'created_at'
    )


class CustomUserAdmin(UserAdmin):

    inlines = (
        UserProfileInline,
        UserFaceProfileInline
    )

    list_display = (
        'username',
        'first_name',
        'last_name',
        'is_staff',
        'is_active'
    )

    search_fields = (
        'username',
        'first_name',
        'last_name'
    )

    list_filter = (
        'is_staff',
        'is_superuser',
        'is_active'
    )


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'phone_number',
        'company',
        'person_status',
        'return_date',
        'created_at'
    )

    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name',
        'phone_number'
    )

    list_filter = (
        'company',
        'person_status'
    )

    ordering = (
        'company',
        'user__first_name'
    )


@admin.register(UserFaceProfile)
class UserFaceProfileAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'face_registered_at',
        'created_at'
    )

    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name'
    )

    ordering = (
        '-created_at',
    )