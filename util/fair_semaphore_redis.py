"""
SPDX-License-Identifier: AGPL-3.0-or-later
Copyright (C) 2025 Lappeenrannan-Lahden teknillinen yliopisto LUT
Author: Aleksei Romanenko <aleksei.romanenko@lut.fi>


This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Funded by the European Union and UKRI. Views and opinions expressed are however those of the author(s) 
only and do not necessarily reflect those of the European Union, CINEA or UKRI. Neither the European 
Union nor the granting authority can be held responsible for them.
"""
import logging
from _pydatetime import datetime
from math import ceil
from uuid import uuid4

from redis import Redis

from logging import getLogger

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
            try:
                lock_current = lock_current.encode("utf-8")
            except Exception as e:
                logger.warning(f"Failed to encode lock_current {lock_current=} {e=}")
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
