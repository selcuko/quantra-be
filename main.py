from pprint import pprint
import django
from models import OHLCVDataset
from strategy import get_strategy
django.setup()
from quantapi.models import Market


if __name__ == '__main__':
    market = Market.objects.get(exchange_name='MEXC')
    interface = market.get_interface()
    lk = interface.get_last_klines('APE-USDT', '15 min')
    ds = OHLCVDataset(lk)
    print(ds.tail(20))
    strategy = get_strategy('StrategyV1.Lisa.PandasTA')()
    stg_ds = strategy(ds)
    last = stg_ds.iloc[-1].to_dict()
    pprint(last)
