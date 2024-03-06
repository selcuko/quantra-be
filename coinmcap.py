

from pprint import pprint
import requests


class CoinMarketCap:
    def __init__(self, api_key) -> None:
        self.url = "https://pro-api.coinmarketcap.com/v1/"
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accept": "application/json",   
        })


    def handle_failed_request(self, response):
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
        uri = self.url + 'cryptocurrency/listings/latest'
        response = self.session.get(uri, params=params)
        self.handle_failed_request(response)
        return response.json()


if __name__ == '__main__':
    token = 'REDACTED'
    cmc = CoinMarketCap(token)
    pprint(cmc.listings())
