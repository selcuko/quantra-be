import json
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
    gs.homepage = cg_symbol['links']['homepage'][0] if cg_symbol['links']['homepage'] else None
    gs.blockchain_site = cg_symbol['links']['blockchain_site'] if cg_symbol['links']['blockchain_site'] else None
    gs.whitepaper = cg_symbol['links']['whitepaper'] if cg_symbol['links']['whitepaper'] else None
    gs.official_forum_url = cg_symbol['links']['official_forum_url'] if cg_symbol['links']['official_forum_url'] else None
    gs.chat_url = cg_symbol['links']['chat_url'] if cg_symbol['links']['chat_url'] else None
    gs.announcement_url = cg_symbol['links']['announcement_url'] if cg_symbol['links']['announcement_url'] else None
    gs.subreddit_url = cg_symbol['links']['subreddit_url'] if 'r/' in cg_symbol['links']['subreddit_url'] else None
    gs.github_repo_url = cg_symbol['links']['repos_url']['github'] if cg_symbol['links']['repos_url']['github'] else None
    gs.genesis_date = cg_symbol['genesis_date']
    gs.sentiment_votes_up_percentage = cg_symbol['sentiment_votes_up_percentage']
    gs.sentiment_votes_down_percentage = cg_symbol['sentiment_votes_down_percentage']
    gs.watchlist_portfolio_users = cg_symbol['watchlist_portfolio_users']
    gs.market_cap_rank = cg_symbol['market_cap_rank']
    gs.twitter_followers = cg_symbol['community_data']['twitter_followers']
    gs.developer_data = cg_symbol['developer_data'] if cg_symbol['developer_data'] else None

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
    for ticker in cg_symbol['tickers']:
        if ticker['target']!= 'USDT':
            continue
        if excname := market_map.get(ticker['market']['identifier']):
            volume_map[excname] = ticker['converted_volume']['usd']
        else:
            volume_map['OTHER'] += ticker['converted_volume']['usd']
    gs.volume_distribution = volume_map

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


def update_symbol_metrics_mini(gs: GlobalSymbol, cg_symbol: dict):
    try:
        metrics = gs.metrics
        assert metrics
    except GlobalSymbol.metrics.RelatedObjectDoesNotExist:
        metrics = GlobalSymbolMetrics(symbol=gs)

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
    metrics.data_updated=cg_symbol['last_updated']
    metrics.total_supply = cg_symbol['total_supply']
    metrics.circulating_supply = cg_symbol['circulating_supply']
    metrics.max_supply = cg_symbol['max_supply']
    metrics.raw_payload = json.dumps(cg_symbol)
    metrics.calculate()
    metrics.save()


def update_all_coins_coingecko():
    cg = CoinGecko()
    cg_symbols = cg.all_coins_with_market_data()
    symbols = GlobalSymbol.objects.all()

    for cg_symbol in cg_symbols:
        if symbols.filter(cid=cg_symbol['id']).exists():
            gs = symbols.get(cid=cg_symbol['id'])
        else:
            gs = GlobalSymbol.objects.create(
                cid=cg_symbol['id'],
                base=cg_symbol['symbol'].upper(),
                display=cg_symbol['name'],
                image=cg_symbol['image'] if cg_symbol['image'].startswith('http') else None,
            )
        update_symbol_metrics_mini(gs, cg_symbol)


def match_symbols():
    gs = GlobalSymbol.objects.all().order_by('-metrics__market_cap')
    for symbol in gs:
        market_symbols = MarketSymbol.objects.filter(
            base=symbol.base,
            quote='USDT',
            symbol__isnull=True
        )
        market_symbols.update(symbol=symbol)
        print('.', end='', flush=True)


def update_all_tags():
    cg = CoinGecko()
    payload = cg.categories()
    for category in payload:
        tag, created = Tag.objects.update_or_create(
                name=category['id'],
                defaults={
                    'display': category['name'],
                    'description': category['content'],
                }
            )
        tag.save()
        print('created' if created else 'updated', tag)
        try:
            metrics = tag.metrics
            assert metrics
        except Tag.metrics.RelatedObjectDoesNotExist:
            print('Creating metrics for', tag)
            metrics = TagMetrics.objects.create(tag=tag)
        
        metrics.market_cap = category['market_cap']
        metrics.market_cap_change_24h = category['market_cap_change_24h']
        metrics.volume = category['volume_24h']
        metrics.data_updated = category['updated_at']
        metrics.save()


def match_tags():
    cmc = CoinMarketCap()
    cmc_symbols = cmc.listings()['data']
    for cmc_symbol in cmc_symbols:
        try:
            symbol = GlobalSymbol.objects.get(cid=cmc_symbol['slug'])
        except GlobalSymbol.DoesNotExist:
            print('Symbol not found:', cmc_symbol['slug'])
        tags = Tag.objects.filter(name__in=cmc_symbol['tags'])
        symbol.tags.set(tags)
        missing_tags = set(cmc_symbol['tags']) - set(tags.values_list('name', flat=True))
        if missing_tags:
            print('Missing tags:', missing_tags)


def fix_missing_images():
    gs = GlobalSymbol.objects.exclude(image__startswith='http')
    gs.update(image=None)
