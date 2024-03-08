


import json
from pprint import pprint
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
    xrp = gc.coins_list_market()
    with open('cg-list-market.json', 'w') as f:
        f.write(json.dumps(xrp, indent=4))
