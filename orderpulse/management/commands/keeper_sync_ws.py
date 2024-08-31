from decimal import Decimal
import json
import time
from django.core.management.base import BaseCommand, CommandError

from websockets.sync.client import connect, ClientConnection

from orderpulse.keeper import KeeperPool
from orderpulse.structures import Bid, Book, Delta
from quantapi.models import MarketSymbol


class Command(BaseCommand):

    def handle(self, *args, **options):
        buffer = []
        book_sync = None

        def get_book(payload):
            book = keeper.manager.create_book()
            for bid in payload['bids']:
                bid = Bid(Decimal(bid[0]), Decimal(bid[1]))
                book.bids[bid.price] = bid
            for ask in payload['asks']:
                ask = Bid(Decimal(ask[0]), Decimal(ask[1]))
                book.asks[ask.price] = ask
            return book

        def payload_to_delta(payload):
            bids = {Decimal(bid[0]): Bid(Decimal(bid[0]), Decimal(bid[1])) for bid in payload['bids']}
            asks = {Decimal(ask[0]): Bid(Decimal(ask[0]), Decimal(ask[1])) for ask in payload['asks']}
            delta = Delta(
                sequence=payload['sequence'],
                received=payload['received'],
                processed=payload['processed'],
                bids=bids,
                asks=asks,
                market='OKX'
            )
            return delta

        symbol = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, market__exchange_name='OKX', name='BTC-USDT')
        keeper = KeeperPool.get(symbol)
        keeper.start()

        uri = 'ws://localhost:8000/ws/orderbook/OKX/BTC-USDT/'
        try:
            socket: ClientConnection = connect(uri)
            print(f'Connected to {uri}')
        except Exception as e:
            raise CommandError(f'Failed to connect to {uri}: {e}')

        socket.send('{"type": "snapshot"}')

        while True:
            try:
                payload = json.loads(socket.recv())
                ptype = payload.get('type', 'NOTSET')
                if ptype == 'book':
                    book_sync = get_book(payload)
                elif ptype == 'delta':
                    if not book_sync:
                        print('BUFFERING', payload.get('sequence'))
                        buffer.append(payload)
                        continue
                    if buffer:
                        for d in buffer:
                            if d['sequence'] <= book_sync.sequence.value:
                                print(f'SKIPPING {d["sequence"]}', book_sync.sequence.value)
                                continue
                            print('APPLYING BUFFER', d.get('sequence'), book_sync.sequence.value)
                            Book.apply(book_sync, payload_to_delta(d))
                        buffer.clear()
                    delta = payload_to_delta(payload)
                    #print(f'APPLYING DELTA {delta.sequence}', book_sync.sequence.value)
                    Book.apply(book_sync, delta)
                    bids, asks = book_sync.get_best(count=1)
                    print(f'Bids: {bids[0].price:,.2f} {bids[0].size:,.5f}', end='\t')
                    print(f'Asks: {asks[0].price:,.2f} {asks[0].size:,.5f}')
            except KeyboardInterrupt:
                break