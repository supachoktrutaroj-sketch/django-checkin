import os
import json
import math
import urllib.request
import urllib.error
from datetime import time, datetime

from django.db.models import Q, Count
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test


import openpyxl

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import CheckInRecord, SystemSetting, UserFaceProfile, UserProfile


# ====================================================
#  ระบบตรวจสอบสิทธิ์และฟังก์ชันตัวช่วย (Helpers)
# ====================================================

def is_admin_or_staff(user):
    """ ตรวจสอบว่าผู้ใช้มีสิทธิ์ของแอดมินหรือเจ้าหน้าที่หรือไม่ """
    return user.is_authenticated and (user.is_staff or user.is_superuser)


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
    
    late_time_setting = setting.late_time
    if isinstance(late_time_setting, str):
        try:
            late_time_setting = datetime.strptime(late_time_setting, '%H:%M').time()
        except ValueError:
            late_time_setting = datetime.strptime(late_time_setting, '%H:%M:%S').time()
            
    return "late" if local_time > late_time_setting else "present"


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

    deadline_setting = system_setting.return_deadline
    if isinstance(deadline_setting, str):
        dt_parsed = datetime.strptime(deadline_setting, '%H:%M')
        deadline_hour, deadline_minute = dt_parsed.hour, dt_parsed.minute
    else:
        deadline_hour, deadline_minute = deadline_setting.hour, deadline_setting.minute

    deadline = now_local.replace(
        hour=deadline_hour,
        minute=deadline_minute,
        second=0,
        microsecond=0,
    )

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
            # 🛠️ แก้ไขจุดนี้: เปลี่ยนจาก 'userprofile' -> 'profile' ให้ถูกต้องตามโมเดล
            profile = getattr(user, 'profile', None)
            phone = profile.phone_number if profile and profile.phone_number else "-"
            full_name = f"{user.first_name} {user.last_name}".strip() or user.username

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


# ====================================================
#  ระบบลงทะเบียนและเข้าสู่ระบบ (Authentication)
# ====================================================

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        company = request.POST.get('company', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        context = {
            'first_name': first_name,
            'last_name': last_name,
            'username': username,
            'phone_number': phone_number,
            'company': company,
        }

        if not all([first_name, last_name, username, phone_number, company, password1, password2]):
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
            company=company,
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
            if user.is_superuser:
                return redirect('dashboard')

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


# ====================================================
#  ระบบแสดงผล Dashboard และประวัติ (User Side)
# ====================================================

@login_required
def dashboard(request):
    today = timezone.localdate()
    raw_data = CheckInRecord.objects.filter(user=request.user).select_related('user').order_by('-created_at')
    
    for item in raw_data:
        if item.action == 'checkin':
            item.action_badge = "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300"
            item.action_icon = "fa-sign-in-alt"
        else:
            item.action_badge = "bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-300"
            item.action_icon = "fa-sign-out-alt"
            
        if item.status == 'present':
            item.status_badge = "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300"
        elif item.status == 'late':
            item.status_badge = "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300"
        else:
            item.status_badge = "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300"

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

    status_labels = ['มาปกติ (คน)', 'มาสาย (คน)']
    status_values = [
        today_records.filter(action='checkin', status='present').count(),
        today_records.filter(action='checkin', status='late').count(),
    ]

    returned_users, not_returned_users = get_return_status_summary()

    context = {
        'data': raw_data,
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
    data = CheckInRecord.objects.filter(user=request.user).select_related('user').order_by('-created_at')
    
    for item in data:
        item.badge_class = "bg-green-100 text-green-800 text-xs font-medium px-2.5 py-0.5 rounded-full" if item.action == 'checkin' else "bg-red-100 text-red-800 text-xs font-medium px-2.5 py-0.5 rounded-full"
        item.status_class = "bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded" if item.status == 'present' else "bg-amber-100 text-amber-800 text-xs font-medium px-2.5 py-0.5 rounded"
        
    return render(request, 'history.html', {'data': data})


@login_required
def profile_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    latest_record = CheckInRecord.objects.filter(user=user).select_related('user').order_by('-created_at').first()
    total_checkin = CheckInRecord.objects.filter(user=user, action='checkin').count()
    total_checkout = CheckInRecord.objects.filter(user=user, action='checkout').count()

    today = timezone.localdate()
    today_record = CheckInRecord.objects.filter(user=user, created_at__date=today).order_by('-created_at').first()

    context = {
        'profile_user': user,
        'profile': profile,
        'latest_record': latest_record,
        'total_checkin': total_checkin,
        'total_checkout': total_checkout,
        'today_record': today_record,
    }
    return render(request, 'profile.html', context)


# ====================================================
#  ระบบจัดการและตรวจจับใบหน้า (Face Recognition)
# ====================================================

@login_required
def face_register_page(request):
    if request.user.is_superuser:
        messages.info(request, 'สิทธิ์ Super Admin ไม่จำเป็นต้องลงทะเบียนใบหน้า')
        return redirect('dashboard')

    profile, _ = UserFaceProfile.objects.get_or_create(user=request.user)
    context = {
        'has_face_registered': bool(profile.face_descriptor),
    }
    return render(request, 'face_register.html', context)


@login_required
@require_POST
def save_face_descriptor(request):
    if request.user.is_superuser:
        return JsonResponse({
            'success': False,
            'message': 'สิทธิ์ Super Admin ไม่จำเป็นต้องลงทะเบียนใบหน้า',
            'error': 'สิทธิ์ Super Admin ไม่จำเป็นต้องลงทะเบียนใบหน้า'
        }, status=400)

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

        return JsonResponse({'success': True, 'message': 'บันทึกใบหน้าเรียบร้อยแล้ว'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e), 'error': str(e)}, status=400)


@login_required
def face_verify_page(request):
    if request.user.is_superuser:
        messages.info(request, 'สิทธิ์ Super Admin ไม่จำเป็นต้องสแกนใบหน้า')
        return redirect('dashboard')

    profile, _ = UserFaceProfile.objects.get_or_create(user=request.user)
    context = {
        'has_face_registered': bool(profile.face_descriptor),
        'saved_descriptor': profile.face_descriptor if profile.face_descriptor else '[]',
    }
    return render(request, 'face_verify.html', context)


# ====================================================
#  ระบบเช็คอิน / เช็คเอาต์ และตำแหน่งที่ตั้ง (GPS Check-In)
# ====================================================

@login_required
def checkin_view(request):
    """ หน้าเช็คอินและบันทึกพิกัด GPS (รองรับการโหลดหน้า และการรับค่า PUSH/POST มาบันทึก) """
    office_lat = 13.819810075005167
    office_lon = 100.52961418065506
    allowed_radius = 600
    location_name = "จุดบริการกำลังพล"

    # ====================================================
    #  ส่วนที่ 1: รองรับการส่งข้อมูลกลับมาบันทึก (POST)
    # ====================================================
    if request.method == 'POST':
        user_lat = request.POST.get('latitude')
        user_lon = request.POST.get('longitude')
        action = request.POST.get('action')  # 'checkin' หรือ 'checkout'
        verification_method = request.POST.get('verification_method', 'face_recognition')
        confidence_score = request.POST.get('confidence_score', '0.0')

        # ตรวจสอบความครบถ้วนของข้อมูลพิกัด
        if not user_lat or not user_lon:
            messages.error(request, 'ไม่สามารถบันทึกได้เนื่องจากระบบตรวจไม่พบพิกัด GPS จริงของคุณ')
            return redirect('checkin')

        try:
            # คำนวณระยะห่างจริง ณ เสี้ยววินาทีที่กดส่ง เพื่อป้องกันการสปูฟค่าพิกัดหน้าเว็บ
            distance = calculate_distance(float(user_lat), float(user_lon), office_lat, office_lon)
            
            # ตรวจสอบว่าพิกัดข้ามรัศมีที่อนุญาตหรือไม่
            if distance > allowed_radius:
                messages.error(request, f'บันทึกไม่สำเร็จ: คุณอยู่ห่างจากจุดที่กำหนดเกินไป (ห่าง {int(distance)} เมตร)')
                return redirect('checkin')

            # คำนวณสถานะเวลา มาปกติ / มาสาย
            status = calculate_status(timezone.now()) if action == 'checkin' else 'present'

            # บันทึกลงฐานข้อมูลโมเดล CheckInRecord
            record = CheckInRecord.objects.create(
                user=request.user,
                latitude=float(user_lat),
                longitude=float(user_lon),
                action=action,
                status=status,
                verification_method=verification_method,
                confidence_score=float(confidence_score),
                distance_meters=float(distance)
            )

            # ยิงแจ้งเตือนเข้าห้อง LINE ของหน่วยงานทันที
            try:
                notify_line_return_status(trigger_record=record)
            except Exception as line_err:
                print(f"ระบบแจ้งเตือน LINE ขัดข้องชั่วคราว: {line_err}")

            action_th = "เช็คอินเข้าปฏิบัติงาน" if action == 'checkin' else "เช็คเอาต์กลับ"
            messages.success(request, f'✨ บันทึกข้อมูล {action_th} สำเร็จเรียบร้อยแล้ว!')
            return redirect('dashboard')

        except Exception as e:
            messages.error(request, f'เกิดข้อผิดพลาดระหว่างบันทึกข้อมูล: {str(e)}')
            return redirect('checkin')

    # ====================================================
    #  ส่วนที่ 2: สำหรับเปิดหน้าจอปกติ (GET)
    # ====================================================
    try:
        face_profile, _ = UserFaceProfile.objects.get_or_create(user=request.user)
        saved_descriptor = face_profile.face_descriptor if face_profile.face_descriptor else '[]'
    except Exception:
        saved_descriptor = '[]'
        
    google_maps_api_key = getattr(settings, 'AIzaSyAdEA5DMsDjS26MJotjMxeXkDRxbZZo_dY', '')

    context = {
        'office_lat': office_lat,
        'office_lon': office_lon,
        'allowed_radius': allowed_radius,
        'location_name': location_name,
        'saved_descriptor': saved_descriptor,
        'google_maps_api_key': google_maps_api_key,
    }
    return render(request, 'checkin.html', context)
# ====================================================
#  ⚙️ เมนูแอดมิน: ระบบจัดการข้อมูลกำลังพล (Personnel Management)
# ====================================================

@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
def admin_dashboard(request):
    return render(request, 'admin_dashboard.html')


@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
def time_settings_view(request):
    return render(request, 'time_settings.html')


@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
def export_excel(request):
    return HttpResponse("Export Excel")

@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
def export_pdf(request):
    """ ฟังก์ชันดึงข้อมูลตาม Filter ล่าสุด เพื่อส่งไปหน้าพิมพ์รายงาน/PDF """
    
    # 1. ดึงข้อมูลกำลังพล (กรองแอดมินออกเหมือนหน้าหลัก)
    users_queryset = User.objects.filter(
        is_superuser=False,
        is_staff=False
    ).select_related('profile', 'face_profile')

    # 2. กรองข้อมูลตามที่แอดมินค้นหาค้างไว้ (ถ้ามี)
    search_query = request.GET.get('search', '').strip()
    if search_query:
        users_queryset = users_queryset.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    filter_company = request.GET.get('company_filter', '').strip()
    if filter_company:
        users_queryset = users_queryset.filter(profile__company=filter_company)

    # 3. ส่งข้อมูลไปที่หน้า HTML พิเศษสำหรับสั่งพิมพ์ PDF
    context = {
        'users': users_queryset,
        'search_query': search_query,
        'filter_company': filter_company,
        'current_date': timezone.now() if 'timezone' in globals() else None
    }
    return render(request, 'export_pdf_template.html', context)
@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
@require_POST
def add_user_admin(request):
    username = request.POST.get('username', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    phone_number = request.POST.get('phone_number', '').strip()
    company = request.POST.get('company', '').strip()
    password = request.POST.get('password', '').strip() or '123456'

    if not username or not first_name or not last_name:
        messages.error(request, 'กรุณากรอก Username และ ชื่อ-นามสกุล')
        return redirect('manage_users')

    if User.objects.filter(username=username).exists():
        messages.error(request, f'Username "{username}" มีอยู่ในระบบแล้ว')
        return redirect('manage_users')

    user = User.objects.create_user(username=username, password=password, first_name=first_name, last_name=last_name)
    UserProfile.objects.create(user=user, phone_number=phone_number, company=company, person_status='normal')
    
    try:
        UserFaceProfile.objects.get_or_create(user=user)
    except Exception:
        pass

    messages.success(request, f'เพิ่มกำลังพล {first_name} สำเร็จเรียบร้อย')
    return redirect('manage_users')


@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
@require_POST
def edit_user_admin(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    target_user.first_name = request.POST.get('first_name', '').strip()
    target_user.last_name = request.POST.get('last_name', '').strip()
    target_user.save()

    profile.phone_number = request.POST.get('phone_number', '').strip()
    profile.company = request.POST.get('company', '').strip()
    profile.person_status = request.POST.get('status', 'normal').strip()
    
    return_date_val = request.POST.get('return_date', '').strip()
    profile.return_date = return_date_val if return_date_val else None
    profile.save()

    messages.success(request, f'อัปเดตข้อมูลของ {target_user.username} แล้ว')
    return redirect('manage_users')


@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
def delete_user_admin(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    username = target_user.username
    target_user.delete()
    
    messages.success(request, f'ลบกำลังพล {username} ออกจากระบบแล้ว')
    return redirect('manage_users')
# ====================================================================
#  📥 ฟังก์ชันแสดงหน้าตาราง "เข้ากรมแล้ว" แบบเต็มจอ
# ====================================================================
def list_in_camp_view(request):
    # ดึงข้อมูลทหารที่มีสถานะเป็น 'normal' (อยู่กรม)
    list_in_camp = User.objects.filter(profile__person_status='normal').select_related('profile')
    
    context = {
        'list_in_camp': list_in_camp,
    }
    return render(request, 'list_in_camp.html', context)


# ====================================================================
#  📤 ฟังก์ชันแสดงหน้าตาราง "ออกกรม" แบบเต็มจอ
# ====================================================================
def list_out_camp_view(request):
    # ดึงข้อมูลทหารที่มีสถานะเป็น 'leave' (ลา) หรือ 'official' (ราชการ)
    list_out_camp = User.objects.filter(profile__person_status__in=['leave', 'official']).select_related('profile')
    
    context = {
        'list_out_camp': list_out_camp,
    }
    return render(request, 'list_out_camp.html', context)


# ====================================================================
#  👥 ฟังก์ชันแสดงหน้าตาราง "ยอดคงเหลือทั้งหมด" แบบเต็มจอ
# ====================================================================
def list_total_view(request):
    # ดึงข้อมูลกำลังพลทั้งหมดที่มีอยู่ในระบบ
    list_total = User.objects.all().select_related('profile')
    
    context = {
        'list_total': list_total,
    }
    return render(request, 'list_total.html', context)
# ====================================================================
#  📥 ฟังก์ชันแสดงหน้าตาราง "เข้ากรมแล้ว" แบบเต็มจอ (ใส่ท้ายไฟล์ views.py)
# ====================================================================
def list_in_camp_view(request):
    # ดึงข้อมูลรายชื่อคนที่อยู่กรม (normal)
    list_in_camp = User.objects.filter(profile__person_status='normal').select_related('profile')
    
    # นับยอดสถิติส่งไปโชว์ที่กล่องด้านบนด้วย
    stat_in_camp = list_in_camp.count()
    stat_out_camp = User.objects.filter(profile__person_status__in=['leave', 'official']).count()
    stat_total = User.objects.count()
    
    context = {
        'list_in_camp': list_in_camp,
        'stat_in_camp': stat_in_camp,
        'stat_out_camp': stat_out_camp,
        'stat_total': stat_total,
    }
    return render(request, 'list_in_camp.html', context)


# ====================================================================
#  📤 ฟังก์ชันแสดงหน้าตาราง "ออกกรม" แบบเต็มจอ (ใส่ท้ายไฟล์ views.py)
# ====================================================================
def list_out_camp_view(request):
    # ดึงข้อมูลรายชื่อคนไม่อยู่กรม (leave, official)
    list_out_camp = User.objects.filter(profile__person_status__in=['leave', 'official']).select_related('profile')
    
    # นับยอดสถิติส่งไปโชว์ที่กล่องด้านบนด้วย
    stat_in_camp = User.objects.filter(profile__person_status='normal').count()
    stat_out_camp = list_out_camp.count()
    stat_total = User.objects.count()
    
    context = {
        'list_out_camp': list_out_camp,
        'stat_in_camp': stat_in_camp,
        'stat_out_camp': stat_out_camp,
        'stat_total': stat_total,
    }
    return render(request, 'list_out_camp.html', context)


# ====================================================================
#  👥 ฟังก์ชันแสดงหน้าตาราง "ยอดคงเหลือทั้งหมด" แบบเต็มจอ (ใส่ท้ายไฟล์ views.py)
# ====================================================================
def list_total_view(request):
    # ดึงข้อมูลรายชื่อกำลังพลทั้งหมดในระบบ
    list_total = User.objects.all().select_related('profile')
    
    # นับยอดสถิติส่งไปโชว์ที่กล่องด้านบนด้วย
    stat_in_camp = User.objects.filter(profile__person_status='normal').count()
    stat_out_camp = User.objects.filter(profile__person_status__in=['leave', 'official']).count()
    stat_total = list_total.count()
    
    context = {
        'list_total': list_total,
        'stat_in_camp': stat_in_camp,
        'stat_out_camp': stat_out_camp,
        'stat_total': stat_total,
    }
    return render(request, 'list_total.html', context)
# ====================================================================
#  📥 ฟังก์ชันแสดงหน้าตาราง "เข้ากรมแล้ว" แบบเต็มจอ (แก้ไขไม่เอาแอดมิน)
# ====================================================================
def list_in_camp_view(request):
    # กรองเอาเฉพาะคนที่มีสถานะปกติ (normal) และ ต้องไม่ใช่แอดมิน (is_staff=False)
    list_in_camp = User.objects.filter(profile__person_status='normal', is_staff=False).select_related('profile')
    
    # คำนวณยอดสถิติด้านบนใหม่ โดยตัดแอดมินออกทั้งหมดเหมือนกัน
    stat_in_camp = list_in_camp.count()
    stat_out_camp = User.objects.filter(profile__person_status__in=['leave', 'official'], is_staff=False).count()
    stat_total = User.objects.filter(is_staff=False).count()
    
    context = {
        'list_in_camp': list_in_camp,
        'stat_in_camp': stat_in_camp,
        'stat_out_camp': stat_out_camp,
        'stat_total': stat_total,
    }
    return render(request, 'list_in_camp.html', context)


# ====================================================================
#  📤 ฟังก์ชันแสดงหน้าตาราง "ออกกรม" แบบเต็มจอ (แก้ไขไม่เอาแอดมิน)
# ====================================================================
def list_out_camp_view(request):
    # กรองเอาเฉพาะคนที่ ลา/ราชการ และ ต้องไม่ใช่แอดมิน (is_staff=False)
    list_out_camp = User.objects.filter(profile__person_status__in=['leave', 'official'], is_staff=False).select_related('profile')
    
    # คำนวณยอดสถิติด้านบนใหม่ โดยตัดแอดมินออกทั้งหมดเหมือนกัน
    stat_in_camp = User.objects.filter(profile__person_status='normal', is_staff=False).count()
    stat_out_camp = list_out_camp.count()
    stat_total = User.objects.filter(is_staff=False).count()
    
    context = {
        'list_out_camp': list_out_camp,
        'stat_in_camp': stat_in_camp,
        'stat_out_camp': stat_out_camp,
        'stat_total': stat_total,
    }
    return render(request, 'list_out_camp.html', context)


# ====================================================================
#  👥 ฟังก์ชันแสดงหน้าตาราง "ยอดคงเหลือทั้งหมด" แบบเต็มจอ (แก้ไขไม่เอาแอดมิน)
# ====================================================================
def list_total_view(request):
    # ดึงกำลังพลทั้งหมดในระบบ และ ต้องไม่ใช่แอดมิน (is_staff=False)
    list_total = User.objects.filter(is_staff=False).select_related('profile')
    
    # คำนวณยอดสถิติด้านบนใหม่ โดยตัดแอดมินออกทั้งหมดเหมือนกัน
    stat_in_camp = User.objects.filter(profile__person_status='normal', is_staff=False).count()
    stat_out_camp = User.objects.filter(profile__person_status__in=['leave', 'official'], is_staff=False).count()
    stat_total = list_total.count()
    
    context = {
        'list_total': list_total,
        'stat_in_camp': stat_in_camp,
        'stat_out_camp': stat_out_camp,
        'stat_total': stat_total,
    }
    return render(request, 'list_total.html', context)
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Q
from .models import UserProfile  # ตรวจสอบชื่อโมเดลโปรไฟล์ของพี่ด้วยนะครับ
# หากใช้ Django timezone ให้ import มาด้วย (ถ้าไม่มีให้ลบ บรรทัด current_date ใน context ออก)
from django.utils import timezone 

def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff)

@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
def export_pdf(request):
    """ ฟังก์ชันดึงข้อมูลตาม Filter ล่าสุด เพื่อส่งไปหน้าพิมพ์รายงาน/PDF """
    users_queryset = User.objects.filter(
        is_superuser=False,
        is_staff=False
    ).select_related('profile', 'face_profile')

    search_query = request.GET.get('search', '').strip()
    if search_query:
        users_queryset = users_queryset.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    filter_company = request.GET.get('company_filter', '').strip()
    if filter_company:
        users_queryset = users_queryset.filter(profile__company=filter_company)

    context = {
        'users': users_queryset,
        'search_query': search_query,
        'filter_company': filter_company,
        'current_date': timezone.now()
    }
    return render(request, 'export_pdf_template.html', context)


@login_required
@user_passes_test(is_admin_or_staff, login_url='dashboard')
def manage_users(request):
    """ หน้าแสดงรายชื่อ ค้นหา Filter และจัดการสถานะกำลังพลทั้งหมด (ตัวจริงที่ระบบเรียกหา) """
    company_choices = UserProfile.COMPANY_CHOICES if hasattr(UserProfile, 'COMPANY_CHOICES') else []
    status_choices = UserProfile.STATUS_CHOICES if hasattr(UserProfile, 'STATUS_CHOICES') else []

    users_queryset = User.objects.filter(
        is_superuser=False,
        is_staff=False
    ).select_related('profile', 'face_profile')

    # ระบบค้นหา (Search)
    search_query = request.GET.get('search', '').strip()
    if search_query:
        users_queryset = users_queryset.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    # ระบบกรองกองร้อย (Filter)
    filter_company = request.GET.get('company_filter', '').strip()
    if filter_company:
        users_queryset = users_queryset.filter(profile__company=filter_company)

    # ตกแต่ง UI Badge สำหรับสถานะ
    for user in users_queryset:
        prof = getattr(user, 'profile', None)
        status = prof.person_status if prof else 'normal'
        if status == 'normal':
            user.status_ui = "bg-green-100 text-green-800 px-2 py-1 rounded text-xs font-semibold"
        elif status == 'leave':
            user.status_ui = "bg-indigo-100 text-indigo-800 px-2 py-1 rounded text-xs font-semibold"
        else:
            user.status_ui = "bg-rose-100 text-rose-800 px-2 py-1 rounded text-xs font-semibold"

    context = {
        'users': users_queryset,
        'company_choices': company_choices,
        'status_choices': status_choices,
        'search_query': search_query,
        'filter_company': filter_company,
    }
    return render(request, 'manage_users.html', context)
@user_passes_test(lambda u: u.is_superuser) # ล็อกสิทธิ์เฉพาะ Superuser เท่านั้น
def set_location_view(request):
    # 🛠️ ส่วนนี้คือการดึงพิกัดเดิมมาโชว์ในช่องกรอก (ถ้ามี)
    # config = TimeSetting.objects.first() 
    
    if request.method == 'POST':
        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')
        
        # 🛠️ ส่วนนี้คือการบันทึกข้อมูลลงฐานข้อมูล
        # if config:
        #     config.latitude = lat
        #     config.longitude = lon
        #     config.save()
        # else:
        #     TimeSetting.objects.create(latitude=lat, longitude=lon)
            
        messages.success(request, f"อัปเดตพิกัดกรมเป็น {lat}, {lon} เรียบร้อยแล้ว!")
        return redirect('set_location') # ชื่อตามที่เราตั้งใน urls.py

    context = {
        'current_lat': '13.819810', # ตัวอย่าง (ให้เปลี่ยนเป็น config.latitude)
        'current_lon': '100.529614', # ตัวอย่าง (ให้เปลี่ยนเป็น config.longitude)
    }
    return render(request, 'set_location.html', context)