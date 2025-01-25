


import json
import os
import time
import requests


API_KEYS = [
    'REDACTED',
    'REDACTED',
    'REDACTED'
]


class CoinGecko:
    def __init__(self) -> None:
        
        self.url = "https://api.coingecko.com/api/v3/"
        self.api_key = API_KEYS[0]
        self.key_cache = {}
        for key in API_KEYS:
            self.key_cache[key] = {
                '429': 0,
            }  
        self.session = requests.Session()
        self.session.headers.update({
            'x-cg-demo-api-key': self.api_key,
            "Accept": "application/json",
        })
        self.coins = self.coins_list()

    def rotate_key(self):
        for key in API_KEYS:
            last_used = self.key_cache[key]['429']
            if time.time() - last_used > 60:
                self.api_key = key
                self.session.headers.update({
                    'x-cg-demo-api-key': self.api_key,
                    "Accept": "application/json",
                })
                return
        print('No keys available, waiting for 5s')
        time.sleep(5)
        return self.rotate_key()

    @staticmethod
    def handle_failed_request(response):
        if response.ok:
            return
        if response.status_code == 429:
            print('Rate limited, sleeping for a bit')
            time.sleep(15)
            return
        raise ValueError('CoinGecko API request failed with', response.status_code, response.text)

    def coins_list(self):
        uri = self.url + 'coins/list'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()

    def coins_list_market(self, vs_currency:str='usd', order:str='market_cap_desc', per_page:int=100, page:int=1, sparkline:bool=False, price_change_percentage:str='1h,24h,7d'):
        uri = self.url + f'coins/markets?vs_currency={vs_currency}&order={order}&per_page={per_page}&page={page}&sparkline={sparkline}&price_change_percentage={price_change_percentage}'
        # get tags too
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()
    
    def all_coins_with_market_data(self, vs_currency:str='usd', order:str='volume_desc', volmin=0):
        ts = time.time()
        fname = f'cg-cache.json'
        if os.path.exists(fname):
            with open(fname, 'r') as f:
                date_updated = os.path.getmtime(fname)
                hrs24 = 60*60*24
                if ts - date_updated < hrs24:
                    return json.loads(f.read())
        last_page = False
        page = 1
        all_coins = []
        error = 0
        while not last_page:
            try:
                coins = self.coins_list_market(vs_currency=vs_currency, order=order, per_page=250, page=page)
                time.sleep(1)
            except:
                self.key_cache[self.api_key] = {
                    '429': time.time(),
                }
                self.rotate_key()
                error += 1
                if error > len(API_KEYS) * 2:
                    print('Too many errors, stopping')
                    break
                # time.sleep(5)
                continue
            all_coins += coins
            if len(coins) < 250:
                last_page = True
            page += 1
        with open(fname, 'w') as f:
            f.write(json.dumps(all_coins, indent=4))
        return all_coins

    def coin_id(self, name:str):
        name = name.lower()
        name = name.replace('-usdt', '')
        for coin in self.coins:
            if coin['symbol'] == name:
                return coin['id']
        return None

    def coin(self, name:str):
        coin_id = self.coin_id(name)
        if not coin_id:
            return None
        return self.coin_by_cid(coin_id)

    def coin_by_cid(self, cid:str):
        uri = self.url + f'coins/{cid}'
        response = self.session.get(uri)
        if response.status_code == 429:
            self.key_cache[self.api_key] = {
                '429': time.time(),
            }
            self.rotate_key()
            return self.coin_by_cid(cid)
        return response.json()

    def categories(self):
        uri = self.url + 'coins/categories'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        payload = response.json()
        with open('categories.json', 'w') as f:
            f.write(json.dumps(payload, indent=4))
        return payload


if __name__ == '__main__':
    gc = CoinGecko()
    xrp = gc.categories()
