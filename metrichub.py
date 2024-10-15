from datetime import datetime, timedelta
from django.utils.text import slugify
from django.db.models import Sum
import json
import os

import pytz
from coingecko import CoinGecko
from coinmcap import CoinMarketCap
from quantapi.models import GlobalSymbol, MarketSymbol, GlobalSymbolMetrics, Tag, TagMetrics


def update_symbol(gs: GlobalSymbol):
    # Single symbol update
    cg = CoinGecko()
    cg_symbol = cg.coin_by_cid(gs.cid)
    if not cg_symbol['symbol'].upper() == gs.base:
        print('Symbol mismatch:', gs.base, cg_symbol['symbol'].upper())
        return
    gs.image = cg_symbol['image']['large']
    if not gs.image.startswith('http'):
        gs.image = cg_symbol['image']['small']
    gs.description = cg_symbol['description']['en']
    gs.homepage = cg_symbol['links']['homepage'][0] if cg_symbol.get('links', {}).get('homepage') else None
    gs.blockchain_site = cg_symbol.get('links', {}).get('blockchain_site')
    gs.whitepaper = cg_symbol.get('links', {}).get('whitepaper')
    gs.official_forum_url = cg_symbol.get('links', {}).get('official_forum_url')
    gs.chat_url = cg_symbol.get('links', {}).get('chat_url')
    gs.announcement_url = cg_symbol.get('links', {}).get('announcement_url') 
    gs.subreddit_url = cg_symbol['links']['subreddit_url'] if 'r/' in cg_symbol.get('links', {}).get('subreddit_url') else None
    gs.github_repo_url = cg_symbol.get('links', {}).get('repos_url', {}).get('github')  
    gs.genesis_date = cg_symbol.get('genesis_date')
    gs.sentiment_votes_up_percentage = cg_symbol.get('sentiment_votes_up_percentage')
    gs.sentiment_votes_down_percentage = cg_symbol.get('sentiment_votes_down_percentage')
    gs.watchlist_portfolio_users = cg_symbol.get('watchlist_portfolio_users')
    gs.market_cap_rank = cg_symbol.get('market_cap_rank')
    gs.twitter_followers = cg_symbol.get('community_data', {}).get('twitter_followers')
    gs.developer_data = cg_symbol.get('developer_data')

    gs.coingecko_response = json.dumps(cg_symbol) # Delete ?

    market_map = {
        'gate': 'GATEIO',
        'mxc': 'MEXC',
        'binance': 'BINANCE',
        'kucoin': 'KUCOIN',
        'okex': 'OKX',
        'bybit_spot': 'BYBIT',
        }
    volume_map = {
        'OTHER': 0,
    }
    bid_ask_spread = {}
    for ticker in cg_symbol['tickers']:
        if ticker['target']!= 'USDT':
            continue
        if excname := market_map.get(ticker['market']['identifier']):
            volume_map[excname] = ticker['converted_volume']['usd']
            bid_ask_spread[excname] = ticker['bid_ask_spread_percentage']
        else:
            volume_map['OTHER'] += ticker['converted_volume']['usd']
    gs.volume_distribution = volume_map  # type: ignore
    gs.bid_ask_spread_percentage_distribution = bid_ask_spread  # type: ignore

    try:
        metrics = gs.metrics
        assert metrics
    except GlobalSymbol.metrics.RelatedObjectDoesNotExist:
        metrics = GlobalSymbolMetrics(symbol=gs)

    mdata = cg_symbol['market_data']
    metrics.market_cap = mdata['market_cap']['usd']
    metrics.market_cap_change_24h = mdata['market_cap_change_24h']
    metrics.market_cap_change_percentage_24h = mdata['market_cap_change_percentage_24h']
    metrics.price = mdata['current_price']['usd']
    metrics.volume = mdata['total_volume']['usd']
    metrics.price_change_24h = mdata['price_change_24h']
    metrics.price_change_percentage_24h = mdata['price_change_percentage_24h']
    metrics.price_high_24h = mdata['high_24h']['usd']
    metrics.price_low_24h = mdata['low_24h']['usd']
    metrics.ath = mdata['ath']['usd']
    metrics.ath_date = mdata['ath_date']['usd']
    metrics.atl = mdata['atl']['usd']
    metrics.atl_date = mdata['atl_date']['usd']
    metrics.data_updated=mdata['last_updated']
    metrics.total_supply = mdata['total_supply']
    metrics.circulating_supply = mdata['circulating_supply']
    metrics.max_supply = mdata['max_supply']
    metrics.fully_diluted_valuation = mdata['fully_diluted_valuation']['usd']
    metrics.market_cap_fdv_ratio = mdata['market_cap_fdv_ratio']
    metrics.price_change_percentage_7d = mdata['price_change_percentage_7d']
    metrics.price_change_percentage_14d = mdata['price_change_percentage_14d']
    metrics.price_change_percentage_30d = mdata['price_change_percentage_30d']
    metrics.price_change_percentage_60d = mdata['price_change_percentage_60d']
    metrics.price_change_percentage_200d = mdata['price_change_percentage_200d']
    metrics.price_change_percentage_1y = mdata['price_change_percentage_1y']

    metrics.raw_payload = json.dumps(mdata)
    metrics.calculate()
    metrics.save()
    gs.save()

    # match with market symbols too
    ms = MarketSymbol.objects.filter(base=gs.base, quote='USDT')
    ms_update = []
    for m in ms:
        try:
            if m.symbol.metrics.market_cap < gs.metrics.market_cap:  # type: ignore
                m.symbol = gs  # type: ignore
                ms_update.append(m)
        except (GlobalSymbolMetrics.DoesNotExist, AttributeError):
            pass
    MarketSymbol.objects.bulk_update(ms_update, ['symbol'])


def update_symbol_metrics_mini(metrics: GlobalSymbolMetrics, cg_symbol: dict):
    metrics.market_cap = cg_symbol['market_cap']
    metrics.market_cap_change_24h = cg_symbol['market_cap_change_24h']
    metrics.market_cap_change_percentage_24h = cg_symbol['market_cap_change_percentage_24h']
    metrics.price = cg_symbol['current_price']
    metrics.volume = cg_symbol['total_volume']
    metrics.price_change_24h = cg_symbol['price_change_24h']
    metrics.price_change_percentage_24h = cg_symbol['price_change_percentage_24h']
    metrics.price_high_24h = cg_symbol['high_24h']
    metrics.price_low_24h = cg_symbol['low_24h']
    metrics.ath = cg_symbol['ath']
    metrics.ath_date = cg_symbol['ath_date']
    metrics.atl = cg_symbol['atl']
    metrics.atl_date = cg_symbol['atl_date']
    metrics.data_updated=cg_symbol['last_updated'] or datetime.now(pytz.UTC)
    metrics.total_supply = cg_symbol['total_supply']
    metrics.circulating_supply = cg_symbol['circulating_supply']
    metrics.max_supply = cg_symbol['max_supply']
    metrics.raw_payload = json.dumps(cg_symbol)
    metrics.calculate()
    return metrics


def update_all_coins_coingecko():
    cg = CoinGecko()
    print('Fetching all coins from CoinGecko...', end='\t', flush=True)
    cg_symbols = cg.all_coins_with_market_data()
    print('OK')
    symbols = GlobalSymbol.objects.all()

    symbols_to_create = {}
    symbols_to_update = {}

    # Create a dictionary of existing symbols for quick lookup
    existing_symbols = {s.cid: s for s in symbols}
    symbols_to_skip = {s.cid for s in GlobalSymbol.objects.filter(metrics__data_updated__gte=datetime.now(pytz.UTC)-timedelta(minutes=30))} 

    for cg_symbol in cg_symbols:
        cid = cg_symbol['id']
        if cid in symbols_to_skip:
            print('Skipping:', cg_symbol['name'])
            continue
        if cid in existing_symbols:
            gs = existing_symbols[cid]
            # Add the symbol for bulk update later
            gs.base = cg_symbol['symbol'].upper()
            gs.display = cg_symbol['name']
            gs.image = cg_symbol['image'] if cg_symbol['image'].startswith('http') else None
            if symbols_to_update.get(cid):
                print('Duplicate symbol:', gs)
                continue
            symbols_to_update[cid] = gs
        else:
            # Collect the new symbol to create
            gs = GlobalSymbol(
                cid=cg_symbol['id'],
                base=cg_symbol['symbol'].upper(),
                display=cg_symbol['name'],
                image=cg_symbol['image'] if cg_symbol['image'].startswith('http') else None,
            )
            if symbols_to_create.get(cid):
                print('Duplicate symbol:', gs)
                continue
            symbols_to_create[cid] = gs
            print('Prepared for creation:', gs)

    # Bulk create new symbols
    if symbols_to_create:
        GlobalSymbol.objects.bulk_create(symbols_to_create.values())
        print(f'Created {len(symbols_to_create)} new symbols')

    # Bulk update existing symbols
    if symbols_to_update:
        GlobalSymbol.objects.bulk_update(symbols_to_update.values(), ['base', 'display', 'image'])
        print(f'Updated {len(symbols_to_update)} existing symbols')


def update_all_coins_coingecko_metrics():
    metrics_to_save = []
    symbols_to_create_metrics = [gs for gs in GlobalSymbol.objects.filter(metrics__isnull=True)]
    metrics_to_create = []

    # Create symbol metrics
    for gs in symbols_to_create_metrics:
        metrics = GlobalSymbolMetrics(symbol=gs, data_updated=datetime.now(pytz.UTC))
        metrics_to_create.append(metrics)
        print('Prepared metrics to create for:', gs)
    
    if metrics_to_create:
        GlobalSymbolMetrics.objects.bulk_create(metrics_to_create)
        print(f'Created {len(metrics_to_create)} symbol metrics')

    symbols = {gs.cid: gs for gs in GlobalSymbol.objects.select_related('metrics')}

    # Update symbol metrics
    for cg_symbol in CoinGecko().all_coins_with_market_data():
        symbol = symbols[cg_symbol['id']]
        metrics = update_symbol_metrics_mini(symbol.metrics, cg_symbol)
        print('Prepared metrics to update for:', symbol)
        metrics_to_save.append(metrics)

    updated_count = GlobalSymbolMetrics.objects.bulk_update(
        metrics_to_save, 
        ['market_cap', 'market_cap_change_24h', 'market_cap_change_percentage_24h', 'price', 'volume', 'price_change_24h', 'price_change_percentage_24h', 'price_high_24h', 'price_low_24h', 'ath', 'ath_date', 'atl', 'atl_date', 'data_updated', 'total_supply', 'circulating_supply', 'max_supply', 'raw_payload'],
        batch_size=1000)
    print(f'Updated {updated_count} symbol metrics')



def match_symbols():
    gs = GlobalSymbol.objects.filter().select_related('metrics').exclude(metrics__market_cap__isnull=True, metrics__volume__isnull=True).order_by('-metrics__market_cap')
    ms = MarketSymbol.objects.filter(quote='USDT', symbol__isnull=True)
    ms = [m for m in ms if m.base in {s.base for s in gs}]
    ms_to_update = []
    for symbol in gs:
        market_symbols = [m for m in ms if m.base == symbol.base and m.symbol is None]
        for msymbol in market_symbols:
            msymbol.symbol = symbol  # type: ignore
            ms_to_update.append(msymbol)
        print('.', end='', flush=True)
    MarketSymbol.objects.bulk_update(ms_to_update, ['symbol'])


def update_all_tags():
    cg = CoinGecko()
    payload = cg.categories()
    
    # Fetch all existing tags to avoid repetitive queries
    existing_tags = {tag.name: tag for tag in Tag.objects.all()}
    
    tags_to_update = []
    tags_to_create = []
    metrics_to_update = []
    metrics_to_create = []

    for category in payload:
        tag = existing_tags.get(category['id'])
        
        if tag:
            # Update tag if it already exists
            tag.display = category['name']
            tag.description = category['content']
            tags_to_update.append(tag)
        else:
            # Create new tag
            tag = Tag(
                name=category['id'],
                display=category['name'],
                description=category['content']
            )
            tags_to_create.append(tag)
        
        # Handle tag metrics (create if not exists)
        try:
            metrics = tag.metrics
        except Tag.metrics.RelatedObjectDoesNotExist:
            metrics = TagMetrics(tag=tag)
            metrics_to_create.append(metrics)
        
        # Update metrics with new data
        assert metrics
        metrics.market_cap = category['market_cap']
        metrics.market_cap_change_24h = category['market_cap_change_24h']
        metrics.volume = category['volume_24h']
        metrics.data_updated = category['updated_at']
        metrics_to_update.append(metrics)

    # Bulk create and update tags
    if tags_to_create:
        Tag.objects.bulk_create(tags_to_create)
    
    if tags_to_update:
        Tag.objects.bulk_update(tags_to_update, ['display', 'description'])
    
    # Bulk create TagMetrics
    if metrics_to_create:
        TagMetrics.objects.bulk_create(metrics_to_create)
    
    # Bulk update TagMetrics
    if metrics_to_update:
        TagMetrics.objects.bulk_update(
            metrics_to_update, 
            ['market_cap', 'market_cap_change_24h', 'volume', 'data_updated']
        )

from django.db import transaction

def cmc_match_tags():
    # DO NOT USE
    # we migrated to using only coingecko
    cmc = CoinMarketCap()
    cmc_symbols = cmc.listings()['data']
    gsymbols = {gs.cid: gs for gs in GlobalSymbol.objects.all()}
    
    all_tags = {tag.name: tag for tag in Tag.objects.all()}
    
    tags_to_create = set()
    symbol_tag_relations = []

    for cmc_symbol in cmc_symbols:
        try:
            symbol = gsymbols[cmc_symbol['id']]
        except KeyError:
            print('Symbol not found:', cmc_symbol['slug'])
            continue
        
        # Existing tags associated with the symbol
        existing_tags = [all_tags[tag_name] for tag_name in cmc_symbol['tags'] if tag_name in all_tags]
        
        # Find missing tags
        missing_tags = set(cmc_symbol['tags']) - set(all_tags.keys())
        if missing_tags:
            print('Missing tags:', missing_tags)
            tags_to_create.update(missing_tags)
        
        # Save the relationship for bulk creation later
        symbol_tag_relations.append((symbol, existing_tags, cmc_symbol['tags']))
    
    # Bulk create missing tags
    if tags_to_create:
        new_tags = [Tag(name=tag_name) for tag_name in tags_to_create]
        created_tags = Tag.objects.bulk_create(new_tags)
        
        # Update all_tags with newly created tags
        for tag in created_tags:
            all_tags[tag.name] = tag
    
    # Create missing TagMetrics for newly created tags and link to symbols
    new_tag_metrics = []
    through_model_entries = []

    for symbol, existing_tags, cmc_tags in symbol_tag_relations:
        # Get tags for the symbol (existing and newly created)
        tags_for_symbol = [all_tags[tag_name] for tag_name in cmc_tags]
        
        # Collect through-model data for bulk_create
        for tag in tags_for_symbol:
            through_model_entries.append(
                symbol.tags.through(symbol_id=symbol.id, tag_id=tag.pk)
            )
        
        # Create TagMetrics for any newly created tags
        for tag_name in cmc_tags:
            if tag_name in tags_to_create:
                new_tag_metrics.append(TagMetrics(tag=all_tags[tag_name]))

    # Bulk create TagMetrics for new tags
    TagMetrics.objects.bulk_create(new_tag_metrics)
    
    # Bulk insert the many-to-many relationship through the intermediary table
    with transaction.atomic():
        GlobalSymbol.tags.through.objects.bulk_create(through_model_entries, ignore_conflicts=True)


def cg_match_tags():
    folder_name = 'cg-payloads'
    tags = Tag.objects.all()
    tags = {tag.display: tag for tag in tags}
    symbols = GlobalSymbol.objects.prefetch_related('tags', 'symbols').filter(tags__isnull=True).exclude(symbols__isnull=True).distinct()
    missing = set()

    for s in symbols:
        if not os.path.exists(f'{folder_name}/{s.cid}.json'):
            print('Payload not found:', s.cid)
            continue
        with open(f'{folder_name}/{s.cid}.json', 'r') as f:
            payload = json.load(f)
            for category in payload.get('categories', []):
                tag = tags.get(category)
                if tag:
                    s.tags.add(tag)
                else:
                    missing.add(category)

    print('Missing tags:', missing)
    if missing:
        create_missing_tags(missing)
        print('Created missing tags, recalling self')
        cg_match_tags()
    print('Done')


def create_missing_tags(tag_names):
    for tag_name in tag_names:
        name = slugify(tag_name)
        tag = Tag.objects.create(display=tag_name, name=name)
        TagMetrics.objects.create(tag=tag)


def calculate_tag_metrics():
    tags = Tag.objects.prefetch_related('metrics', 'symbols').filter(metrics__volume__isnull=True, metrics__market_cap__isnull=True, symbols__isnull=False).distinct()
    print('Calculating metrics for', tags.count(), 'tags')

    for tag in tags:
        assert tag.metrics
        aggregated = tag.symbols.aggregate(volume_sum=Sum('metrics__volume'), marketcap_sum=Sum('metrics__market_cap'))
        tag.metrics.volume = aggregated['volume_sum']
        tag.metrics.market_cap = aggregated['marketcap_sum']
        tag.metrics.save()

def calculate_tag_weights():
    update = []
    tags = Tag.objects.prefetch_related('metrics').filter(symbols__isnull=False)
    for tag in tags:
        tag.weight = tag.symbols.all().count()
        update.append(tag)
    Tag.objects.bulk_update(update, ['weight'])


def fix_missing_images():
    gs = GlobalSymbol.objects.exclude(image__startswith='http')
    gs.update(image=None)
