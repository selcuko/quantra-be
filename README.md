# Quantra API

## Populating Database

### Populate Markets

There should be a single record of Market object for each supported exchange. There is a fixture `quantapi/fixtures/markets.json` for populating markets:
```bash
python manage.py loaddata markets
```

### Populate MarketSymbols

There is a script `reload_markets` to populate MarketSymbol objects. This will create every supported symbol for each Market object.
```bash
python manage.py reload_markets
```

### Populate GlobalSymbols

Populating GlobalSymbols is a bit tricky as it involves remote API payloads and matching with MarketSymbols. This is done in several steps.

1. Fetch all symbol payloads from CoinGecko. Payloads will be stored in `cg-payloads` folder.
    ```bash
    python manage.py cg_fetch_symbols
    ```

2. Process payloads - this will create GlobalSymbol records where necessary.
    ```bash
    python manage.py reload_cg_payloads
    ```

3. Match GlobalSymbols with MarketSymbols
    ```bash
    python manage.py match_symbols
    ```