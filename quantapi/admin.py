from django.contrib import admin

from quantapi.models import *


class BacktestAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'symbol', 'market', 'start', 'end', 'freq', 'status')
    search_fields = ('symbol', 'market',)
    list_filter = ('market', 'status')

class MarketAdmin(admin.ModelAdmin):
    list_display = ('exchange_name', 'friendly_name', 'testnet_enabled', 'trading_enabled', 'mainnet_enabled')
    search_fields = ('exchange_name', 'friendly_name')
    list_filter = ('exchange_name', 'testnet_enabled', 'trading_enabled', 'mainnet_enabled')


class SymbolAdmin(admin.ModelAdmin):
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
    list_display = ('__str__', 'oid', 'status', 'order_type', 'symbol', 'timestamp', 'force')
    search_fields = ('signal__session__symbol__name', 'signal__session__symbol__market__exchange_name')
    list_filter = ('status', 'order_type', 'force')


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'message', 'severity', 'notification_type', 'state')
    list_filter = ('severity', 'notification_type', 'state')
    search_fields = ('message', 'subject')

    actions = ['send']

    def send(self, request, queryset):
        for notification in queryset:
            notification.send()

admin.site.register(Market, MarketAdmin)
admin.site.register(Symbol, SymbolAdmin)
admin.site.register(Session, SessionAdmin)
admin.site.register(Signal, SignalAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(Subscription)
admin.site.register(Endpoint)
admin.site.register(Backtest, BacktestAdmin)
admin.site.register(WhitelistedUser)
admin.site.register(Strategy)
admin.site.register(Notification, NotificationAdmin)
