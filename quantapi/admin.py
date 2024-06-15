from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.db.models.query import QuerySet
from django.http import HttpRequest

from quantapi.models import *


class IssuesInline(GenericTabularInline):
    fields = ['level', 'status', 'subject']
    model = Issue
    extra = 0


class IssueAdmin(admin.ModelAdmin):
    list_filter = ('level', 'status')
    list_display = ('object', 'subject', 'level', 'status', 'created_at')


class BacktestAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'symbol', 'market', 'start', 'end', 'freq', 'status')
    search_fields = ('symbol', 'market',)
    list_filter = ('market', 'status')


class MarketAdmin(admin.ModelAdmin):
    list_display = ('exchange_name', 'prices_updated')
    search_fields = ('exchange_name', )
    list_filter = ('exchange_name', )


class MarketCredentialsAdmin(admin.ModelAdmin):
    list_display = ('market', 'owner', 'expires_at', 'internal', 'active')
    search_fields = ('market__exchange_name', 'owner')
    list_filter = ('market__exchange_name', 'internal', 'active')

    def get_queryset(self, request: HttpRequest) -> QuerySet[MarketCredentials]:
        return super().get_queryset(request).select_related('market')


class MarketAccountAdmin(admin.ModelAdmin):
    list_display = ('market', 'owner', 'equity', 'capital', 'last_cache')
    search_fields = ('owner', )
    list_filter = ('market__exchange_name', )
    inlines = [IssuesInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[MarketAccount]:
        return MarketAccount.objects.select_related('market')

class MarketSymbolAdmin(admin.ModelAdmin):
    list_display = ('name', 'market', 'base', 'quote', 'spot_trading_enabled', 'margin_trading_enabled')
    search_fields = ('name', 'base', 'quote')
    list_filter = ('market__exchange_name', 'quote', 'spot_trading_enabled', 'margin_trading_enabled')


class SessionAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'freq', 'status', 'started')
    search_fields = ('symbol__name', 'symbol__market__exchange_name')
    list_filter = ('freq', 'status', 'session_type', 'use_heikin_ashi', 'candle_source')
    readonly_fields = ('started', 'ended', 'last_heartbeat')
    raw_id_fields = ('symbol', 'strategy')
    inlines = [IssuesInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Session]:
        return Session.objects.select_related('symbol', 'strategy', 'symbol__market')


class SignalAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'side', 'symbol', 'price', 'timestamp')
    search_fields = ('session__symbol__name', 'session__symbol__market__exchange_name')
    list_filter = ('side',)
    raw_id_fields = ('session',)
    inlines = [IssuesInline]
    def get_queryset(self, request: HttpRequest) -> QuerySet[Signal]:
        return super().get_queryset(request).prefetch_related('session__symbol', 'session__symbol__market')


class OrderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'oid', 'status', 'order_type','deal_funds', 'force', 'created_at')
    list_filter = ('status', 'order_type', 'force')
    raw_id_fields = ('signal', 'session', 'symbol', 'account')
    inlines = [IssuesInline]
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related('signal__session__symbol', 'signal__session__symbol__market')

    def signal_display(self, obj):
        return obj.signal

    def session_display(self, obj):
        return obj.signal.session

    def symbol_display(self, obj):
        return obj.signal.session.symbol

    signal_display.short_description = 'Signal'
    session_display.short_description = 'Session'
    symbol_display.short_description = 'Symbol'


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'message', 'severity', 'notification_type', 'state')
    list_filter = ('severity', 'notification_type', 'state')
    search_fields = ('message', 'subject')

    actions = ['send']

    @admin.action(description="Send selected notifications to respective groups")
    def send(self, request, queryset):
        for notification in queryset:
            notification.send()


class GlobalSymbolAdmin(admin.ModelAdmin):
    class VolumeFilter(admin.SimpleListFilter):
        title = 'Hide no volumes'

        parameter_name = 'volume'

        def lookups(self, request, model_admin):
            return [
                ('vol100', 'Hide volume<=100'),
                ('volall', 'Show all volumes'),
            ]

        def queryset(self, request, queryset):
            """
            Returns the filtered queryset based on the value
            provided in the query string and retrievable via
            `self.value()`.
            """
            # Compare the requested value (either '80s' or '90s')
            # to decide how to filter the queryset.
            if self.value() == 'vol0' or self.value() is None:
                return queryset.filter(volume__gt=0)
            if self.value() == 'vol100':
                return queryset.filter(volume__gt=100)
            if self.value() == 'volall':
                pass
            return queryset

    list_display = ['name', 'volume', 'data_updated', 'data_source', 'markets']
    search_fields = ['name', 'data_source']
    list_filter = ['data_source', VolumeFilter]
    ordering = ['-volume']
    inlines = [IssuesInline]

    def get_markets(self, obj):
        return json.loads(obj.available_markets)


class ComplexOrderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status', 'type', 'session', 'deal_funds')
    list_filter = ('status', 'type', 'side',)
    raw_id_fields = ('session', 'market_order')
    inlines = [IssuesInline]


class SessionGroupAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'status', 'created_at', 'source')
    list_filter = ('status', 'source')
    inlines = [IssuesInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[SessionGroup]:
        return SessionGroup.objects.select_related('symbol', 'strategy')


admin.site.register(SessionGroup, SessionGroupAdmin)
admin.site.register(GlobalSymbol, GlobalSymbolAdmin)
admin.site.register(Market, MarketAdmin)
admin.site.register(MarketAccount, MarketAccountAdmin)
admin.site.register(MarketCredentials, MarketCredentialsAdmin)
admin.site.register(MarketSymbol, MarketSymbolAdmin)
admin.site.register(Session, SessionAdmin)
admin.site.register(Signal, SignalAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(Subscription)
admin.site.register(Endpoint)
admin.site.register(Backtest, BacktestAdmin)
admin.site.register(WhitelistedUser)
admin.site.register(Strategy)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(ComplexOrder, ComplexOrderAdmin)
admin.site.register(Issue, IssueAdmin)
