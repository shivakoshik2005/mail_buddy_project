import os
from django.db import models

class EmailDraft(models.Model):
    TONE_CHOICES = [
        ('professional', 'Professional & Formal'),
        ('friendly', 'Friendly & Warm'),
        ('persuasive', 'Persuasive & Sales'),
        ('concise', 'Direct & Concise'),
        ('casual', 'Casual & Conversational'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
    ]

    receiver_name = models.CharField(max_length=255)
    receiver_email = models.EmailField()
    subject = models.CharField(max_length=255, blank=True)
    description = models.TextField(help_text="Core instructions for the email")
    tone = models.CharField(max_length=50, choices=TONE_CHOICES, default='professional')
    generated_body = models.TextField()
    attachment = models.FileField(upload_to='attachments/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def filename(self):
        if self.attachment:
            return os.path.basename(self.attachment.name)
        return None

    def __str__(self):
        return f"{self.subject or 'No Subject'} - {self.receiver_email}"