import json
import os


def get_market_config(config_name):
    if not os.path.exists('api.json'):
        raise FileNotFoundError('api.json not found')
    config = json.load(open('api.json'))
    if not config.get(config_name):
        raise ValueError(f'No config for {config_name}')
    return config[config_name]
