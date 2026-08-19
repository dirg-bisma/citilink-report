from django.db import models
from django.contrib.auth.models import User
import hashlib


class Project(models.Model):
    project_id = models.CharField(max_length=100, unique=True)
    period = models.CharField(max_length=50)  # e.g., "Winter 2026", "S26"
    year = models.IntegerField()
    month = models.IntegerField()  # 1-12
    template_path = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'projects'
        unique_together = [['project_id', 'year', 'month']]

    def __str__(self):
        return f"{self.project_id} {self.year}-{self.month:02d}"


class SourceFile(models.Model):
    FILE_TYPE_CHOICES = [
        ('WTT', 'Working Time Table'),
        ('PPRP', 'Perubahan Perencanaan'),
        ('GHP', 'Ground Handling Performance'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='files')
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    file_path = models.CharField(max_length=500)
    file_hash = models.CharField(max_length=64)  # SHA256
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(blank=True)
    parser_version = models.CharField(max_length=20, default='1.0')

    class Meta:
        db_table = 'source_files'
        unique_together = [['project', 'file_type', 'file_hash']]  # Idempotency

    def __str__(self):
        return f"{self.file_type} - {self.project}"

    @staticmethod
    def compute_hash(file_content):
        return hashlib.sha256(file_content).hexdigest()


class ScheduleVersion(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='schedules')
    parent_version = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    version_number = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    
    # Schedule fields (from WTT/PPRP)
    flight_number = models.CharField(max_length=20)
    origin = models.CharField(max_length=10)
    destination = models.CharField(max_length=10)
    flight_date = models.DateField()
    aircraft = models.CharField(max_length=20, blank=True)
    std = models.TimeField(null=True, blank=True)
    sta = models.TimeField(null=True, blank=True)
    atd = models.TimeField(null=True, blank=True)  # From WTT only
    ata = models.TimeField(null=True, blank=True)  # From WTT only
    
    # PPRP metadata
    pprp_letter = models.CharField(max_length=100, blank=True)
    pprp_date = models.DateField(null=True, blank=True)
    
    # Operational flag (from GHP match)
    operational_flag = models.BooleanField(default=False)  # 1 or 0
    
    # Audit
    source_wtt = models.ForeignKey(SourceFile, null=True, on_delete=models.SET_NULL, related_name='wtt_schedules')
    source_pprp = models.ForeignKey(SourceFile, null=True, on_delete=models.SET_NULL, related_name='pprp_schedules')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'schedule_versions'
        indexes = [
            models.Index(fields=['project', 'flight_number', 'flight_date']),
            models.Index(fields=['flight_number', 'flight_date', 'origin', 'destination']),  # Matching key
            models.Index(fields=['project', 'is_active']),
        ]

    def __str__(self):
        return f"{self.flight_number} {self.flight_date} v{self.version_number}"

    @property
    def matching_key(self):
        return f"{self.flight_number}|{self.flight_date}|{self.origin}|{self.destination}"
