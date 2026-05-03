import json
from pathlib import Path

CACHE_FILE = Path("marketcap_cache.json")

marketcaps = {}

def load_cache():
    global marketcaps

    if CACHE_FILE.exists():
        marketcaps = json.loads(CACHE_FILE.read_text())

def save_cache():
    CACHE_FILE.write_text(json.dumps(marketcaps))

def get_marketcap(symbol):

    coin = symbol.replace("USDT", "").lower()

    return marketcaps.get(coin)

def update_cache(data):
    global marketcaps
    marketcaps = data
    save_cache()