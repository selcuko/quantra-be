import requests

token = 'REDACTED'


def endpoint(chat_id, text):
    """Telegram wrapper for sending notification messages."""
    return send_message(chat_id, text)


def send_message(chat_id, text):
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = {'chat_id': chat_id, 'text': text}
    response = requests.post(url, data=data)
    return response
