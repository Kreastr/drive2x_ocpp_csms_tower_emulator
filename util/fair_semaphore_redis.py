from _pydatetime import datetime
from math import ceil
from uuid import uuid4

from redis import Redis


class FairSemaphoreRedis:

    def __init__(self, name : str, n_users : int, redis : Redis, session_timeout : int = 10):
        self.session_timeout = session_timeout
        self.my_id = str(uuid4()).encode("utf-8")
        self.redis = redis
        self.name = name
        self.name_lock = name + ":lock"
        self.name_zset = name + ":queue"
        self.name_ctr = name + ":cntr"
        self.n_users = n_users
        self.acquired = False
        self.rank = None

    def __enter__(self):
        self.acquire()
        assert self.acquired
        return self

    def acquire(self):
        session_timeout = self.session_timeout
        t_now = datetime.now().timestamp()
        pipeline = self.redis.pipeline(True)
        lock_current = self.redis.get(self.name_lock)
        if lock_current is not None:
            lock_current = lock_current.encode("utf-8")
        mid = self.my_id
        if lock_current == mid:
            self.redis.expire(self.name_lock, int(ceil(session_timeout)))
            pipeline.zadd(self.name, {self.my_id: t_now})
            self.acquired = True
            self.rank = -1
            return
        else:
            if self.redis.ttl(self.name_lock) > session_timeout:
                self.redis.expire(self.name_lock, int(ceil(session_timeout)))
        # Delete stale requests and get them out of the queue
        pipeline.zremrangebyscore(self.name, '-inf', t_now - session_timeout)
        pipeline.zinterstore(self.name_zset, {self.name_zset: 1, self.name: 0})
        pipeline.incr(self.name_ctr)
        nonce = pipeline.execute()[-1]
        # Add myself to semaphore set and queue
        pipeline.zadd(self.name, {self.my_id: t_now})
        pipeline.zadd(self.name_zset, {self.my_id: nonce}, nx=True)
        pipeline.zrank(self.name_zset, self.my_id)
        rank = pipeline.execute()[-1]
        if rank < self.n_users:
            if self.redis.get(self.name_lock) == self.my_id or self.redis.setnx(self.name_lock, self.my_id):
                self.redis.expire(self.name_lock, int(ceil(session_timeout)))
                self.acquired = True
                self.rank = -1
                return
            elif not self.redis.ttl(self.name_lock):
                self.redis.expire(self.name_lock, int(ceil(session_timeout)))
                self.acquired = False
                self.rank = rank
                return

        self.acquired = False
        self.rank = rank
        return

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.free()

    def free(self):
        self.redis.expire(self.name_lock, 1)
        pipeline = self.redis.pipeline(True)
        pipeline.zrem(self.name, self.my_id)
        pipeline.zrem(self.name_zset, self.my_id)
        assert pipeline.execute()[0]
