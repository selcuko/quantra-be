import traceback
from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from relay.telegram import send_message

class Issue(models.Model):
    class Level(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'
        CRITICAL = 'CRITICAL', 'Critical'
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        ACKNOWLEDGED = 'ACKNOWLEDGED', 'Acknowledged'
        IGNORED = 'IGNORED', 'Ignored'

    level = models.CharField(max_length=30, choices=Level.choices, default=Level.INFO)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ACTIVE)
    message = models.TextField()
    subject = models.CharField(max_length=250)
    traceback = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Generic relationship fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    object = GenericForeignKey()

    def __str__(self):
        return f'{self.status} {self.level} {self.subject}'

    @property
    def class_name(self):
        if (cls:=self.content_type.model_class()):
            return cls.__name__
        else:
            return 'Unknown'

    @classmethod
    def from_exception(cls, e:Exception, save=False):
        issue = cls()
        issue.traceback = traceback.format_exc()
        issue.message = repr(e)
        issue.subject = str(e)
        if save:
            issue.save()
        return issue



class Endpoint(models.Model):
    class Type(models.TextChoices):
        TELEGRAM = 'TELEGRAM'
    class Group(models.TextChoices):
        TRADER = 'TRADER'
        ADMIN = 'ADMIN'
        DEVOPS = 'DEVOPS'
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='endpoints')
    endpoint_type = models.CharField(max_length=30, choices=Type.choices)
    external_id = models.CharField(max_length=256)
    group = models.CharField(max_length=30, choices=Group.choices, default=Group.ADMIN)

    def __str__(self) -> str:
        return f'{self.endpoint_type} {self.external_id}'


class Notification(models.Model):
    class Severity(models.TextChoices):
        INFO = 'INFO'
        WARNING = 'WARNING'
        ERROR = 'ERROR'
        CRITICIAL = 'CRITICAL'
    class Type(models.TextChoices):
        ORDER = 'ORDER'
        SIGNAL = 'SIGNAL'
        EXCEPTION = 'EXCEPTION'
        CRASH = 'CRASH'
        DEBUG = 'DEBUG'
        LOG = 'LOG'

    class State(models.TextChoices):
        NEW = 'NEW'
        SENT = 'SENT'
        SENT_PARTIAL = 'SENT_PARTIAL'
        ERROR = 'ERROR'

    severity = models.CharField(max_length=30, choices=Severity.choices, default=Severity.INFO)
    notification_type = models.CharField(max_length=30, choices=Type.choices, default=Type.DEBUG)
    state = models.CharField(max_length=30, choices=State.choices, default=State.NEW)
    subject = models.CharField(max_length=256, null=True, blank=True)
    message = models.TextField()
    details = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    sent_to = models.ManyToManyField(Endpoint, related_name='notifications', blank=True)
    acknowledged_by = models.ManyToManyField(User, related_name='acknowledged_notifications', blank=True)

    def __str__(self) -> str:
        return f'{self.severity} {self.notification_type} {self.state} {self.subject or ""}'

    def send(self):
        if not self.pk:
            self.save()
        message = f'[{self.severity}] {self.message}'
        sent_to = []
        already_sent_to = self.sent_to.all()
        for endpoint in Endpoint.objects.all():
            if endpoint in already_sent_to:
                sent_to.append(endpoint)
                continue
            try:
                send_message(int(endpoint.external_id), message)
                sent_to.append(endpoint)
            except:
                pass
        self.sent_to.add(*sent_to)
        if len(sent_to) == 0:
            self.state = Notification.State.ERROR
        elif len(sent_to) < len(Endpoint.objects.all()):
            self.state = Notification.State.SENT_PARTIAL
        else:
            self.state = Notification.State.SENT
        self.save()
    
    def save(self, *args, **kwargs):
        if not self.subject:
            self.subject = f'{self.severity} {self.notification_type} Message (No Subject)'
        super().save(*args, **kwargs)

