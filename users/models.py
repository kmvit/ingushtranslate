from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.


class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Администратор"),
        ("representative", "Представитель республики"),
        ("translator", "Переводчик"),
        ("corrector", "Корректор"),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="translator", verbose_name="Роль")
    email = models.EmailField(unique=True, verbose_name="Email")
    phone = models.CharField(max_length=15, blank=True, verbose_name="Телефон")

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name", "last_name", "email"]

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_role_display()})"
