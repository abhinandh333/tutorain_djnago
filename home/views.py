from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from home.models import User, Class, StudentClassMapping
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.cache import cache_control
from django.shortcuts import render




def index(request):
    return render(request, 'home/main.html') 


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def student_login(request):
    mobile = request.data.get('mobile')
    password = request.data.get('password')

    if not mobile or not password:
        return Response({'error': 'Mobile and password required'}, status=400)

    try:
        student = User.objects.get(mobile=mobile, is_student=True)
        if not student.check_password(password):
            return Response({'error': 'Invalid credentials'}, status=401)
    except User.DoesNotExist:
        return Response({'error': 'Invalid credentials'}, status=401)

    token, _ = Token.objects.get_or_create(user=student)

    return Response({
        'mobile': student.mobile,
        'token': token.key
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_classes(request):
    student = request.user
    mappings = StudentClassMapping.objects.filter(student=student)
    data = []
    for m in mappings:
        data.append({
            'title': m.klass.title,
            'description': m.klass.description,
            'recorded_link': m.klass.recorded_link,
            'live_link': m.klass.live_link,
            'scheduled_time': m.klass.scheduled_time
        })
    return Response(data)

def contact(request):
    return render(request, 'home/contact.html')


def comingsoon(request):
    return render(request, 'home/comingsoon.html')


def maca(request):
    return render(request, 'home/maca.html')


def findsub(request):
    return render(request, 'home/findsub.html')

from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from home.models import User

@never_cache
@cache_control(
    no_cache=True,
    must_revalidate=True,
    no_store=True
)
def student_login_web(request):
    if request.method == "POST":
        mobile = request.POST.get("mobile")
        password = request.POST.get("password")

        user = authenticate(request, mobile=mobile, password=password)

        if user is not None and user.is_student:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'home/login.html', {'error': 'Invalid credentials'})

    return render(request, 'home/login.html')






from django.contrib.auth.decorators import login_required
import requests


# =========================================================
# GOOGLE SHEET
# =========================================================

SHEET_ID = "1bSH1WySBYYHDFROKOhxIib4296Wr_WVC_zbtXZ6fL7o"


# =========================================================
# MOBILE NUMBER NORMALIZATION
# =========================================================

def normalize_mobile(value):

    if value is None:
        return ""

    value = str(value).strip()

    # Google Sheets can sometimes return:
    # 9567326701.0
    if value.endswith(".0"):
        value = value[:-2]

    # Remove spaces and symbols
    value = value.replace(" ", "")
    value = value.replace("-", "")
    value = value.replace("+", "")

    # Convert Indian country-code format
    # 919567326701 -> 9567326701
    if value.startswith("91") and len(value) == 12:
        value = value[2:]

    return value


# =========================================================
# FETCH STUDENTS
# =========================================================

def fetch_students():

    url = f"https://opensheet.elk.sh/{SHEET_ID}/students"

    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException:
        return []

    if response.status_code != 200:
        return []

    try:
        data = response.json()
    except ValueError:
        return []

    return data


# =========================================================
# FETCH RECORDED CLASSES
# =========================================================

def fetch_recorded(mobile):

    url = f"https://opensheet.elk.sh/{SHEET_ID}/recorded_classes"

    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException:
        return []

    if response.status_code != 200:
        return []

    try:
        data = response.json()
    except ValueError:
        return []

    mobile = normalize_mobile(mobile)

    return [
        row
        for row in data
        if normalize_mobile(row.get("mobile")) == mobile
    ]


# =========================================================
# FETCH LIVE CLASS
# =========================================================

def fetch_live(mobile):

    url = f"https://opensheet.elk.sh/{SHEET_ID}/live_class"

    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    mobile = normalize_mobile(mobile)

    for row in data:

        if normalize_mobile(row.get("mobile")) == mobile:
            return row

    return None


# =========================================================
# FETCH TUTORAIN SPECIAL REVISION VIDEOS
# =========================================================

def fetch_revision_videos(mobile):

    url = f"https://opensheet.elk.sh/{SHEET_ID}/link"

    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException:
        return []

    if response.status_code != 200:
        return []

    try:
        data = response.json()
    except ValueError:
        return []

    mobile = normalize_mobile(mobile)

    revision_videos = []

    for row in data:

        row_mobile = normalize_mobile(
            row.get("mobile")
        )

        # Only show this student's videos
        if row_mobile != mobile:
            continue

        title = str(
            row.get("Tutorain Special Revision Video", "")
        ).strip()

        link = str(
            row.get("link", "")
        ).strip()

        # Ignore incomplete rows
        if not title or not link:
            continue

        revision_videos.append({
            "title": title,
            "link": link,
        })

    return revision_videos


# =========================================================
# DASHBOARD
# =========================================================

@login_required
def dashboard(request):

    user_mobile_raw = request.user.mobile
    user_mobile = normalize_mobile(user_mobile_raw)

    students = fetch_students()

    debug_data = []

    for s in students:

        sheet_mobile_raw = s.get("mobile", "")
        sheet_mobile = normalize_mobile(sheet_mobile_raw)

        debug_data.append({
            "raw": sheet_mobile_raw,
            "normalized": sheet_mobile,
            "matches": sheet_mobile == user_mobile,
            "student": s,
        })

    student = None

    for item in debug_data:

        if item["matches"]:
            student = item["student"]
            break

    if not student:

        return HttpResponse(
            f"""
            <html>
            <body style="font-family:Arial;padding:30px">

            <h2>Student matching failed</h2>

           

            <p>
                Raw mobile:
                <strong>{user_mobile_raw}</strong>
            </p>

            <p>
                Normalized mobile:
                <strong>{user_mobile}</strong>
            </p>

           

            </body>
            </html>
            """
        )

    recorded = fetch_recorded(user_mobile)

    live = fetch_live(user_mobile)

    revision_videos = fetch_revision_videos(user_mobile)

    return render(
        request,
        "home/dashboard.html",
        {
            "student": student,
            "recorded": recorded,
            "live": live,
            "revision_videos": revision_videos,
        }
    )










from django.shortcuts import redirect

def accounts_login_redirect(request):
    return redirect('/login/')

def download(request):
    return render(request, 'home/download.html')

def free_classes(request):
    return render(request, 'home/free_classes.html')


def abhinandh(request):
    return render(request, 'home/abhinandh.html')

def ceo(request):
    return render(request, 'home/ceo.html')



@api_view(['POST'])
@permission_classes([AllowAny])
def auto_login(request):
    token_key = request.data.get("token")

    if not token_key:
        return Response({"success": False}, status=400)

    try:
        token = Token.objects.get(key=token_key)

        return Response({
            "success": True,
            "mobile": token.user.mobile,
            "name": token.user.name
        })

    except Token.DoesNotExist:
        return Response({"success": False}, status=401)
    


from django.shortcuts import redirect

def meet_redirect(request, username):

    links = {
        "abhinandh": "https://meet.google.com/orw-acbx-sta",

    }

    if username in links:
        return redirect(links[username])

    return redirect("/")




import csv
import requests
from django.shortcuts import render

CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTyiO8zG1Y6IAtZPSpR1_e6Jq4cy09GrhYOSx5uI-Zw1taFu5LwoxmrZIPDKHhAJ7TBBzQ6-K5pYeKK/pub?output=csv"

def free_classes(request):
    response = requests.get(CSV_URL)
    response.raise_for_status()  # Shows an error if the sheet can't be downloaded
    response.encoding = "utf-8"

    rows = list(csv.DictReader(response.text.splitlines()))

    classes = []

    for row in rows:
        class_name = row["Class"].strip()

        if class_name not in classes:
            classes.append(class_name)

    classes.sort()  # Sorts as 1,2,3...9 instead of 1,10,2

    return render(request, "home/free_classes.html", {
        "classes": classes
    })


import csv
import requests
from django.shortcuts import render

CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTyiO8zG1Y6IAtZPSpR1_e6Jq4cy09GrhYOSx5uI-Zw1taFu5LwoxmrZIPDKHhAJ7TBBzQ6-K5pYeKK/pub?output=csv"

def class_subjects(request, class_name):

    response = requests.get(CSV_URL)
    response.encoding = "utf-8"

    rows = list(csv.DictReader(response.text.splitlines()))

    subjects = []

    for row in rows:

        if row["Class"].strip() == class_name:

            subject = row["Subject"].strip()

            if subject not in subjects:
                subjects.append(subject)

    return render(request, "home/class_subjects.html", {
        "class_name": class_name,
        "subjects": subjects,
    })

def get_sheet_data():

    response = requests.get(CSV_URL)

    response.encoding = "utf-8"

    return list(csv.DictReader(response.text.splitlines()))

def subject_details(request, class_name, subject):

    rows = get_sheet_data()

    playlist = ""
    chapters = []

    for row in rows:

        if (
            row["Class"].strip() == class_name
            and
            row["Subject"].strip() == subject
        ):

            if row["Chapter"].strip().lower() == "playlist":

                playlist = row["Playlist URL"]

            else:

                chapters.append({

                    "chapter": row["Chapter"],

                    "video": row["Video URL"],

                    "status": row["Status"]

                })

    return render(
        request,
        "home/subject_details.html",
        {
            "class_name": class_name,
            "subject": subject,
            "playlist": playlist,
            "chapters": chapters,
        }
    )