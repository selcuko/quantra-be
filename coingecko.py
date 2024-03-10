


import json
from pprint import pprint
import time
import requests


class CoinGecko:
    def __init__(self, api_key:str='REDACTED') -> None:
        self.url = "https://api.coingecko.com/api/v3/"
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'x-cg-demo-api-key': self.api_key,
            "Accept": "application/json",
        })
        self.coins = self.coins_list()

    def handle_failed_request(self, response):
        if not response.ok:
            raise ValueError('CoinGecko API request failed with', response.status_code, response.text)

    def coins_list(self):
        uri = self.url + 'coins/list'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()

    def coins_list_market(self, vs_currency:str='usd', order:str='market_cap_desc', per_page:int=100, page:int=1, sparkline:bool=False, price_change_percentage:str='1h,24h,7d'):
        uri = self.url + f'coins/markets?vs_currency={vs_currency}&order={order}&per_page={per_page}&page={page}&sparkline={sparkline}&price_change_percentage={price_change_percentage}'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()
    
    def all_coins_with_market_data(self, vs_currency:str='usd', order:str='volume_desc', volmin=0):
        last_page = False
        page = 1
        all_coins = []
        while not last_page:
            try:
                coins = self.coins_list_market(vs_currency=vs_currency, order=order, per_page=250, page=page)
            except:
                print(f'Failed to get page {page}, sleeping for 5 seconds')
                time.sleep(5)
                continue
            all_coins += coins
            if len(coins) < 250:
                last_page = True
            print(f'Page {page} has {len(coins)} coins')
            page += 1
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
        uri = self.url + f'coins/{coin_id}'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()




if __name__ == '__main__':
    token = 'REDACTED'
    gc = CoinGecko(token)
    xrp = gc.all_coins_with_market_data()
    with open('cg-all.json', 'w') as f:
        f.write(json.dumps(xrp, indent=4))
