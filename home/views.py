from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from home.models import User, Class, StudentClassMapping
from django.views.decorators.csrf import csrf_exempt
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


def findsub(request):
    return render(request, 'home/findsub.html')

from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from home.models import User

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