from django.contrib import admin

from relay.models import Endpoint, Issue, Notification


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'message', 'severity', 'notification_type', 'state')
    list_filter = ('severity', 'notification_type', 'state')
    search_fields = ('message', 'subject')

    actions = ['send']

    @admin.action(description="Send selected notifications to respective groups")
    def send(self, request, queryset):
        for notification in queryset:
            notification.send()


admin.site.register(Notification, NotificationAdmin)
admin.site.register(Issue)
admin.site.register(Endpoint)