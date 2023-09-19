

def authentication_required(func):
    def wrapper(self, *args, **kwargs):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to use {func.__name__} on {self.name}')
        return func(self, *args, **kwargs)
    return wrapper