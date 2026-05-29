#!/bin/bash
set -o errexit

# 1. ติดตั้งแพ็กเกจหลักทั้งหมดจาก requirements.txt
pip install -r requirements.txt

# 2. ติดตั้ง gunicorn เสริมบน Railway Server
pip install gunicorn

# 3. จัดการไฟล์ Static
python manage.py collectstatic --noinput