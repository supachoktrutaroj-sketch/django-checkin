#!/bin/bash
set -o errexit

# ติดตั้ง dependencies
pip install -r requirements.txt

# ติดตั้ง gunicorn
pip install gunicorn

# collect static
python manage.py collectstatic --noinput

# migrate database
python manage.py migrate