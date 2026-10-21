from types import SimpleNamespace
from pipeline.premium_source import _deep_link, _urls


def test_telegram_start_link_parsing():
    assert _deep_link('https://t.me/FAP_UNDERGROUND_bot?start=abc123') == ('FAP_UNDERGROUND_bot','abc123')
    assert _deep_link('https://example.com/x') is None


def test_urls_include_caption_and_buttons():
    button=SimpleNamespace(url='https://short.example/token')
    markup=SimpleNamespace(inline_keyboard=[[button]])
    message=SimpleNamespace(text=None,caption='Open https://t.me/test_bot?start=x',reply_markup=markup)
    assert _urls(message)==['https://t.me/test_bot?start=x','https://short.example/token']
