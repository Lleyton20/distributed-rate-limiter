-- Sliding-window log, evaluated atomically inside Redis.
-- KEYS[1] = window key (sorted set of request timestamps)
-- ARGV[1] = limit (max requests per window)
-- ARGV[2] = window length in microseconds
-- ARGV[3] = unique member id for this request
-- Returns {allowed (0|1), remaining, retry_after_ms}

local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local member = ARGV[3]

local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000000 + tonumber(t[2])

-- Drop requests that have slid out of the window.
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count < limit then
  redis.call('ZADD', key, now, member)
  redis.call('PEXPIRE', key, math.ceil(window / 1000))
  return {1, limit - count - 1, 0}
end

-- Denied: the caller can retry once the oldest request leaves the window.
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local retry_after_ms = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
return {0, 0, retry_after_ms}
