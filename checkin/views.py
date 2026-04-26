import math
import os
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
from django.views.decorators.http import require_POST

import openpyxl

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import CheckInRecord, SystemSetting, UserFaceProfile, UserProfile


def is_valid_face_descriptor(descriptor):
    return (
        isinstance(descriptor, list)
        and len(descriptor) == 128
        and all(isinstance(x, (int, float)) for x in descriptor)
    )


def calculate_face_distance(desc1, desc2):
    try:
        total = 0
        for a, b in zip(desc1, desc2):
            total += (float(a) - float(b)) ** 2
        return math.sqrt(total)
    except Exception:
        return 999


def get_pdf_font():
    """
    โหลดฟอนต์ไทยสำหรับ PDF
    ต้องมีไฟล์ฟอนต์อยู่ที่:
    checkin/static/fonts/THSarabunNew.ttf
    """
    font_path = os.path.join(
        settings.BASE_DIR,
        'checkin',
        'static',
        'fonts',
        'THSarabunNew.ttf'
    )

    try:
        pdfmetrics.registerFont(TTFont("ThaiFont", font_path))
        return "ThaiFont"
    except Exception as e:
        print("โหลดฟอนต์ไทยไม่สำเร็จ:", e)
        return "Helvetica"


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


def get_system_setting():
    setting = SystemSetting.objects.first()
    if not setting:
        setting = SystemSetting.objects.create(
            checkin_start_time='08:00',
            late_time='08:30',
            return_deadline='18:00',
        )
    return setting


def calculate_distance(lat1, lon1, lat2, lon2):
    r = 6371000

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return r * c


def calculate_status(checkin_datetime):
    setting = get_system_setting()
    local_time = timezone.localtime(checkin_datetime).time()
    return "late" if local_time > setting.late_time else "present"


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
    today = timezone.localdate()
    now_local = timezone.localtime()
    system_setting = get_system_setting()

    deadline = now_local.replace(
        hour=system_setting.return_deadline.hour,
        minute=system_setting.return_deadline.minute,
        second=0,
        microsecond=0,
    )

    # ใช้เฉพาะผู้ใช้จริงเท่านั้น ไม่เอา admin / staff / superuser / user ที่ปิดใช้งาน
    real_users = User.objects.filter(
        is_superuser=False,
        is_staff=False,
        is_active=True,
    )

    checked_in_user_ids = (
        CheckInRecord.objects
        .filter(
            action='checkin',
            created_at__date=today,
            user__is_superuser=False,
            user__is_staff=False,
            user__is_active=True,
        )
        .values_list('user_id', flat=True)
        .distinct()
    )

    checked_in_user_ids_set = set(checked_in_user_ids)
    checked_count = len(checked_in_user_ids_set)

    not_checkedin_users = (
        real_users
        .exclude(id__in=checked_in_user_ids_set)
        .order_by('username')
    )

    not_checked_count = not_checkedin_users.count()

    lines = []

    # ก่อนถึงเวลากำหนด: ตอนเช็คอินให้แจ้งจำนวนรวมเหมือนเดิม
    if now_local <= deadline:
        if trigger_record:
            action_text = 'เช็คอินแล้ว' if trigger_record.action == 'checkin' else 'เช็คเอาต์แล้ว'
            lines.append("📢 มีการอัปเดตการเช็คชื่อ")
            lines.append(f"ชื่อ: {trigger_record.user.username}")
            lines.append(f"รายการ: {action_text}")
            lines.append(f"เวลา: {timezone.localtime(trigger_record.created_at).strftime('%H:%M:%S')}")
            lines.append("")

        lines.append(f"✅ เช็คอินแล้ว: {checked_count} คน")
        lines.append(f"⏳ ยังไม่มา: {not_checked_count} คน")
        lines.append(f"⏰ เวลากำหนด: {deadline.strftime('%H:%M')} น.")

        return "\n".join(lines)

    # หลังเลยเวลากำหนด: แจ้งรายชื่อคนที่ยังไม่มา พร้อมเบอร์โทร
    lines.append("🚨 เลยเวลากลับเข้ากรมแล้ว")
    lines.append(f"เวลากำหนด: {deadline.strftime('%H:%M')} น.")
    lines.append(f"เวลาอัปเดต: {now_local.strftime('%H:%M:%S')}")
    lines.append("")
    lines.append(f"✅ เช็คอินแล้ว: {checked_count} คน")
    lines.append(f"❌ ยังไม่มา: {not_checked_count} คน")
    lines.append("")

    if not_checkedin_users.exists():
        lines.append("รายชื่อคนที่ยังไม่มา / ยังไม่เช็คอิน:")
        for i, user in enumerate(not_checkedin_users, start=1):
            profile = getattr(user, 'userprofile', None)
            phone = profile.phone_number if profile and profile.phone_number else "-"

            full_name = f"{user.first_name} {user.last_name}".strip()
            if not full_name:
                full_name = user.username

            lines.append(f"{i}. {full_name}")
            lines.append(f"   เบอร์โทร: {phone}")
    else:
        lines.append("✅ ทุกคนเช็คอินครบแล้ว")

    return "\n".join(lines)

def send_line_push_message(message_text):
    channel_access_token = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '').strip()
    target_id = getattr(settings, 'LINE_TARGET_ID', '').strip()

    if not channel_access_token or not target_id:
        return False, "LINE settings not configured"

    url = "https://api.line.me/v2/bot/message/push"
    payload = json.dumps({
        "to": target_id,
        "messages": [{"type": "text", "text": message_text[:5000]}]
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
        phone_number = request.POST.get('phone_number', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        context = {
            'first_name': first_name,
            'last_name': last_name,
            'username': username,
            'phone_number': phone_number,
        }

        if not first_name or not last_name or not username or not phone_number or not password1 or not password2:
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

        user = User.objects.create_user(
            username=username,
            password=password1,
            first_name=first_name,
            last_name=last_name,
        )

        UserProfile.objects.create(
            user=user,
            phone_number=phone_number,
        )

        UserFaceProfile.objects.get_or_create(user=user)
        login(request, user)
        messages.success(request, 'สมัครสมาชิกสำเร็จ กรุณาลงทะเบียนใบหน้าก่อนใช้งาน')
        return redirect('face_register')

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

            face_profile, _ = UserFaceProfile.objects.get_or_create(user=user)
            if not face_profile.face_descriptor:
                messages.warning(request, 'กรุณาลงทะเบียนใบหน้าก่อนใช้งาน')
                return redirect('face_register')

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

    total_users = User.objects.filter(is_superuser=False, is_staff=False, is_active=True).count()
    users_checked_in_today = today_records.filter(action='checkin', user__is_superuser=False, user__is_staff=False, user__is_active=True).values('user').distinct().count()
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
def profile_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    latest_record = (
        CheckInRecord.objects
        .filter(user=user)
        .select_related('user')
        .order_by('-created_at')
        .first()
    )

    total_checkin = CheckInRecord.objects.filter(user=user, action='checkin').count()
    total_checkout = CheckInRecord.objects.filter(user=user, action='checkout').count()

    today = timezone.localdate()
    today_record = (
        CheckInRecord.objects
        .filter(user=user, created_at__date=today)
        .order_by('-created_at')
        .first()
    )

    context = {
        'profile_user': user,
        'profile': profile,
        'latest_record': latest_record,
        'total_checkin': total_checkin,
        'total_checkout': total_checkout,
        'today_record': today_record,
    }

    return render(request, 'profile.html', context)


@login_required
def face_register_page(request):
    profile, _ = UserFaceProfile.objects.get_or_create(user=request.user)
    context = {
        'has_face_registered': bool(profile.face_descriptor),
    }
    return render(request, 'face_register.html', context)


@login_required
@require_POST
def save_face_descriptor(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        descriptor = data.get('descriptor')

        if not is_valid_face_descriptor(descriptor):
            return JsonResponse({
                'success': False,
                'message': 'ข้อมูลใบหน้าไม่ถูกต้อง กรุณาสแกนใหม่อีกครั้ง',
                'error': 'ข้อมูลใบหน้าไม่ถูกต้อง กรุณาสแกนใหม่อีกครั้ง'
            }, status=400)

        profile, _ = UserFaceProfile.objects.get_or_create(user=request.user)

        if profile.face_descriptor:
            return JsonResponse({
                'success': False,
                'message': 'บัญชีนี้ลงทะเบียนใบหน้าไว้แล้ว ไม่สามารถลงทะเบียนซ้ำได้',
                'error': 'บัญชีนี้ลงทะเบียนใบหน้าไว้แล้ว ไม่สามารถลงทะเบียนซ้ำได้'
            }, status=400)

        duplicate_threshold = 0.45
        other_profiles = (
            UserFaceProfile.objects
            .exclude(user=request.user)
            .exclude(face_descriptor__isnull=True)
            .exclude(face_descriptor='')
            .select_related('user')
        )

        for other_profile in other_profiles:
            try:
                old_descriptor = json.loads(other_profile.face_descriptor)

                if not is_valid_face_descriptor(old_descriptor):
                    continue

                distance = calculate_face_distance(descriptor, old_descriptor)

                if distance < duplicate_threshold:
                    return JsonResponse({
                        'success': False,
                        'message': 'ใบหน้านี้ถูกลงทะเบียนกับบัญชีอื่นแล้ว ไม่สามารถใช้ซ้ำได้',
                        'error': 'ใบหน้านี้ถูกลงทะเบียนกับบัญชีอื่นแล้ว ไม่สามารถใช้ซ้ำได้'
                    }, status=400)

            except Exception:
                continue

        profile.face_descriptor = json.dumps(descriptor)
        profile.face_registered_at = timezone.now()
        profile.save()

        return JsonResponse({
            'success': True,
            'message': 'บันทึกใบหน้าเรียบร้อยแล้ว'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e),
            'error': str(e)
        }, status=400)


@login_required
def face_verify_page(request):
    profile, _ = UserFaceProfile.objects.get_or_create(user=request.user)
    has_face_registered = bool(profile.face_descriptor)

    context = {
        'has_face_registered': has_face_registered,
        'saved_descriptor': profile.face_descriptor if profile.face_descriptor else '[]',
    }
    return render(request, 'face_verify.html', context)


@login_required
def checkin_view(request):
    office_lat = 13.819810075005167
    office_lon = 100.52961418065506
    allowed_radius = 500
    location_name = "จุดเช็คอินหลัก"

    face_profile, _ = UserFaceProfile.objects.get_or_create(user=request.user)

    if not face_profile.face_descriptor:
        messages.warning(request, 'กรุณาลงทะเบียนใบหน้าก่อนเช็คอิน')
        return redirect('face_register')

    context = {
        'office_lat': office_lat,
        'office_lon': office_lon,
        'allowed_radius': allowed_radius,
        'location_name': location_name,
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'has_face_registered': bool(face_profile.face_descriptor),
        'saved_descriptor': face_profile.face_descriptor if face_profile.face_descriptor else '[]',
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
def time_settings_view(request):
    if not request.user.is_staff:
        messages.error(request, 'คุณไม่มีสิทธิ์เข้าใช้งานหน้านี้')
        return redirect('dashboard')

    setting = get_system_setting()

    if request.method == 'POST':
        checkin_start_time = request.POST.get('checkin_start_time')
        late_time = request.POST.get('late_time')
        return_deadline = request.POST.get('return_deadline')

        if not checkin_start_time or not late_time or not return_deadline:
            messages.error(request, 'กรุณากรอกเวลาให้ครบทุกช่อง')
            return render(request, 'time_settings.html', {'setting': setting})

        setting.checkin_start_time = checkin_start_time
        setting.late_time = late_time
        setting.return_deadline = return_deadline
        setting.save()

        messages.success(request, 'บันทึกการตั้งค่าเวลาเรียบร้อยแล้ว')
        return redirect('time_settings')

    return render(request, 'time_settings.html', {'setting': setting})


@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        messages.error(request, 'คุณไม่มีสิทธิ์เข้าใช้งานหน้านี้')
        return redirect('dashboard')

    today = timezone.localdate()
    system_setting = get_system_setting()

    checked_in_user_ids = (
        CheckInRecord.objects
        .filter(action='checkin', created_at__date=today)
        .values_list('user_id', flat=True)
        .distinct()
    )

    not_checkedin_users = (
        User.objects
        .filter(is_superuser=False, is_staff=False, is_active=True)
        .exclude(id__in=checked_in_user_ids)
        .order_by('username')
    )

    now_local = timezone.localtime()
    deadline = now_local.replace(
        hour=system_setting.return_deadline.hour,
        minute=system_setting.return_deadline.minute,
        second=0,
        microsecond=0,
    )

    context = {
        'not_checkedin_users': not_checkedin_users,
        'system_setting': system_setting,
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
        'ชื่อผู้ใช้',
        'ชื่อ-นามสกุล',
        'เบอร์โทร',
        'วันที่',
        'เวลา',
        'ประเภท',
        'ละติจูด',
        'ลองจิจูด',
        'ระยะทาง (เมตร)',
        'สถานะ'
    ])

    records = CheckInRecord.objects.select_related('user').all().order_by('-created_at')

    for r in records:
        local_dt = timezone.localtime(r.created_at)
        action_text = "เข้างาน" if r.action == "checkin" else "ออกงาน"
        status_text = "มาสาย" if r.status == "late" else "ปกติ"

        full_name = f"{r.user.first_name} {r.user.last_name}".strip() or "-"
        profile = getattr(r.user, 'userprofile', None)
        phone_number = profile.phone_number if profile and profile.phone_number else "-"

        ws.append([
            r.user.username,
            full_name,
            phone_number,
            local_dt.strftime('%d/%m/%Y'),
            local_dt.strftime('%H:%M:%S'),
            action_text,
            r.latitude,
            r.longitude,
            round(r.distance, 2),
            status_text,
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=attendance.xlsx'

    wb.save(response)
    return response


@login_required
def export_pdf(request):
    if not request.user.is_staff:
        return redirect('dashboard')

    font_name = get_pdf_font()
    today = timezone.localdate()

    checked_in_user_ids = (
        CheckInRecord.objects
        .filter(action='checkin', created_at__date=today)
        .values_list('user_id', flat=True)
        .distinct()
    )

    not_checkedin_users = (
        User.objects
        .filter(is_superuser=False, is_staff=False, is_active=True)
        .exclude(id__in=checked_in_user_ids)
        .order_by('username')
    )

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=not_checkedin_report.pdf'

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        rightMargin=1 * cm,
        leftMargin=1 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )

    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ThaiTitle',
        parent=styles['Title'],
        fontName=font_name,
        fontSize=24,
        leading=28,
        alignment=1,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        'ThaiSubtitle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=13,
        leading=16,
        alignment=1,
        textColor=colors.HexColor('#475569'),
        spaceAfter=16,
    )

    generated_at = timezone.localtime().strftime('%d/%m/%Y %H:%M:%S')

    elements.append(Paragraph("รายงานรายชื่อผู้ที่ยังไม่มา / ยังไม่เช็คอิน", title_style))
    elements.append(Paragraph(f"วันที่ออกรายงาน: {generated_at}", subtitle_style))
    elements.append(Spacer(1, 10))

    data = [[
        'ลำดับ',
        'ชื่อผู้ใช้',
        'ชื่อ',
        'นามสกุล',
        'เบอร์โทร',
        'สถานะ',
    ]]

    for index, user in enumerate(not_checkedin_users, start=1):
        profile = getattr(user, 'userprofile', None)
        phone_number = profile.phone_number if profile and profile.phone_number else "-"

        data.append([
            str(index),
            user.username,
            user.first_name or "-",
            user.last_name or "-",
            phone_number,
            "ยังไม่เช็คอิน",
        ])

    if len(data) == 1:
        data.append(['-', '-', '-', '-', '-', 'ทุกคนเช็คอินแล้ว'])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[
            2 * cm,
            5 * cm,
            5 * cm,
            5 * cm,
            4 * cm,
            5 * cm,
        ],
    )

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),

        ('FONTNAME', (0, 1), (-1, -1), font_name),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#111827')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor('#f8fafc')
        ]),

        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))

    elements.append(table)
    doc.build(elements)

    return response
