import re

def parse_signal(text):

    match = re.search(r"(?:#|\b)([A-Z]{2,8})\b", text.upper())

    if match:
        return match.group(1) + "USDT"

    return None