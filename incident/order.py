from incident.base import IssueBase
from incident.groups import Groups


class OrderBase(IssueBase):
    send_to = Groups.Everyone


class Order:
    class Error(OrderBase):
        def __init__(self, exc):
            self.message = f'Order failed with exception: {exc!r}'
            super().__init__()

    class NotFilled(OrderBase):
        def __init__(self, order_id):
            self.message = f'Order failed to fill (id={order_id}), ensure market liquidity.'
            super().__init__()

    class Rejected(OrderBase):
        def __init__(self, response):
            self.message = f'Order rejected with response: {response}'
            super().__init__()
    
    class ErrorPlacing(OrderBase):
        def __init__(self, exc):
            self.issue_worthy = True
            self.message = f'Error placing order: {exc!r}'
            super().__init__()
