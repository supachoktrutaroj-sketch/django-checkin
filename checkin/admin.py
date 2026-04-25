from django.contrib import admin
from .models import CheckInRecord, SystemSetting


@admin.register(CheckInRecord)
class CheckInRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'status', 'created_at', 'distance')
    list_filter = ('action', 'status', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('checkin_start_time', 'late_time', 'return_deadline', 'updated_at')