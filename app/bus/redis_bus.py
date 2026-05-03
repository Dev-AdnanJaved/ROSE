import redis.asyncio as redis
import json
from app.core.config import Config

r = redis.Redis(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    decode_responses=True
)

async def publish(channel, data):
    await r.publish(channel, json.dumps(data))

async def subscribe(channel):
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    return pubsub