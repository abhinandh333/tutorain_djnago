from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

class UserManager(BaseUserManager):
    def create_user(self, mobile, password=None, **extra_fields):
        if not mobile:
            raise ValueError("Mobile number is required")
        user = self.model(mobile=mobile, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(mobile, password, **extra_fields)


class User(AbstractUser):
    username = None  # remove username field
    mobile = models.CharField(max_length=15, unique=True)
    is_student = models.BooleanField(default=True)
    is_superadmin = models.BooleanField(default=False)

    USERNAME_FIELD = 'mobile'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.mobile


# ==================== CLASS ====================
class Class(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    recorded_link = models.URLField(blank=True, null=True)
    live_link = models.URLField(blank=True, null=True)
    scheduled_time = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.title


# ==================== STUDENT ↔ CLASS MAPPING ====================
class StudentClassMapping(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    klass = models.ForeignKey(Class, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('student', 'klass')

    def __str__(self):
        return f"{self.student.mobile} → {self.klass.title}"
