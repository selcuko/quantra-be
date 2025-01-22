from datetime import datetime, timedelta
from django.utils.text import slugify
from django.db.models import Sum
import json
import os

import pytz
from coingecko import CoinGecko
from coinmcap import CoinMarketCap
from quantapi.models import GlobalSymbol, MarketSymbol, Tag


def update_symbol(gs: GlobalSymbol, payload: dict|None = None, match=False):
    # Single symbol update
    cg = CoinGecko()
    if payload:
        cg_symbol = payload
    else:
        cg_symbol = cg.coin_by_cid(gs.cid)
        with open("cg-payloads/{}.json".format(gs.cid), "w") as f:
            json.dump(cg_symbol, f)
    if not cg_symbol['symbol'].upper() == gs.base:
        print('Symbol mismatch:', gs.base, cg_symbol['symbol'].upper())
        return
    gs.image = cg_symbol['image']['large']
    if gs.image and not gs.image.startswith('http'):
        gs.image = cg_symbol['image']['small']
    gs.description = cg_symbol['description']['en']
    gs.homepage = cg_symbol['links']['homepage'][0] if cg_symbol.get('links', {}).get('homepage') else None
    gs.blockchain_site = cg_symbol.get('links', {}).get('blockchain_site')
    gs.whitepaper = cg_symbol.get('links', {}).get('whitepaper')
    gs.official_forum_url = cg_symbol.get('links', {}).get('official_forum_url')
    gs.chat_url = cg_symbol.get('links', {}).get('chat_url')
    gs.announcement_url = cg_symbol.get('links', {}).get('announcement_url')
    try:
        gs.subreddit_url = cg_symbol['links']['subreddit_url'] if 'r/' in cg_symbol["links"]["subreddit_url"] else None
    except (TypeError, KeyError):
        gs.subreddit_url = None
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


    mdata = cg_symbol['market_data']
    gs.market_cap = mdata['market_cap']['usd']
    gs.market_cap_change_24h = mdata['market_cap_change_24h']
    gs.market_cap_change_percentage_24h = mdata['market_cap_change_percentage_24h']
    gs.price = mdata['current_price']['usd'] if mdata.get('current_price') else None
    gs.volume = mdata['total_volume']['usd'] if mdata.get('total_volume') else None
    gs.price_change_24h = mdata['price_change_24h']
    gs.price_change_percentage_24h = mdata['price_change_percentage_24h']
    gs.price_high_24h = mdata.get('high_24h', {}).get('usd')
    gs.price_low_24h = mdata.get('low_24h', {}).get('usd')
    gs.ath = mdata.get('ath', {}).get('usd')
    gs.ath_date = mdata.get('ath_date', {}).get('usd')
    gs.atl = mdata.get('atl', {}).get('usd')
    gs.atl_date = mdata.get('atl_date', {}).get('usd')
    gs.data_updated=mdata['last_updated']
    gs.total_supply = mdata['total_supply']
    gs.circulating_supply = mdata['circulating_supply']
    gs.max_supply = mdata['max_supply']
    gs.fully_diluted_valuation = mdata.get('fully_diluted_valuation', {}).get('usd')
    gs.market_cap_fdv_ratio = mdata['market_cap_fdv_ratio']
    gs.price_change_percentage_7d = mdata['price_change_percentage_7d']
    gs.price_change_percentage_14d = mdata['price_change_percentage_14d']
    gs.price_change_percentage_30d = mdata['price_change_percentage_30d']
    gs.price_change_percentage_60d = mdata['price_change_percentage_60d']
    gs.price_change_percentage_200d = mdata['price_change_percentage_200d']
    gs.price_change_percentage_1y = mdata['price_change_percentage_1y']

    gs.raw_payload = json.dumps(mdata)
    gs.calculate()
    gs.save()

    # match with market symbols too
    if match:
        ms = MarketSymbol.objects.filter(base=gs.base, quote='USDT')
        ms_update = []
        for m in ms:
            try:
                if m.symbol.market_cap < gs.market_cap:  # type: ignore
                    m.symbol = gs  # type: ignore
                    ms_update.append(m)
            except (AttributeError, TypeError):
                pass
        MarketSymbol.objects.bulk_update(ms_update, ['symbol'])


def update_symbol_metrics_mini(gs: GlobalSymbol, cg_symbol: dict):
    gs.market_cap = cg_symbol['market_cap']
    gs.market_cap_change_24h = cg_symbol['market_cap_change_24h']
    gs.market_cap_change_percentage_24h = cg_symbol['market_cap_change_percentage_24h']
    gs.price = cg_symbol['current_price']
    gs.volume = cg_symbol['total_volume']
    gs.price_change_24h = cg_symbol['price_change_24h']
    gs.price_change_percentage_24h = cg_symbol['price_change_percentage_24h']
    gs.price_high_24h = cg_symbol['high_24h']
    gs.price_low_24h = cg_symbol['low_24h']
    gs.ath = cg_symbol['ath']
    gs.ath_date = cg_symbol['ath_date']
    gs.atl = cg_symbol['atl']
    gs.atl_date = cg_symbol['atl_date']
    gs.data_updated=cg_symbol['last_updated'] or datetime.now(pytz.UTC)
    gs.total_supply = cg_symbol['total_supply']
    gs.circulating_supply = cg_symbol['circulating_supply']
    gs.max_supply = cg_symbol['max_supply']
    gs.raw_payload = json.dumps(cg_symbol)
    gs.calculate()
    return gs


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

    for cg_symbol in cg_symbols:
        cid = cg_symbol['id']
        if cid in existing_symbols:
            gs = existing_symbols[cid]
            # Add the symbol for bulk update later
            gs.base = cg_symbol['symbol'].upper()
            gs.display = cg_symbol['name']
            gs.image = cg_symbol['image'] if cg_symbol['image'].startswith('http') else None
            if symbols_to_update.get(cid):
                # print('Duplicate symbol:', gs)
                continue
            symbols_to_update[cid] = gs
        else:
            # Collect the new symbol to create
            gs = GlobalSymbol(
                cid=cid,
                base=cg_symbol['symbol'].upper(),
                display=cg_symbol['name'],
                image=cg_symbol['image'] if cg_symbol['image'].startswith('http') else None,
            )
            if symbols_to_create.get(cid):
                # print('Duplicate symbol:', gs)
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
    symbols = {gs.cid: gs for gs in GlobalSymbol.objects.all()}
    symbols_to_update = []

    # Update symbol metrics
    for cg_symbol in CoinGecko().all_coins_with_market_data():
        symbol = symbols[cg_symbol['id']]
        symbol_updated = update_symbol_metrics_mini(symbol, cg_symbol)
        symbols_to_update.append(symbol_updated)
        print('Prepared to update for:', symbol)

    updated_count = GlobalSymbol.objects.bulk_update(
        symbols_to_update, 
        [
            'volume24h_to_mcap',
            'volume',
            'market_cap', 
            'market_cap_change_24h', 
            'market_cap_change_percentage_24h', 
            'price', 
            'volume', 
            'price_change_24h', 
            'price_change_percentage_24h', 
            'price_high_24h', 
            'price_low_24h', 
            'ath', 
            'ath_date', 
            'ath_prox', 
            'atl', 
            'atl_date', 
            'atl_prox', 
            'data_updated', 
            'total_supply', 
            'circulating_supply', 
            'max_supply', 
            'raw_payload'
        ],
        batch_size=1000)
    print(f'Updated {updated_count} symbols')


def match_symbols():
    gs = GlobalSymbol.objects.filter().exclude(market_cap__isnull=True, volume__isnull=True).order_by('-market_cap')
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

        # Update tags with new data
        tag.market_cap = category['market_cap']
        tag.market_cap_change_24h = category['market_cap_change_24h']
        tag.volume = category['volume_24h']
        tag.data_updated = category['updated_at']

    # Bulk create and update tags
    if tags_to_create:
        Tag.objects.bulk_create(tags_to_create)

    if tags_to_update:
        Tag.objects.bulk_update(tags_to_update, ['volume', 'market_cap', 'market_cap_change_24h', 'data_updated'])

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

    through_model_entries = []

    for symbol, existing_tags, cmc_tags in symbol_tag_relations:
        # Get tags for the symbol (existing and newly created)
        tags_for_symbol = [all_tags[tag_name] for tag_name in cmc_tags]
        
        # Collect through-model data for bulk_create
        for tag in tags_for_symbol:
            through_model_entries.append(
                symbol.tags.through(symbol_id=symbol.id, tag_id=tag.pk)
            )
    
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
        Tag.objects.create(display=tag_name, name=name)


def calculate_tag_metrics():
    tags = Tag.objects.prefetch_related('symbols').filter(volume__isnull=True, market_cap__isnull=True, symbols__isnull=False).distinct()
    print('Calculating metrics for', tags.count(), 'tags')

    for tag in tags:
        aggregated = tag.symbols.aggregate(volume_sum=Sum('volume'), marketcap_sum=Sum('market_cap'))
        tag.volume = aggregated['volume_sum']
        tag.market_cap = aggregated['marketcap_sum']
        tag.save()

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
