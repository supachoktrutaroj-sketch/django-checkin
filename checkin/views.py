import os
import json
import math
import urllib.request
import urllib.error
import pytz
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import openpyxl

from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import (
    CheckInRecord,
    SystemSetting,
    UserFaceProfile,
    UserProfile
)

# ====================================================
# Helper Functions
# ====================================================

def is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser
    )


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


def calculate_distance(lat1, lon1, lat2, lon2):
    r = 6371000

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))

    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return r * c


def get_pdf_font():
    font_path = os.path.join(
        settings.BASE_DIR,
        'checkin',
        'static',
        'fonts',
        'THSarabunNew.ttf'
    )

    try:
        pdfmetrics.registerFont(
            TTFont("ThaiFont", font_path)
        )
        return "ThaiFont"

    except Exception as e:
        print("โหลดฟอนต์ไม่สำเร็จ:", e)
        return "Helvetica"


def get_system_setting():
    setting = SystemSetting.objects.first()

    if not setting:
        setting = SystemSetting.objects.create(
            checkin_start_time='08:00',
            late_time='08:30',
            return_deadline='18:00',
            latitude=13.968636,
            longitude=100.652162
        )

    return setting


def calculate_status(checkin_datetime):
    setting = get_system_setting()

    local_time = timezone.localtime(
        checkin_datetime
    ).time()

    late_time_setting = setting.late_time

    if isinstance(late_time_setting, str):
        try:
            late_time_setting = datetime.strptime(
                late_time_setting,
                '%H:%M'
            ).time()
        except Exception:
            late_time_setting = datetime.strptime(
                late_time_setting,
                '%H:%M:%S'
            ).time()

    return (
        "late"
        if local_time > late_time_setting
        else "present"
    )


# ====================================================
# LINE
# ====================================================

@csrf_exempt
def line_webhook(request):

    if request.method == 'POST':
        try:
            body = json.loads(
                request.body.decode('utf-8')
            )

            print("LINE EVENT:", body)

        except Exception as e:
            print("LINE ERROR:", str(e))

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'message': 'ok'})

def build_line_summary_message(trigger_record=None):

    today = timezone.localdate()

    checked_count = (
        CheckInRecord.objects.filter(
            created_at__date=today,
            action='checkin'
        )
        .values('user')
        .distinct()
        .count()
    )

    total_users = User.objects.filter(
        is_superuser=False,
        is_staff=False,
        is_active=True
    ).count()

    not_checked_count = max(total_users - checked_count, 0)

    lines = []

    if trigger_record:

        action_text = (
            'เช็คอิน'
            if trigger_record.action == 'checkin'
            else 'เช็คเอาต์'
        )

        # 💡 ดึงชื่อจริง (first_name) มาแสดงผล ถ้าไม่มีค่อยใช้ username
        display_name = trigger_record.user.first_name or trigger_record.user.username

        lines.append("📢 มีการอัปเดต")
        lines.append(f"ชื่อ: {display_name}")
        lines.append(f"รายการ: {action_text}")
        lines.append(
            f"เวลา: {timezone.localtime(trigger_record.created_at).strftime('%H:%M:%S')}"
        )

        lines.append("")

    # 📊 ปรับเปลี่ยนข้อความแสดงผลสรุปยอดตามที่คุณต้องการ
    lines.append(f"✅ มาแล้ว: {checked_count} คน")
    lines.append(f"❌ ไม่มา: {not_checked_count} คน")
    lines.append(f"📊 ทั้งหมด: {total_users} คน") # 👈 เพิ่มบรรทัดนี้เข้าไป

    return "\n".join(lines)


def send_line_push_message(message_text):

    channel_access_token = getattr(
        settings,
        'LINE_CHANNEL_ACCESS_TOKEN',
        ''
    ).strip()

    target_id = getattr(
        settings,
        'LINE_TARGET_ID',
        ''
    ).strip()

    if not channel_access_token or not target_id:
        return False, "LINE NOT CONFIG"

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
        with urllib.request.urlopen(
            req,
            timeout=15
        ) as response:

            return True, response.read().decode(
                "utf-8",
                errors="ignore"
            )

    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode(
                "utf-8",
                errors="ignore"
            )
        except Exception:
            detail = str(e)

        return False, detail

    except Exception as e:
        return False, str(e)


def notify_line_return_status(trigger_record=None):

    message_text = build_line_summary_message(
        trigger_record=trigger_record
    )

    cache_key = f"line_notify:{hash(message_text)}"

    if cache.get(cache_key):
        return False, "duplicate skipped"

    ok, result = send_line_push_message(
        message_text
    )

    if ok:
        cache.set(cache_key, True, timeout=60)

    return ok, result


# ====================================================
# Authentication
# ====================================================

def register_view(request):

    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':

        first_name = request.POST.get(
            'first_name',
            ''
        ).strip()

        last_name = request.POST.get(
            'last_name',
            ''
        ).strip()

        username = request.POST.get(
            'username',
            ''
        ).strip()

        phone_number = request.POST.get(
            'phone_number',
            ''
        ).strip()

        company = request.POST.get(
            'company',
            ''
        ).strip()

        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if User.objects.filter(
            username=username
        ).exists():

            return render(request, 'register.html', {
                'error': 'Username ถูกใช้แล้ว'
            })

        if password1 != password2:
            return render(request, 'register.html', {
                'error': 'รหัสผ่านไม่ตรงกัน'
            })

        user = User.objects.create_user(
            username=username,
            password=password1,
            first_name=first_name,
            last_name=last_name
        )

        UserProfile.objects.create(
            user=user,
            phone_number=phone_number,
            company=company
        )

        UserFaceProfile.objects.get_or_create(
            user=user
        )

        login(request, user)

        return redirect('face_register')

    return render(request, 'register.html')


def login_view(request):

    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user:

            login(request, user)

            if user.is_superuser:
                return redirect('dashboard')

            profile, _ = UserFaceProfile.objects.get_or_create(
                user=user
            )

            if not profile.face_descriptor:
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
# Dashboard
# ====================================================

@login_required
def dashboard(request):

    today = timezone.localdate()

    raw_data = (
        CheckInRecord.objects
        .filter(user=request.user)
        .select_related('user')
        .order_by('-created_at')
    )

    today_records = CheckInRecord.objects.filter(
        created_at__date=today
    )

    total_checkin = today_records.filter(
        action='checkin'
    ).count()

    late_count = today_records.filter(
        action='checkin',
        status='late'
    ).count()

    checkout_count = today_records.filter(
        action='checkout'
    ).count()

    total_users = User.objects.filter(
        is_superuser=False,
        is_staff=False
    ).count()

    checked_today = (
        today_records
        .filter(action='checkin')
        .values('user')
        .distinct()
        .count()
    )

    not_checked_in = max(
        total_users - checked_today,
        0
    )

    context = {
        'data': raw_data,
        'total_checkin': total_checkin,
        'late_count': late_count,
        'checkout_count': checkout_count,
        'not_checked_in': not_checked_in,
    }

    return render(
        request,
        'dashboard.html',
        context
    )
@login_required
@user_passes_test(is_admin_or_staff)
def time_settings_view(request):
    # ดึงข้อมูลตั้งค่าแถวแรกสุดขึ้นมา (ถ้าไม่มีระบบจะสร้างให้โดยอัตโนมัติ)
    system_setting, _ = SystemSetting.objects.get_or_create(id=1)

    if request.method == 'POST':
        # รับค่าข้อความเวลาที่แอดมินพิมพ์ (เช่น "08:00")
        checkin_start = request.POST.get('checkin_start_time')
        late_time = request.POST.get('late_time')
        
        try:
            # 定กำหนดเขตเวลาให้เป็นของประเทศไทย (Asia/Bangkok)
            bangkok_tz = pytz.timezone('Asia/Bangkok')
            today_str = datetime.today().strftime('%Y-%m-%d')

            if checkin_start:
                # นำเวลาที่พิมพ์มารวมกับวันที่ปัจจุบัน เพื่อแปลงเป็นรูปแบบ DateTime ที่มี Timezone ไทย
                naive_start = datetime.strptime(f"{today_str} {checkin_start}", "%Y-%m-%d %H:%M")
                aware_start = timezone.make_aware(naive_start, bangkok_tz)
                system_setting.checkin_start_time = aware_start.time()

            if late_time:
                # ทำแบบเดียวกันกับเวลาสาย เพื่อบล็อกไม่ให้เวลาขยับเพี้ยน
                naive_late = datetime.strptime(f"{today_str} {late_time}", "%Y-%m-%d %H:%M")
                aware_late = timezone.make_aware(naive_late, bangkok_tz)
                system_setting.late_time = aware_late.time()
                
            system_setting.save()
            messages.success(request, '💾 อัปเดตการตั้งค่าเวลาเข้างานตรงตามที่พิมพ์เรียบร้อยแล้ว!')
            return redirect('admin_dashboard')
            
        except Exception as e:
            messages.error(request, f'เกิดข้อผิดพลาดในการบันทึก (กรุณาเช็คฟอร์ม): {str(e)}')

    context = {
        'system_setting': system_setting,
    }
    return render(request, 'time_settings.html', context)
@login_required
def history_view(request):

    data = (
        CheckInRecord.objects
        .filter(user=request.user)
        .order_by('-created_at')
    )

    return render(request, 'history.html', {
        'data': data
    })


@login_required
def profile_view(request):

    profile, _ = UserProfile.objects.get_or_create(
        user=request.user
    )

    return render(request, 'profile.html', {
        'profile': profile
    })


# ====================================================
# Face Recognition
# ====================================================

@login_required
def face_register_page(request):

    profile, _ = UserFaceProfile.objects.get_or_create(
        user=request.user
    )

    return render(request, 'face_register.html', {
        'has_face_registered': bool(
            profile.face_descriptor
        )
    })

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
@login_required
@require_POST
def save_face_descriptor(request):

    try:

        data = json.loads(
            request.body.decode('utf-8')
        )

        descriptor = data.get('descriptor')

        if not is_valid_face_descriptor(descriptor):

            return JsonResponse({
                'success': False,
                'message': 'ข้อมูลใบหน้าไม่ถูกต้อง'
            })

        profile, _ = UserFaceProfile.objects.get_or_create(
            user=request.user
        )

        if profile.face_descriptor:
            return JsonResponse({
                'success': False,
                'message': 'บัญชีนี้ลงทะเบียนแล้ว'
            })

        duplicate_threshold = 0.45

        other_profiles = (
            UserFaceProfile.objects
            .exclude(user=request.user)
            .exclude(face_descriptor__isnull=True)
            .exclude(face_descriptor='')
        )

        for other in other_profiles:

            try:
                old_descriptor = json.loads(
                    other.face_descriptor
                )

                distance = calculate_face_distance(
                    descriptor,
                    old_descriptor
                )

                if distance < duplicate_threshold:

                    return JsonResponse({
                        'success': False,
                        'message': 'ใบหน้านี้ถูกใช้แล้ว'
                    })

            except Exception:
                continue

        profile.face_descriptor = json.dumps(
            descriptor
        )

        profile.face_registered_at = timezone.now()

        profile.save()

        return JsonResponse({
            'success': True
        })

    except Exception as e:

        return JsonResponse({
            'success': False,
            'message': str(e)
        })


# ====================================================
# Checkin
# ====================================================

@login_required
def checkin_view(request):

    setting = get_system_setting()

    OFFICE_LAT = float(setting.latitude)
    OFFICE_LON = float(setting.longitude)

    ALLOWED_RADIUS = 500.0

    LOCATION_NAME = "หน่วยงาน"

    if request.method == 'POST':

        action = request.POST.get(
            'action',
            'checkin'
        )

        verification_method = request.POST.get(
            'verification_method',
            'face'
        )

        confidence_score = request.POST.get(
            'confidence_score',
            0
        )

        user_lat = request.POST.get('latitude')
        user_lon = request.POST.get('longitude')

        if not user_lat or not user_lon:

            messages.error(
                request,
                'ไม่พบ GPS'
            )

            return redirect('checkin')

        try:
# 🛠️ จุดที่เพิ่มใหม่: เช็คว่าวันนี้คนๆ นี้เคยเช็คอิน (action='checkin') ไปแล้วหรือยัง
            if action == 'checkin':
                today = timezone.localdate()
                already_checked_in = CheckInRecord.objects.filter(
                    user=request.user,
                    created_at__date=today,
                    action='checkin'
                ).exists()

                if already_checked_in:
                    # ถ้าเคยเช็คอินไปแล้วในวันนี้ ให้แจ้งเตือนฝั่งหน้าเว็บและเด้งกลับทันที ไม่บันทึกซ้ำ
                    messages.error(
                        request,
                        'วันนี้คุณได้ทำการเช็คอินไปเรียบร้อยแล้ว ไม่สามารถเช็คอินซ้ำได้'
                    )
                    return redirect('checkin')

            # ---------------------------------------------------------------------
            # (โค้ดเดิมด้านล่าง) ทำงานตามปกติหากผ่านเงื่อนไขด้านบน หรือถ้าเลือกสแกน 'checkout'
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

            # 🛠️ อัปเดตสถานะใน UserProfile เพื่อให้หน้าจัดการกำลังพลเปลี่ยนตามทันที
            try:
                # ดึงข้อมูล Profile ของคนที่กำลังแสกนหน้า
                profile, _ = UserProfile.objects.get_or_create(user=request.user)
                
                if action == 'checkin':
                    profile.person_status = 'normal'  # เมื่อเช็คอินสำเร็จ -> เปลี่ยนสถานะเป็น "ปกติ"
                elif action == 'checkout':
                    profile.person_status = 'home'    # เมื่อเช็คเอาต์สำเร็จ -> เปลี่ยนสถานะเป็น "กลับบ้าน"
                
                profile.save()
            except Exception as profile_err:
                print("PROFILE UPDATE ERROR:", profile_err)

            # 2. ส่งการแจ้งเตือนเข้าไปยังระบบ LINE
            try:
                notify_line_return_status(
                    trigger_record=record
                )
            except Exception as e:
                print("LINE ERROR:", e)

            messages.success(
                request,
                'บันทึกสำเร็จ'
            )

            return redirect('dashboard')

        except Exception as e:

            messages.error(
                request,
                str(e)
            )

            return redirect('checkin')
        # 1. บันทึกข้อมูลประวัติการสแกนใบหน้าเข้า CheckInRecord
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

            # 🛠️ จุดที่เพิ่มใหม่: อัปเดตสถานะใน UserProfile เพื่อให้หน้าจัดการกำลังพลเปลี่ยนตามทันที
            try:
                # ดึงข้อมูล Profile ของคนที่กำลังแสกนหน้า
                profile, _ = UserProfile.objects.get_or_create(user=request.user)
                
                if action == 'checkin':
                    profile.person_status = 'normal'  # เมื่อเช็คอินสำเร็จ -> เปลี่ยนสถานะเป็น "ปกติ"
                elif action == 'checkout':
                    profile.person_status = 'home'    # เมื่อเช็คเอาต์สำเร็จ -> เปลี่ยนสถานะเป็น "กลับบ้าน"
                
                profile.save()
            except Exception as profile_err:
                print("PROFILE UPDATE ERROR:", profile_err)

            # 2. ส่งการแจ้งเตือนเข้าไปยังระบบ LINE
            try:
                notify_line_return_status(
                    trigger_record=record
                )
            except Exception as e:
                print("LINE ERROR:", e)

            messages.success(
                request,
                'บันทึกสำเร็จ'
            )

            return redirect('dashboard')

        except Exception as e:

            messages.error(
                request,
                str(e)
            )

            return redirect('checkin')

    try:

        face_profile, _ = (
            UserFaceProfile.objects.get_or_create(
                user=request.user
            )
        )

        saved_descriptor = (
            face_profile.face_descriptor
            if face_profile.face_descriptor
            else '[]'
        )

    except Exception:
        saved_descriptor = '[]'

    google_maps_api_key = getattr(
        settings,
        'AIzaSyAdEA5DMsDjS26MJotjMxeXkDRxbZZo_dY',
        ''
    )

    context = {
        'office_lat': OFFICE_LAT,
        'office_lon': OFFICE_LON,
        'allowed_radius': ALLOWED_RADIUS,
        'location_name': LOCATION_NAME,
        'saved_descriptor': saved_descriptor,
        'google_maps_api_key': google_maps_api_key,
    }

    return render(
        request,
        'checkin.html',
        context
    )


# ====================================================
# Admin
# ====================================================

@login_required
@user_passes_test(is_admin_or_staff)
def admin_dashboard(request):
    today = timezone.localdate()

    # 1. ดึงข้อมูลโมเดล SystemSetting ส่งไปทั้งก้อน (แก้ปัญหาเวลากลับเข้ากรม และเคลียร์ NaN ใน JavaScript)
    system_setting = SystemSetting.objects.first()

    # 2. คำนวณจำนวนกำลังพลทั้งหมด (ไม่รวมแอดมิน)
    total_users = User.objects.filter(
        is_superuser=False,
        is_staff=False,
        is_active=True
    ).count()

    # 3. นับจำนวนคนที่เช็คอินวันนี้แล้ว (นับแบบไม่ซ้ำคนใน 1 วัน)
    today_records = CheckInRecord.objects.filter(created_at__date=today)
    
    # 4. ดึงรายชื่อออบเจกต์ User ของคนที่ "ยังไม่ได้เช็คอิน" ในวันนี้ เพื่อเอาไปวนลูปแสดงในตาราง
    checked_user_ids = today_records.filter(action='checkin').values_list('user_id', flat=True)
    not_checkedin_users = User.objects.filter(
        is_superuser=False,
        is_staff=False,
        is_active=True
    ).exclude(id__in=checked_user_ids).select_related('profile')

    # 5. จัดตัวแปรลงชื่อคีย์เวิร์ดที่ไฟล์ HTML ชุดเก่าตั้งเอาไว้เป๊ะๆ
    context = {
        'system_setting': system_setting,          # 👈 แมทช์กับ {{ system_setting }} ทั่วทั้งหน้าจอ
        'not_checkedin_users': not_checkedin_users,  # 👈 แมทช์กับ {{ not_checkedin_users }} ในตารางและการ์ดสีแดง
    }

    return render(
        request,
        'admin_dashboard.html',
        context
    )

@login_required
@user_passes_test(is_admin_or_staff)
def manage_users(request):

    users_queryset = User.objects.filter(
        is_superuser=False,
        is_staff=False
    ).select_related(
        'profile',
        'face_profile'
    )

    search_query = request.GET.get(
        'search',
        ''
    ).strip()

    if search_query:

        users_queryset = users_queryset.filter(
            Q(username__icontains=search_query)
            |
            Q(first_name__icontains=search_query)
            |
            Q(last_name__icontains=search_query)
        )

    filter_company = request.GET.get(
        'company_filter',
        ''
    ).strip()

    if filter_company:

        users_queryset = users_queryset.filter(
            profile__company=filter_company
        )

    context = {
        'users': users_queryset,
        'search_query': search_query,
        'filter_company': filter_company,
        'company_choices': UserProfile.COMPANY_CHOICES,
        'status_choices': UserProfile.PERSON_STATUS_CHOICES,
    }

    return render(
        request,
        'manage_users.html',
        context
    )

@login_required
@user_passes_test(is_admin_or_staff)
@require_POST
def add_user_admin(request):

    username = request.POST.get(
        'username',
        ''
    ).strip()

    first_name = request.POST.get(
        'first_name',
        ''
    ).strip()

    last_name = request.POST.get(
        'last_name',
        ''
    ).strip()

    phone_number = request.POST.get(
        'phone_number',
        ''
    ).strip()

    company = request.POST.get(
        'company',
        ''
    ).strip()

    password = request.POST.get(
        'password',
        '123456'
    ).strip()

    if User.objects.filter(
        username=username
    ).exists():

        messages.error(
            request,
            'Username ซ้ำ'
        )

        return redirect('manage_users')

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name
    )

    UserProfile.objects.create(
        user=user,
        phone_number=phone_number,
        company=company,
        person_status='normal'
    )

    UserFaceProfile.objects.get_or_create(
        user=user
    )

    messages.success(
        request,
        'เพิ่มผู้ใช้สำเร็จ'
    )

    return redirect('manage_users')


@login_required
@user_passes_test(is_admin_or_staff)
def delete_user_admin(request, user_id):

    target_user = get_object_or_404(
        User,
        id=user_id
    )

    target_user.delete()

    messages.success(
        request,
        'ลบผู้ใช้สำเร็จ'
    )

    return redirect('manage_users')


# ====================================================
# Export PDF
# ====================================================

@login_required
@user_passes_test(is_admin_or_staff)
def export_pdf(request):

    users_queryset = User.objects.filter(
        is_superuser=False,
        is_staff=False
    ).select_related(
        'profile',
        'face_profile'
    )

    search_query = request.GET.get(
        'search',
        ''
    ).strip()

    if search_query:

        users_queryset = users_queryset.filter(
            Q(username__icontains=search_query)
            |
            Q(first_name__icontains=search_query)
            |
            Q(last_name__icontains=search_query)
        )

    filter_company = request.GET.get(
        'company_filter',
        ''
    ).strip()

    if filter_company:

        users_queryset = users_queryset.filter(
            profile__company=filter_company
        )

    context = {
        'users': users_queryset,
        'search_query': search_query,
        'filter_company': filter_company,
        'current_date': timezone.now()
    }

    return render(
        request,
        'export_pdf_template.html',
        context
    )


# ====================================================
# Lists
# ====================================================

@login_required
def list_in_camp_view(request):

    list_in_camp = User.objects.filter(
        profile__person_status='normal',
        is_staff=False
    ).select_related('profile')

    context = {
        'list_in_camp': list_in_camp,
        'stat_in_camp': list_in_camp.count(),
        'stat_out_camp': User.objects.filter(
            profile__person_status__in=[
                'leave',
                'official'
            ],
            is_staff=False
        ).count(),
        'stat_total': User.objects.filter(
            is_staff=False
        ).count(),
    }

    return render(
        request,
        'list_in_camp.html',
        context
    )


@login_required
def list_out_camp_view(request):

    list_out_camp = User.objects.filter(
        profile__person_status__in=[
            'leave',
            'official'
        ],
        is_staff=False
    ).select_related('profile')

    context = {
        'list_out_camp': list_out_camp,
        'stat_in_camp': User.objects.filter(
            profile__person_status='normal',
            is_staff=False
        ).count(),
        'stat_out_camp': list_out_camp.count(),
        'stat_total': User.objects.filter(
            is_staff=False
        ).count(),
    }

    return render(
        request,
        'list_out_camp.html',
        context
    )


@login_required
def list_total_view(request):

    list_total = User.objects.filter(
        is_staff=False
    ).select_related('profile')

    context = {
        'list_total': list_total,
        'stat_in_camp': User.objects.filter(
            profile__person_status='normal',
            is_staff=False
        ).count(),
        'stat_out_camp': User.objects.filter(
            profile__person_status__in=[
                'leave',
                'official'
            ],
            is_staff=False
        ).count(),
        'stat_total': list_total.count(),
    }

    return render(
        request,
        'list_total.html',
        context
    )


# ====================================================
# Set Location
# ====================================================

@login_required
@user_passes_test(lambda u: u.is_superuser)
def set_location_view(request):

    config = get_system_setting()

    if request.method == 'POST':

        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')

        config.latitude = lat
        config.longitude = lon

        config.save()

        messages.success(
            request,
            'อัปเดตพิกัดสำเร็จ'
        )

        return redirect('set_location')

    context = {
        'current_lat': config.latitude,
        'current_lon': config.longitude,
    }

    return render(
        request,
        'set_location.html',
        context
    )