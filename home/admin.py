from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Student

class StudentAdmin(UserAdmin):
    model = Student
    list_display = ('mobile', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active')
    fieldsets = (
        (None, {'fields': ('mobile', 'password')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('mobile', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    search_fields = ('mobile',)
    ordering = ('mobile',)

admin.site.register(Student, StudentAdmin)
