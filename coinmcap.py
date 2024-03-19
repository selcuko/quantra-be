

import json
import os
from pprint import pprint
import time
import requests


class CoinMarketCap:
    def __init__(self, api_key:str='REDACTED') -> None:
        self.url = "https://pro-api.coinmarketcap.com/v1/"
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accept": "application/json",   
        })


    @staticmethod
    def handle_failed_request(response):
        if not response.ok:
            raise ValueError('CMC API request failed with', response.status_code, response.text)


    def categories(self):
        uri = self.url + 'cryptocurrency/categories'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()


    def global_metrics(self):
        uri = self.url + 'global-metrics/quotes/latest'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()


    def listings(self, **params):
        if os.path.exists('cmc-cache.json') and os.path.getmtime('cmc-cache.json') > time.time() - 60*60*4:
            with open('cmc-cache.json', 'r') as f:
                return json.loads(f.read())
        uri = self.url + 'cryptocurrency/listings/latest?limit=5000'
        response = self.session.get(uri, params=params)
        self.handle_failed_request(response)
        payload = response.json()
        with open('cmc-cache.json', 'w') as f:
            f.write(json.dumps(payload, indent=4))
        return payload

    def coin_info(self, name):
        uri = self.url + f'cryptocurrency/info?slug={name}'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()
    
    def get_all_coins(self):
        uri = self.url + f'cryptocurrency/info'
        response = self.session.get(uri)
        self.handle_failed_request(response)
        return response.json()



if __name__ == '__main__':
    token = 'REDACTED'
    cmc = CoinMarketCap(token)
    res = cmc.listings()
    with open('cmc-cache.json', 'w') as f:
        f.write(json.dumps(res, indent=4))
    pprint(res)
