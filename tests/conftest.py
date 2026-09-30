import os

import pytest
import redis

REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture
def redis_url():
    return REDIS_URL


@pytest.fixture
def r():
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        client.ping()
    except redis.ConnectionError:
        pytest.skip("Redis is not running")
    client.flushdb()
    yield client
    client.flushdb()
    client.close()
