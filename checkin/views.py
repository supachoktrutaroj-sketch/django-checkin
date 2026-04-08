import math
import json
from datetime import time

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import HttpResponse

import openpyxl

from .models import Attendance


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # เมตร

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def calculate_status(checkin_datetime):
    late_time = time(8, 30)  # 08:30
    local_time = timezone.localtime(checkin_datetime).time()

    if local_time > late_time:
        return 'late'
    return 'present'


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'login.html', {
                'error': 'Username หรือ Password ไม่ถูกต้อง'
            })

    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def home(request):
    return redirect('dashboard')


@login_required
def dashboard(request):
    today = timezone.localdate()

    data = Attendance.objects.filter(user=request.user).order_by('-date', '-check_in_time')

    today_records = Attendance.objects.filter(date=today)
    total_checkin = today_records.filter(check_in_time__isnull=False).count()
    late_count = today_records.filter(status='late').count()
    checkout_count = today_records.filter(check_out_time__isnull=False).count()

    total_users = User.objects.filter(is_superuser=False).count()
    not_checked_in = max(total_users - total_checkin, 0)

    daily_stats = (
        Attendance.objects
        .filter(check_in_time__isnull=False)
        .values('date')
        .annotate(total=Count('id'))
        .order_by('date')
    )

    labels = [str(item['date']) for item in daily_stats]
    values = [item['total'] for item in daily_stats]

    status_labels = ['มาปกติ', 'มาสาย']
    status_values = [
        Attendance.objects.filter(status='present').count(),
        Attendance.objects.filter(status='late').count(),
    ]

    context = {
        'data': data,
        'total_checkin': total_checkin,
        'late_count': late_count,
        'checkout_count': checkout_count,
        'not_checked_in': not_checked_in,
        'labels': json.dumps(labels),
        'values': json.dumps(values),
        'status_labels': json.dumps(status_labels),
        'status_values': json.dumps(status_values),
    }

    return render(request, 'dashboard.html', context)


@login_required
def history_view(request):
    data = Attendance.objects.filter(user=request.user).order_by('-date', '-check_in_time')
    return render(request, 'history.html', {'data': data})


@login_required
def checkin_view(request):
    office_lat = 13.819893421028778 
    office_lon = 100.52994677455986
    allowed_radius = 500
    location_name = "จุดเช็คอินหลัก"

    if request.method == 'POST':
        action = request.POST.get('action')
        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')

        if not lat or not lon:
            return render(request, 'checkin.html', {
                'error': 'กรุณาเปิด GPS ก่อนดำเนินการ',
                'office_lat': office_lat,
                'office_lon': office_lon,
                'allowed_radius': allowed_radius,
                'location_name': location_name,
            })

        distance = calculate_distance(lat, lon, office_lat, office_lon)

        if distance > allowed_radius:
            return render(request, 'checkin.html', {
                'error': f'❌ อยู่นอกพื้นที่ ({int(distance)} เมตร)',
                'office_lat': office_lat,
                'office_lon': office_lon,
                'allowed_radius': allowed_radius,
                'location_name': location_name,
            })

        today = timezone.localdate()
        now = timezone.now()

        attendance, created = Attendance.objects.get_or_create(
            user=request.user,
            date=today
        )

        if action == 'checkin':
            if attendance.check_in_time:
                return render(request, 'checkin.html', {
                    'error': '❗ วันนี้คุณเช็คอินแล้ว',
                    'office_lat': office_lat,
                    'office_lon': office_lon,
                    'allowed_radius': allowed_radius,
                    'location_name': location_name,
                })

            attendance.check_in_time = now
            attendance.latitude = float(lat)
            attendance.longitude = float(lon)
            attendance.status = calculate_status(now)
            attendance.save()

            messages.success(request, '✅ เช็คอินสำเร็จ')
            return redirect('dashboard')

        elif action == 'checkout':
            if not attendance.check_in_time:
                return render(request, 'checkin.html', {
                    'error': '❗ กรุณาเช็คอินก่อนเช็คเอาต์',
                    'office_lat': office_lat,
                    'office_lon': office_lon,
                    'allowed_radius': allowed_radius,
                    'location_name': location_name,
                })

            if attendance.check_out_time:
                return render(request, 'checkin.html', {
                    'error': '❗ วันนี้คุณเช็คเอาต์แล้ว',
                    'office_lat': office_lat,
                    'office_lon': office_lon,
                    'allowed_radius': allowed_radius,
                    'location_name': location_name,
                })

            attendance.check_out_time = now
            attendance.save()

            messages.success(request, '✅ เช็คเอาต์สำเร็จ')
            return redirect('dashboard')

    return render(request, 'checkin.html', {
        'office_lat': office_lat,
        'office_lon': office_lon,
        'allowed_radius': allowed_radius,
        'location_name': location_name,
    })


@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        messages.error(request, 'คุณไม่มีสิทธิ์เข้าใช้งานหน้านี้')
        return redirect('dashboard')

    today = timezone.localdate()

    records = Attendance.objects.select_related('user').order_by('-date', '-check_in_time')

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    date = request.GET.get('date', '').strip()

    if q:
        records = records.filter(
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q)
        )

    if status:
        records = records.filter(status=status)

    if date:
        records = records.filter(date=date)

    today_records = Attendance.objects.filter(date=today)
    total_today = today_records.count()
    late_today = today_records.filter(status='late').count()
    checkout_today = today_records.filter(check_out_time__isnull=False).count()
    total_users = User.objects.filter(is_superuser=False).count()
    absent_today = max(total_users - total_today, 0)

    latest_record = today_records.order_by('-check_in_time').select_related('user').first()

    context = {
        'records': records,
        'total_today': total_today,
        'late_today': late_today,
        'checkout_today': checkout_today,
        'absent_today': absent_today,
        'latest_record': latest_record,
        'q': q,
        'status': status,
        'date': date,
    }

    return render(request, 'admin_dashboard.html', context)


@login_required
def export_excel(request):
    if not request.user.is_staff:
        return redirect('dashboard')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Report"

    ws.append(['Username', 'Date', 'Check In', 'Check Out', 'Status'])

    records = Attendance.objects.select_related('user').all().order_by('-date', '-check_in_time')

    for r in records:
        ws.append([
            r.user.username,
            str(r.date),
            str(r.check_in_time or ''),
            str(r.check_out_time or ''),
            r.get_status_display()
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=attendance.xlsx'

    wb.save(response)
    return response