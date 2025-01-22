from django.contrib import admin
from django.db.models.query import QuerySet
from django.http import HttpRequest

from quantapi.models import *


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


class GlobalSymbolAdmin(admin.ModelAdmin):
    list_display = ['display', 'cid', 'base', 'volume', 'markets']
    search_fields = ['base', 'display', 'cid']
    ordering = ['-volume']

    def volume(self, obj):
        return obj.metrics.volume


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


admin.site.register(GlobalSymbol, GlobalSymbolAdmin)
admin.site.register(Market, MarketAdmin)
admin.site.register(MarketAccount, MarketAccountAdmin)
admin.site.register(MarketCredentials, MarketCredentialsAdmin)
admin.site.register(MarketSymbol, MarketSymbolAdmin)
admin.site.register(Tag, TagAdmin)
admin.site.register(ContactForm, ContactFormAdmin)
