-- Token bucket, evaluated atomically inside Redis.
-- KEYS[1] = bucket key
-- ARGV[1] = capacity (max tokens)
-- ARGV[2] = refill rate (tokens per second)
-- ARGV[3] = cost of this request (tokens)
-- Returns {allowed (0|1), remaining tokens (string), retry_after_ms}
--
-- Time comes from the Redis server clock (TIME), not the app servers, so
-- every app instance sees the same "now" and clock skew between instances
-- cannot hand out extra tokens.

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000000 + tonumber(t[2]) -- microseconds

local state = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
if tokens == nil or ts == nil then
  tokens = capacity
  ts = now
end

-- Refill based on elapsed time, capped at capacity.
local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + (elapsed * rate / 1000000))

local allowed = 0
local retry_after_ms = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_after_ms = math.ceil((cost - tokens) / rate * 1000)
end

redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
-- An idle bucket refills completely after capacity/rate seconds, so the key
-- can expire then without changing behaviour. Keeps Redis memory bounded.
redis.call('PEXPIRE', key, math.ceil(capacity / rate * 1000) + 1000)

return {allowed, tostring(tokens), retry_after_ms}
