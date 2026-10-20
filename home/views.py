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
from firebase_admin import auth, firestore
from tutorain.firebase_config import app
from django.shortcuts import render
from django.http import HttpResponse




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


#correct
def get_recorded_classes(student_email):
    """
    Retrieve recorded classes for a student from the
    recorded_classes tab of the existing Google spreadsheet.
    """

    if not student_email:
        return []

    # Read the recorded_classes tab, NOT the revision-video tab.
    url = f"https://opensheet.elk.sh/{SHEET_ID}/recorded_classes"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError) as error:
        print("Recorded classes sheet error:", error)
        return []

    student_email = str(student_email).strip().lower()
    recordings = []

    for row in rows:

        # Normalize column names and values.
        row = {
            str(key or "").strip().lower(): str(value or "").strip()
            for key, value in row.items()
        }

        # Match the Firebase email stored in the spreadsheet.
        row_email = row.get("student_email", "").strip().lower()

        if row_email != student_email:
            continue

        video_link = (
            row.get("video_link")
            or row.get("video link")
            or ""
        ).strip()

        if not video_link.startswith(("https://", "http://")):
            continue

        recordings.append({
            "title": row.get("title") or "Recorded Class",
            "class_date": (
                row.get("date")
                or row.get("duration")
                or ""
            ),
            "video_link": video_link,
            "tutor_name": (
                row.get("tutor_name")
                or row.get("tutor name")
                or ""
            ),
        })

    print("Student email:", student_email)
    print("Recorded classes found:", len(recordings))

    return recordings



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




def get_live_classes(student_email):
    """Get live classes for a student using their email address."""

    if not student_email:
        return []

    url = f"https://opensheet.elk.sh/{SHEET_ID}/live_class"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        rows = response.json()

    except (requests.RequestException, ValueError) as error:
        print("Live classes sheet error:", error)
        return []

    student_email = str(student_email).strip().lower()
    live_classes = []

    for row in rows:
        # Normalize column names and values
        row = {
            str(key or "").strip().lower(): str(value or "").strip()
            for key, value in row.items()
        }

        row_email = row.get("student_email", "").lower()

        # Match the live class to the logged-in student
        if row_email != student_email:
            continue

        live_link = row.get("live_link", "")

        if not live_link.startswith(("https://", "http://")):
            continue

        live_classes.append({
            "title": row.get("title") or "Live Class",
            "time": row.get("time", ""),
            "live_link": live_link,
        })

    print("Student email:", student_email)
    print("Live classes found:", len(live_classes))

    return live_classes




def get_revision_videos(student_email):
    """Get revision videos for a student from the existing Google Sheet."""

    if not student_email:
        return []

    # Change revision_video to the exact tab name in your spreadsheet.
    url = f"https://opensheet.elk.sh/{SHEET_ID}/link"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        rows = response.json()

    except (requests.RequestException, ValueError) as error:
        print("Revision video sheet error:", error)
        return []

    student_email = str(student_email).strip().lower()
    revision_videos = []

    for row in rows:
        # Normalize column names and values
        row = {
            str(key or "").strip().lower(): str(value or "").strip()
            for key, value in row.items()
        }

        row_email = row.get("student_email", "").lower()

        # Match the student's email.
        # The first column in the supplied sheet has no heading.
        if row_email != student_email:
            continue

        # Find the revision video link
        video_link = row.get("link", "")

        if not video_link.startswith(("https://", "http://")):
            continue

        revision_videos.append({
            "title": (
                row.get("tutorain special revision video")
                or row.get("title")
                or "Tutorain Special Revision Video"
            ),
            "video_title": row.get("tutorain special revision video", ""),
            "link": video_link,
        })

    print("Revision video student:", student_email)
    print("Revision videos found:", len(revision_videos))

    return revision_videos


from firebase_admin import firestore
from tutorain.firebase_config import app
from django.shortcuts import render
from django.http import HttpResponse


def firebase_student_dashboard(request):
    # 1. Verify student session
    if (
        request.session.get("user_role") != "student"
        or not request.session.get("firebase_uid")
    ):
        return HttpResponse(
            "Please log in with your student account.",
            status=401
        )

    firebase_uid = request.session["firebase_uid"]

    # 2. Connect to Firestore
    db = firestore.client(app=app)

    # 3. Find the student record
    student_docs = (
        db.collection("students")
        .where("firebase_uid", "==", firebase_uid)
        .limit(1)
        .stream()
    )

    student_doc = next(student_docs, None)

    if student_doc is None:
        return HttpResponse(
            "Student record not found. Please contact Tutorain.",
            status=404
        )

    student = student_doc.to_dict() or {}

#stsrt
    # Get the student's Firebase email
    student_email = (
        student.get("student_email")
        or student.get("firebase_email")
        or ""
    ).strip().lower()

    # Retrieve recordings belonging to this student
    recorded_classes = get_recorded_classes(student_email)
    # Get live classes using the same student email
    live_classes = get_live_classes(student_email)
    revision_videos = get_revision_videos(student_email)


    

    # 4. Check account status
    if str(student.get("status", "")).strip().lower() != "active":
        request.session.flush()
        return HttpResponse(
            "Your account is inactive. Please contact Tutorain.",
            status=403
        )

    # 5. Get reports belonging to this student
    # Existing class_reports documents contain student_id.
    reports = []

    for report_doc in db.collection("class_reports").stream():
        report = report_doc.to_dict() or {}

        if str(report.get("student_id", "")).strip() == student_doc.id:
            report["report_id"] = report_doc.id
            reports.append(report)

    # 6. Calculate attendance
    total_classes = len(reports)

    attended_classes = sum(
        1 for report in reports
        if str(report.get("attendance_status", "")).strip().lower()
        in ["present", "attended"]
    )

    attendance_percentage = (
        round((attended_classes / total_classes) * 100)
        if total_classes else 0
    )

    # 7. Display the dashboard
    context = {
        "student": student,
        "reports": reports,
        "total_classes": total_classes,
        "attended_classes": attended_classes,
        "attendance_percentage": attendance_percentage,
        "recorded_classes": recorded_classes,
        "live_classes": live_classes,
        "revision_videos": revision_videos,
    }

    return render(
        request,
        "home/firebase_student_dashboard.html",
        context
    )

import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from firebase_admin import auth, firestore
from tutorain.firebase_config import app


@require_POST
@csrf_protect
def firebase_student_login(request):
    try:
        data = json.loads(request.body)
        id_token = data.get("idToken")

        if not id_token:
            return JsonResponse({
                "success": False,
                "error": "Firebase ID token is required."
            }, status=400)

        # Verify the Firebase token on the server.
        decoded_token = auth.verify_id_token(
            id_token,
            app=app,
            check_revoked=True,
        )

        firebase_uid = decoded_token["uid"]

        # Find the student's Firestore record.
        db = firestore.client(app=app)

        results = (
            db.collection("students")
            .where("firebase_uid", "==", firebase_uid)
            .limit(1)
            .stream()
        )

        student_doc = next(results, None)

        if student_doc is None:
            return JsonResponse({
                "success": False,
                "error": "Student record not found. Contact Tutorain."
            }, status=403)

        student = student_doc.to_dict() or {}

        if str(student.get("status", "")).strip().lower() != "active":
            return JsonResponse({
                "success": False,
                "error": "Your student account is inactive."
            }, status=403)

        # Start a fresh Django session.
        request.session.flush()
        request.session["user_role"] = "student"
        request.session["firebase_uid"] = firebase_uid

        return JsonResponse({
            "success": True,
            "redirect_url": "/firebase-student-dashboard/"
        })

    except (ValueError, auth.InvalidIdTokenError):
        return JsonResponse({
            "success": False,
            "error": "Invalid Firebase login token."
        }, status=401)

    except Exception:
        # Avoid exposing internal server details to the browser.
        import logging
        logging.getLogger(__name__).exception(
            "Firebase student login failed"
        )

        return JsonResponse({
            "success": False,
            "error": "A server error occurred during login."
        }, status=500)



