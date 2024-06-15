import inspect
from tests.core import QuantTestCase
from markets import BinanceMarket, BybitMarket, GateIOMarket, KucoinMarket, OKXMarket, MEXCMarket, IMarket


class MarketSignatureTests(QuantTestCase):
    def setUp(self):
        self.ref_class = IMarket
        self.ref_methods = inspect.getmembers(self.ref_class, predicate=inspect.isfunction)

    def test_bybit_signature(self):
        # TODO: Add more markets
        markets = [BybitMarket]
        mismatches = []
        missing_methods = []
        for cls in markets:
            for name, method in self.ref_methods:
                if hasattr(cls, name):
                    cls_method = getattr(cls, name)
                    ref_signature = inspect.signature(method)
                    cls_signature = inspect.signature(cls_method)
                    if ref_signature != cls_signature:
                        mismatches.append(f"Signature mismatch in method {cls.__name__}.{name}: expected {ref_signature}, got {cls_signature}")
                else:
                    missing_methods.append(f"Method {name} not found in class {cls}")

        if mismatches or missing_methods:
            self.fail("\n".join(mismatches + missing_methods))


