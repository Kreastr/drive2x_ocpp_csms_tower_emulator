from redis import Redis
from snoop import snoop

@snoop
def get_default_redis():
    from . import get_app_args
    args = get_app_args()
    redis_host = args.redis_host
    redis_port = args.redis_port
    redis_db = args.redis_db
    rds = Redis(host=redis_host, port=redis_port, db=redis_db)
    assert rds is not None
    return rds
