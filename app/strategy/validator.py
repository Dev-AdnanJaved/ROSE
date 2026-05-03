from app.core.config import Config

async def validate(symbol):

    if not Config.ENABLE_ANTI_SCAM:
        return True

    # extend filters here
    return True