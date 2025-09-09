from redis import Redis
from snoop import snoop

@snoop
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
    rds = Redis(host=redis_host, port=redis_port, db=redis_db)
    assert rds is not None
    return rds
