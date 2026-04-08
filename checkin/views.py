import math
import json
import urllib.request
import urllib.error
from datetime import time

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt

import openpyxl

from .models import CheckInRecord


@csrf_exempt
def line_webhook(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body.decode('utf-8'))
            print("LINE EVENT:", body)
        except Exception as e:
            print("LINE WEBHOOK ERROR:", str(e))
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'message': 'ok'})


def calculate_distance(lat1, lon1, lat2, lon2):
    r = 6371000  # เมตร

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return r * c


def calculate_status(checkin_datetime):
    late_time = time(8, 30)
    local_time = timezone.localtime(checkin_datetime).time()
    return "late" if local_time > late_time else "present"


def get_return_status_summary():
    today = timezone.localdate()

    today_records = (
        CheckInRecord.objects
        .filter(created_at__date=today)
        .select_related('user')
        .order_by('user_id', '-created_at')
    )

    latest_by_user = {}
    for record in today_records:
        if record.user_id not in latest_by_user:
            latest_by_user[record.user_id] = record

    returned_users = []
    not_returned_users = []

    for _, record in latest_by_user.items():
        if record.action == 'checkin':
            returned_users.append(record)
        elif record.action == 'checkout':
            not_returned_users.append(record)

    return returned_users, not_returned_users


def build_line_summary_message(trigger_record=None):
    returned_users, not_returned_users = get_return_status_summary()

    returned_count = len(returned_users)
    not_returned_count = len(not_returned_users)

    now_local = timezone.localtime()
    deadline = now_local.replace(
        hour=getattr(settings, 'RETURN_DEADLINE_HOUR', 18),
        minute=getattr(settings, 'RETURN_DEADLINE_MINUTE', 0),
        second=0,
        microsecond=0,
    )

    lines = []

    if trigger_record:
        action_text = 'กลับเข้ากรม' if trigger_record.action == 'checkin' else 'ออกนอกกรม'
        lines.append("📢 มีการอัปเดตการเช็คชื่อ")
        lines.append(f"ชื่อ: {trigger_record.user.username}")
        lines.append(f"รายการ: {action_text}")
        lines.append(f"เวลา: {timezone.localtime(trigger_record.created_at).strftime('%H:%M:%S')}")
        lines.append("")

    lines.append(f"✅ กลับแล้ว: {returned_count} คน")
    lines.append(f"⏳ ยังไม่กลับ: {not_returned_count} คน")

    if not_returned_users:
        lines.append("")
        lines.append("รายชื่อที่ยังไม่กลับ:")
        for i, item in enumerate(not_returned_users[:20], start=1):
            out_time = timezone.localtime(item.created_at).strftime('%H:%M:%S')
            lines.append(f"{i}. {item.user.username} (ออก {out_time})")

        if len(not_returned_users) > 20:
            lines.append(f"... และอีก {len(not_returned_users) - 20} คน")

    if now_local > deadline and not_returned_count > 0:
        lines.append("")
        lines.append(
            f"🚨 เลยเวลากลับ {deadline.strftime('%H:%M')} แล้ว "
            f"แต่ยังมีผู้ที่ไม่กลับ {not_returned_count} คน"
        )

    return "\n".join(lines)


def send_line_push_message(message_text):
    channel_access_token = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '').strip()
    target_id = getattr(settings, 'LINE_TARGET_ID', '').strip()

    if not channel_access_token or not target_id:
        return False, "LINE settings not configured"

    url = "https://api.line.me/v2/bot/message/push"
    payload = json.dumps({
        "to": target_id,
        "messages": [
            {
                "type": "text",
                "text": message_text[:5000]
            }
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_access_token}",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return True, response.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = str(e)
        return False, detail
    except Exception as e:
        return False, str(e)


def notify_line_return_status(trigger_record=None):
    message_text = build_line_summary_message(trigger_record=trigger_record)
    cache_key = f"line_notify:{hash(message_text)}"

    if cache.get(cache_key):
        return False, "duplicate skipped"

    ok, result = send_line_push_message(message_text)

    if ok:
        cache.set(cache_key, True, timeout=60)

    return ok, result


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        context = {
            'first_name': first_name,
            'last_name': last_name,
            'username': username,
        }

        if not first_name or not last_name or not username or not password1 or not password2:
            context['error'] = 'กรุณากรอกข้อมูลให้ครบทุกช่อง'
            return render(request, 'register.html', context)

        if User.objects.filter(username=username).exists():
            context['error'] = 'Username นี้ถูกใช้งานแล้ว'
            return render(request, 'register.html', context)

        if password1 != password2:
            context['error'] = 'รหัสผ่านไม่ตรงกัน'
            return render(request, 'register.html', context)

        if len(password1) < 6:
            context['error'] = 'รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร'
            return render(request, 'register.html', context)

        User.objects.create_user(
            username=username,
            password=password1,
            first_name=first_name,
            last_name=last_name,
        )

        messages.success(request, 'สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ')
        return redirect('login')

    return render(request, 'register.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')

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

    data = CheckInRecord.objects.filter(user=request.user).select_related('user').order_by('-created_at')

    today_records = CheckInRecord.objects.filter(created_at__date=today)
    total_checkin = today_records.filter(action='checkin').count()
    late_count = today_records.filter(action='checkin', status='late').count()
    checkout_count = today_records.filter(action='checkout').count()

    total_users = User.objects.filter(is_superuser=False).count()
    users_checked_in_today = today_records.filter(action='checkin').values('user').distinct().count()
    not_checked_in = max(total_users - users_checked_in_today, 0)

    daily_stats = (
        CheckInRecord.objects
        .filter(action='checkin')
        .values('created_at__date')
        .annotate(total=Count('id'))
        .order_by('created_at__date')
    )

    labels = [str(item['created_at__date']) for item in daily_stats]
    values = [item['total'] for item in daily_stats]

    status_labels = ['มาปกติ', 'มาสาย']
    status_values = [
        CheckInRecord.objects.filter(action='checkin', status='present').count(),
        CheckInRecord.objects.filter(action='checkin', status='late').count(),
    ]

    returned_users, not_returned_users = get_return_status_summary()

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
        'returned_count': len(returned_users),
        'not_returned_count': len(not_returned_users),
    }

    return render(request, 'dashboard.html', context)


@login_required
def history_view(request):
    data = (
        CheckInRecord.objects
        .filter(user=request.user)
        .select_related('user')
        .order_by('-created_at')
    )
    return render(request, 'history.html', {'data': data})


@login_required
def checkin_view(request):
    office_lat = 13.819810075005167
    office_lon = 100.52961418065506
    allowed_radius = 500
    location_name = "จุดเช็คอินหลัก"

    context = {
        'office_lat': office_lat,
        'office_lon': office_lon,
        'allowed_radius': allowed_radius,
        'location_name': location_name,
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
    }

    if request.method == 'POST':
        action = request.POST.get('action')
        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')

        if action not in ['checkin', 'checkout']:
            context['error'] = 'รูปแบบการทำรายการไม่ถูกต้อง'
            return render(request, 'checkin.html', context)

        if not lat or not lon:
            context['error'] = 'กรุณาเปิด GPS ก่อนดำเนินการ'
            return render(request, 'checkin.html', context)

        try:
            lat = float(lat)
            lon = float(lon)
        except ValueError:
            context['error'] = 'ข้อมูลพิกัดไม่ถูกต้อง'
            return render(request, 'checkin.html', context)

        distance = calculate_distance(lat, lon, office_lat, office_lon)

        if distance > allowed_radius:
            context['error'] = f'❌ อยู่นอกพื้นที่ ({int(distance)} เมตร)'
            return render(request, 'checkin.html', context)

        now = timezone.now()
        today = timezone.localdate()

        if action == 'checkin':
            already_checked_in = CheckInRecord.objects.filter(
                user=request.user,
                action='checkin',
                created_at__date=today
            ).exists()

            if already_checked_in:
                context['error'] = '❗ วันนี้คุณเช็คอินแล้ว'
                return render(request, 'checkin.html', context)

            record = CheckInRecord.objects.create(
                user=request.user,
                action='checkin',
                latitude=lat,
                longitude=lon,
                distance=distance,
                status=calculate_status(now),
            )

            ok, result = notify_line_return_status(trigger_record=record)
            print("LINE PUSH CHECKIN:", ok, result)

            messages.success(request, '✅ เช็คอินสำเร็จ')
            return redirect('dashboard')

        today_checkin = CheckInRecord.objects.filter(
            user=request.user,
            action='checkin',
            created_at__date=today
        ).exists()

        today_checkout = CheckInRecord.objects.filter(
            user=request.user,
            action='checkout',
            created_at__date=today
        ).exists()

        if not today_checkin:
            context['error'] = '❗ กรุณาเช็คอินก่อนเช็คเอาต์'
            return render(request, 'checkin.html', context)

        if today_checkout:
            context['error'] = '❗ วันนี้คุณเช็คเอาต์แล้ว'
            return render(request, 'checkin.html', context)

        record = CheckInRecord.objects.create(
            user=request.user,
            action='checkout',
            latitude=lat,
            longitude=lon,
            distance=distance,
            status='present',
        )

        ok, result = notify_line_return_status(trigger_record=record)
        print("LINE PUSH CHECKOUT:", ok, result)

        messages.success(request, '✅ เช็คเอาต์สำเร็จ')
        return redirect('dashboard')

    return render(request, 'checkin.html', context)


@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        messages.error(request, 'คุณไม่มีสิทธิ์เข้าใช้งานหน้านี้')
        return redirect('dashboard')

    today = timezone.localdate()

    records = CheckInRecord.objects.select_related('user').order_by('-created_at')

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    date = request.GET.get('date', '').strip()
    action = request.GET.get('action', '').strip()

    if q:
        records = records.filter(
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q)
        )

    if status:
        records = records.filter(status=status)

    if action:
        records = records.filter(action=action)

    if date:
        records = records.filter(created_at__date=date)

    today_records = CheckInRecord.objects.filter(created_at__date=today)
    total_today = today_records.filter(action='checkin').count()
    late_today = today_records.filter(action='checkin', status='late').count()
    checkout_today = today_records.filter(action='checkout').count()
    total_users = User.objects.filter(is_superuser=False).count()
    checked_in_users_today = today_records.filter(action='checkin').values('user').distinct().count()
    absent_today = max(total_users - checked_in_users_today, 0)

    latest_record = today_records.order_by('-created_at').select_related('user').first()

    returned_users, not_returned_users = get_return_status_summary()

    now_local = timezone.localtime()
    deadline = now_local.replace(
        hour=getattr(settings, 'RETURN_DEADLINE_HOUR', 18),
        minute=getattr(settings, 'RETURN_DEADLINE_MINUTE', 0),
        second=0,
        microsecond=0,
    )
    show_return_alert = now_local > deadline and len(not_returned_users) > 0

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
        'action': action,
        'returned_count': len(returned_users),
        'not_returned_count': len(not_returned_users),
        'not_returned_users': not_returned_users,
        'show_return_alert': show_return_alert,
        'return_deadline': deadline.strftime('%H:%M'),
    }

    return render(request, 'admin_dashboard.html', context)


@login_required
def export_excel(request):
    if not request.user.is_staff:
        return redirect('dashboard')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Report"

    ws.append([
        'Username',
        'Date',
        'Time',
        'Action',
        'Latitude',
        'Longitude',
        'Distance (m)',
        'Status'
    ])

    records = CheckInRecord.objects.select_related('user').all().order_by('-created_at')

    for r in records:
        local_dt = timezone.localtime(r.created_at)
        ws.append([
            r.user.username,
            local_dt.strftime('%Y-%m-%d'),
            local_dt.strftime('%H:%M:%S'),
            r.action,
            r.latitude,
            r.longitude,
            round(r.distance, 2),
            r.status,
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=attendance.xlsx'

    wb.save(response)
    return response