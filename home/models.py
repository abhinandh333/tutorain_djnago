from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class StudentManager(BaseUserManager):
    def create_user(self, mobile, password=None):
        if not mobile:
            raise ValueError("Mobile number required")

        user = self.model(mobile=mobile)
        user.set_password(password)  # 🔐 hashes password
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile, password):
        user = self.create_user(mobile, password)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        return user


class Student(AbstractBaseUser, PermissionsMixin):
    mobile = models.CharField(max_length=15, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = StudentManager()

    USERNAME_FIELD = 'mobile'

    def __str__(self):
        return self.mobile
