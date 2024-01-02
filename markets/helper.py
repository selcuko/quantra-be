from decimal import Decimal


def authentication_required(func):
    def wrapper(self, *args, **kwargs):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to use {func.__name__} on {self.name}')
        return func(self, *args, **kwargs)
    return wrapper

def float_to_precision(value: Decimal | float, precision: Decimal | float | int):
    precision = Decimal(str(precision))

    if precision <= 0:
        precision = 1
    if precision > 1:
        return round(float(str(value)), int())
    else:
        value = Decimal(str(value))
        return float((value // precision) * precision)



if __name__ == '__main__':
    x = Decimal('48.2395827894573298473')
    print(f'precision is 0.001: {float_to_precision(x, Decimal("0.001"))}')
    print(f'precision is 0.01: {float_to_precision(x, Decimal("0.01"))}')
    print(f'precision is 0.1: {float_to_precision(x, Decimal("0.1"))}')
    print(f'precision is 1: {float_to_precision(x, Decimal("1"))}')
    print(f'precision is 2: {float_to_precision(x, Decimal("2"))}')
    print(f'precision is 3: {float_to_precision(x, Decimal("3"))}')
