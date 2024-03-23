from django.contrib import admin
from django.http import HttpRequest

from quantapi.models import *


class BacktestAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'symbol', 'market', 'start', 'end', 'freq', 'status')
    search_fields = ('symbol', 'market',)
    list_filter = ('market', 'status')


class MarketAdmin(admin.ModelAdmin):
    list_display = ('exchange_name', 'friendly_name', 'testnet_enabled', 'trading_enabled', 'mainnet_enabled')
    search_fields = ('exchange_name', 'friendly_name')
    list_filter = ('exchange_name', 'testnet_enabled', 'trading_enabled', 'mainnet_enabled')


class MarketSymbolAdmin(admin.ModelAdmin):
    list_display = ('name', 'market', 'base', 'quote', 'spot_trading_enabled', 'margin_trading_enabled')
    search_fields = ('name', 'base', 'quote')
    list_filter = ('market__exchange_name', 'quote', 'spot_trading_enabled', 'margin_trading_enabled')


class SessionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'freq', 'status', 'started', 'ended', 'session_type', 'last_heartbeat', 'candle_source', 'use_heikin_ashi')
    search_fields = ('symbol__name', 'symbol__market__exchange_name')
    list_filter = ('freq', 'status', 'session_type', 'use_heikin_ashi', 'candle_source')
    readonly_fields = ('started', 'ended', 'last_heartbeat', 'symbol')


class SignalAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'side', 'symbol', 'price', 'timestamp')
    search_fields = ('session__symbol__name', 'session__symbol__market__exchange_name')
    readonly_fields = ('session', 'symbol')
    list_filter = ('side',)


class OrderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'oid', 'status', 'order_type','deal_funds', 'force')
    list_filter = ('status', 'order_type', 'force')
    raw_id_fields = ('signal', 'session')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related('signal__session__symbol', 'signal__session__symbol__market')

    def get_object(self, request, object_id, *args, **kwargs):
        obj = super().get_object(request, object_id, **kwargs)
        if obj:
            print('Returning object', obj)
        return obj

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

    @staticmethod
    def send(request, queryset):
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

    def get_markets(self, obj):
        return json.loads(obj.available_markets)
    
    # enable vol0 filter by default





class ComplexOrderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status', 'type', 'session', 'deal_funds')
    search_fields = ('signal__session__symbol__name', 'session__symbol__market__exchange_name')
    list_filter = ('status', 'type', 'side', 'session__symbol__market__exchange_name')
    readonly_fields = ('symbol_display',)

    def symbol_display(self, obj):
        return obj.session.symbol

    symbol_display.short_description = 'Symbol'


admin.site.register(GlobalSymbol, GlobalSymbolAdmin)
admin.site.register(Market, MarketAdmin)
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
