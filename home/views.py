from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from home.models import User, Class, StudentClassMapping
from django.views.decorators.csrf import csrf_exempt




def index(request):
    return render(request, 'main.html') 

 
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
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