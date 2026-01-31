from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Class, StudentClassMapping

# ================= CUSTOM USER ADMIN =================
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ('mobile', 'is_student', 'is_superadmin', 'is_staff', 'is_active')
    list_filter = ('is_student', 'is_superadmin', 'is_staff', 'is_active')
    search_fields = ('mobile',)
    ordering = ('mobile',)
    fieldsets = (
        (None, {'fields': ('mobile', 'password')}),
        ('Permissions', {'fields': ('is_student', 'is_superadmin', 'is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('mobile', 'password1', 'password2', 'is_student', 'is_superadmin', 'is_staff', 'is_active')}
        ),
    )

# ================= REGISTER MODELS =================
admin.site.register(User, UserAdmin)
admin.site.register(Class)
admin.site.register(StudentClassMapping)
