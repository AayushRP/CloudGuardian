from django.db import models
from django.contrib.auth.models import User, Group
import uuid

class UploadedFiles(models.Model):
    file_uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)  # NEW
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    original_title = models.CharField(max_length=200)
    file_description = models.CharField(max_length=300, blank=True)
    file_hash = models.CharField(max_length=128)  # SHA-512
    shared_users = models.ManyToManyField(User, related_name='shared_files_users', blank=True)
    shared_groups = models.ManyToManyField(Group, related_name='shared_files_groups', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateField(auto_now=True)
    
    def __str__(self):
        return f"{self.original_title} - {self.owner.username}"
    

class FileChunks(models.Model):
    main_file = models.ForeignKey(UploadedFiles, on_delete=models.CASCADE)
    chunk_file = models.FileField(upload_to='user_uploads/file_chunks/')
    aes_key = models.BinaryField(blank=True)  # store as raw bytes
    order = models.PositiveSmallIntegerField(blank=True)  # chunk order: 1, 2, 3
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateField(auto_now=True)
    
    class Meta:
        unique_together = ('main_file', 'chunk_file')  # Ensures each index is unique per file

    def __str__(self):
        return f"Chunk {self.chunk_name} of {self.main_file.original_title}"
    
    
class FileActivityLog(models.Model):
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('downloaded', 'Downloaded'),
        ('shared_updated', 'Permissions Updated'),
        ('deleted', 'Deleted'),
    ]

    file_uid = models.UUIDField(null=True, blank=True)  # NEW
    file_title = models.CharField(max_length=255)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True)  # e.g., users/groups added for sharing

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.file_title} - {self.action}"