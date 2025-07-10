from django.contrib import admin
from .models import UserProfile

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'storage_limit')

admin.site.register(UserProfile, UserProfileAdmin)
