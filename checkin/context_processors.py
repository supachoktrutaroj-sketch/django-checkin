from django.contrib.auth.models import User
from .models import UserProfile 

def total_stats_processor(request):
    if request.user.is_authenticated and request.user.is_staff:
        # 📥 1. เข้ากรมแล้ว: ดึงข้อมูลกำลังพลทั่วไปที่สถานะเป็น 'ปกติ' หรือ 'normal' (รองรับทั้งสองแบบป้องกันบั๊ก)
        list_in_camp = User.objects.filter(
            is_staff=False, 
            profile__person_status__in=['ปกติ', 'normal']
        ).select_related('profile')
        in_camp = list_in_camp.count()
        
        # 📤 2. ออกกรม: ดึงกำลังพลที่ติดสถานะอื่นๆ (เช่น ลา, ไปราชการ, กลับบ้าน)
        list_out_camp = User.objects.filter(
            is_staff=False, 
            profile__person_status__in=['leave', 'mission', 'home', 'ลาพัก', 'ไปราชการ']
        ).select_related('profile')
        out_camp = list_out_camp.count()
        
        # 👥 3. ยอดรวมกำลังพลทั้งหมดในระบบ
        list_total = User.objects.filter(is_staff=False).select_related('profile')
        total = list_total.count()
        
        return {
            # 🔢 ส่วนที่ 1: ส่งตัวเลขไปโชว์ใน Badge (ยอดสถิติ)
            'stat_in_camp': in_camp,
            'stat_out_camp': out_camp,
            'stat_total': total,
            
            # 📦 ส่วนที่ 2: ส่งข้อมูลรายชื่อตัวจริงไปให้ HTML วนลูปแสดงผลรายชื่อ
            'list_in_camp': list_in_camp,
            'list_out_camp': list_out_camp,
            'list_total': list_total,
        }
    return {}
# เพิ่ม 3 บรรทัดนี้ในฟังก์ชัน manage_users_view เดิมของพี่
stat_in_camp = User.objects.filter(profile__person_status='normal').count()
stat_out_camp = User.objects.filter(profile__person_status__in=['leave', 'official']).count()
stat_total = User.objects.count()

# และเอาไปใส่ใน context ตัวเดิมที่มีอยู่แล้ว แบบนี้:
context = {
    # ... ของเดิมที่มีอยู่แล้ว ...
    'stat_in_camp': stat_in_camp,
    'stat_out_camp': stat_out_camp,
    'stat_total': stat_total,
}