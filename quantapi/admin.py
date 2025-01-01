from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.db.models.query import QuerySet
from django.http import HttpRequest

from quantapi.models import *


class IssuesInline(GenericTabularInline):
    fields = ['level', 'status', 'subject']
    model = Issue
    extra = 0


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
    list_display = ('name', 'market', 'base', 'quote', 'spot_trading_enabled', 'margin_trading_enabled', 'contract_type')
    search_fields = ('name', 'base', 'quote')
    list_filter = ('market__exchange_name', 'quote', 'spot_trading_enabled', 'margin_trading_enabled', 'contract_type')


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


class GlobalSymbolAdmin(admin.ModelAdmin):
    list_display = ['display', 'cid', 'base', 'volume', 'markets']
    search_fields = ['base', 'display', 'cid']
    ordering = ['-volume']

    def volume(self, obj):
        return obj.metrics.volume


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


class ContactFormAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'message', 'user_agent', 'created_at')
    search_fields = ('name', 'email', 'message', 'user_agent')
    list_filter = ('created_at', )
    readonly_fields = ('name', 'email', 'message', 'user_agent', 'created_at')


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
admin.site.register(Backtest, BacktestAdmin)
admin.site.register(Strategy)
admin.site.register(Tag, TagAdmin)
admin.site.register(ContactForm, ContactFormAdmin)
