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
@login_required
def dashboard(request):
    mobile = request.user.mobile

    students = fetch_students()

    # find student
    student = next(
        (s for s in students if s.get('mobile') == mobile),
        None
    )

    if not student:
        return render(request, 'home/no_access.html')

    recorded = fetch_recorded(mobile)
    live = fetch_live(mobile)

    return render(request, 'home/dashboard.html', {
        'student': student,
        'recorded': recorded,
        'live': live
    })







import requests

SHEET_ID = "1bSH1WySBYYHDFROKOhxIib4296Wr_WVC_zbtXZ6fL7o"

def fetch_students():
    url = f"https://opensheet.elk.sh/{SHEET_ID}/students"
    res = requests.get(url)
    
    if res.status_code != 200:
        return []

    return res.json()


def fetch_recorded(mobile):
    url = f"https://opensheet.elk.sh/{SHEET_ID}/recorded_classes"
    res = requests.get(url)

    if res.status_code != 200:
        return []

    data = res.json()
    return [row for row in data if row.get('mobile') == mobile]


def fetch_live(mobile):
    url = f"https://opensheet.elk.sh/{SHEET_ID}/live_class"
    res = requests.get(url)

    if res.status_code != 200:
        return None

    data = res.json()
    for row in data:
        if row.get('mobile') == mobile:
            return row
    return None


from django.shortcuts import redirect

def accounts_login_redirect(request):
    return redirect('/login/')

def download(request):
    return render(request, 'home/download.html')

def free_classes(request):
    return render(request, 'home/free_classes.html')



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