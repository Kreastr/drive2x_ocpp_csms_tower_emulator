from redis import Redis


def get_default_redis():
    import sys
    redis_host = "redis"
    redis_port = 6379
    redis_db = 2
    if len(sys.argv) > 1:
        redis_host = sys.argv[1]
    if len(sys.argv) > 2:
        redis_port = int(sys.argv[2])
    if len(sys.argv) > 3:
        redis_db = int(sys.argv[3])
    return Redis(host=redis_host, port=redis_port, db=redis_db)
