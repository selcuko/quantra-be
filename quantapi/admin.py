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
    list_display = ('related_class', 'subject', 'level', 'status', 'created_at')

    def get_queryset(self, request: HttpRequest) -> QuerySet[Issue]:
        return super().get_queryset(request).prefetch_related('object')
    
    def related_class(self, obj):
        return obj.object.__class__.__name__


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
    list_display = ('market', 'owner', '_equity', '_capital', 'last_cache')
    search_fields = ('owner', )
    list_filter = ('market__exchange_name', )
    inlines = [IssuesInline]

    def _equity(self, obj):
        return round(obj.equity, 2)

    def _capital(self, obj):
        return round(obj.capital, 2)

    def get_queryset(self, request: HttpRequest) -> QuerySet[MarketAccount]:
        return MarketAccount.objects.select_related('market', 'credentials')


class MarketSymbolAdmin(admin.ModelAdmin):
    list_display = ('name', 'market', 'base', 'quote', 'spot_trading_enabled', 'margin_trading_enabled')
    search_fields = ('name', 'base', 'quote')
    list_filter = ('market__exchange_name', 'quote', 'spot_trading_enabled', 'margin_trading_enabled')


class SessionAdmin(admin.ModelAdmin):
    list_display = ('symbol_name', 'exchange', 'equity', 'status', 'started')
    search_fields = ('symbol__name', 'symbol__market__exchange_name')
    list_filter = ('freq', 'status', 'session_type', 'use_heikin_ashi', 'candle_source')
    readonly_fields = ('started', 'ended', 'last_heartbeat')
    raw_id_fields = ('symbol', 'group', 'account')
    inlines = [IssuesInline]

    def symbol_name(self, obj):
        return obj.symbol.name

    def exchange(self, obj):
        try:
            return obj.account.market.exchange_name
        except:
            return None

    def get_queryset(self, request: HttpRequest) -> QuerySet[Session]:
        return Session.objects.select_related('strategy', 'symbol__market', 'group')


class SignalAdmin(admin.ModelAdmin):
    list_display = ('symbol_name', 'exchange', 'side', 'price', 'strategy', 'timestamp')
    search_fields = ('session__symbol__name', 'session__symbol__market__exchange_name')
    list_filter = ('side',)
    raw_id_fields = ('session', 'session', 'group')
    inlines = [IssuesInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Signal]:
        return super().get_queryset(request).select_related(
            'session__symbol__market', 
            'session__strategy',
            'group__symbol__market',
            'group__strategy'
    )

    def parent(self, obj):
        return obj.group or obj.session

    def symbol_name(self, obj):
        return self.parent(obj).symbol.name

    def exchange(self, obj):
        return self.parent(obj).symbol.market.exchange_name

    def strategy(self, obj):
        return f'{self.parent(obj).strategy.name} ({self.parent(obj).strategy.version})'


class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'symbol_name', 'exchange', 'side', 'size', 'status', 'created_at')
    list_filter = ('status', 'order_type', 'force')
    raw_id_fields = ('signal', 'session', 'symbol', 'account', 'group')
    inlines = [IssuesInline]
    
    def get_queryset(self, request: HttpRequest) -> QuerySet[Order]:
        return super().get_queryset(request).select_related('symbol__market', 'session__symbol__market', 'session__symbol', 'account')

    def symbol_name(self, obj):
        return obj.symbol.name

    def exchange(self, obj):
        try:
            return obj.symbol.market.exchange_name
        except:
            return None

    def size(self, obj):
        return round(obj.deal_funds or 0, 2)

    def order_id(self, obj):
        return obj.oid or 'No ID'


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
    list_display = ('symbol_name', 'exchange', 'equity', 'accounts', 'status', 'created_at')
    list_filter = ('status', 'source')
    inlines = [IssuesInline]
    raw_id_fields = ('symbol', 'interface')

    def symbol_name(self, obj):
        return obj.symbol.name
    
    def exchange(self, obj):
        try:
            return obj.interface.market.exchange_name
        except:
            return None

    def accounts(self, obj):
        return obj.sessions.count()

    def get_queryset(self, request: HttpRequest) -> QuerySet[SessionGroup]:
        return super().get_queryset(request).select_related('symbol__market', 'interface__market', 'strategy', 'market').prefetch_related('sessions')


class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'symbol_count', 'is_chain', 'is_portfolio', 'is_ecosystem')
    search_fields = ('name', )
    list_filter = ('is_chain', 'is_portfolio', 'is_ecosystem')

    def symbol_count(self, obj):
        return obj.symbols.count()

    def get_queryset(self, request: HttpRequest) -> QuerySet[Tag]:
        return super().get_queryset(request).prefetch_related('symbols')


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
admin.site.register(Strategy)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(Issue, IssueAdmin)
admin.site.register(Tag, TagAdmin)
