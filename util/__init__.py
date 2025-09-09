import logging
from _pydatetime import datetime
from _typing import TypeVar, Generic
from functools import wraps
from logging import getLogger
from typing import Callable, Iterator

from nicegui import ElementFilter

ET = TypeVar("ET")


class ResettableValue(Generic[ET]):

    def __init__(self, factory: Callable[[], ET]) -> None:
        self._factory = factory
        self._current : ET | None = None
        self.reset()
    
    @property
    def value(self) -> ET:
        if self._current is None:
            raise Exception("Value is not ready")
        return self._current
    
    def reset(self) -> None:
        self._current = self._factory()


ERT = TypeVar("ERT")


class ResettableIterator(Generic[ERT]):

    def __init__(self, factory: Callable[[], Iterator[ERT]]) -> None:
        self._factory = factory
        self._current : Iterator[ERT] | None = None
        self.reset()

    def __iter__(self) -> Iterator[ERT]:
        if self._current is None:
            raise Exception("Iterator is not ready")
        return self._current


    def __next__(self) -> ERT:
        if self._current is None:
            raise Exception("Iterator is not ready")
        return next(self._current)
    
    def reset(self) -> None:
        self._current = self._factory()


def get_time_str():
    return datetime.now().isoformat()


def setup_logging(name):
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    l2 = getLogger(name)
    assert l2 is not None
    logger: logging.Logger = l2
    logger.setLevel(logging.DEBUG)
    lr: logging.Handler | None = logging.lastResort
    assert lr is not None
    lr.setFormatter(formatter)
    lr.setLevel(logging.DEBUG)
    return logger


def time_based_id():
    return int((datetime.now() - datetime(2025, 1, 1)).total_seconds() * 10)


def any_of(*vargs):
    for v in vargs:
        if v():
            return True
    return False


def async_l(f, condition=None):
    async def wrapped_async():
        if condition is None or condition():
            return await f()
        return None
    return wrapped_async


def if_valid(checked_inputs):
    valid = True
    for inp in checked_inputs:
        valid = valid and inp.validate()
    return valid


async def broadcast_to(app, op, page, **filters):
    for client in app.clients(page):
        with client:
            for old in ElementFilter(**filters):
                op(old)


def log_async_call(log_sink):

    def log_call_inner(f):

        @wraps(f)
        async def wrapped_function(*vargs, **kwargs):
            log_sink(f"Called {f.__name__} with {vargs} {kwargs}")
            return await f(*vargs, **kwargs)

        wrapped_function.__name__ = f.__name__
        return wrapped_function

    return log_call_inner
