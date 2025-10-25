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


import base64
import io
import logging
from datetime import timedelta
from argparse import ArgumentParser
from datetime import datetime, timezone
from beartype.typing import TypeVar, Generic, Type
from functools import wraps
from logging import getLogger
from beartype.typing import Callable, Iterator

import qrcode
from beartype import beartype
from cachetools import cached
from camel_converter import dict_to_camel
from nicegui import ElementFilter, ui

import logging

from pydantic import BaseModel

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

ET = TypeVar("ET")


class ResettableValue(Generic[ET]):

    @beartype
    def __init__(self, factory: Callable[[], ET]) -> None:
        super().__init__()
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

    @beartype
    def __init__(self, factory: Callable[[], Iterator[ERT]]) -> None:
        super().__init__()
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
    return datetime.now(tz=timezone.utc).isoformat()


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
            result = await f(*vargs, **kwargs)
            log_sink(f"Returned from {f.__name__} with {result=}")
            return result

        wrapped_function.__name__ = f.__name__
        return wrapped_function

    return log_call_inner

def pil2base64(qr):
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    imb = buf.getvalue()
    logger.warning(imb)
    img: str = base64.b64encode(imb).decode("utf-8")
    logger.warning(img)
    return img

def qr_link(url):
    qr_dialog = None
    try:
        import PIL
        with ui.dialog() as dialog, ui.card():
            qr = qrcode.make(url)
            img = pil2base64(qr)
            ui.image("data:image/png;base64," + img).classes('w-80')
            ui.button('Close', on_click=dialog.close)
            qr_dialog = dialog
    except ImportError:
        pass
    return qr_dialog


CYCLE_DURATION = 15

@beartype
def get_slot_start(rtime : datetime, offset : int = 0 ):
    """

    :param rtime:
    :param offset:
    :return:

    >>> get_slot_start(datetime(2023, 8, 15, 10, 4, 37))
    datetime.datetime(2023, 8, 15, 10, 0)

    >>> get_slot_start(datetime(2023, 8, 15, 10, 4, 37), offset=1)
    datetime.datetime(2023, 8, 15, 10, 15)

    >>> get_slot_start(datetime(2023, 8, 15, 10, 54, 37), offset=1)
    datetime.datetime(2023, 8, 15, 11, 0)

    """
    minutes_since_hour_start = (((rtime.minute // CYCLE_DURATION) + offset) * CYCLE_DURATION)
    return rtime.replace(microsecond=0, second=0, minute=0) + timedelta(seconds=minutes_since_hour_start*60)


def get_slot_duration():
    return CYCLE_DURATION * 60


@cached(cache={})
def get_app_args():
    argparse = ArgumentParser(description="DriVe2X test CSMS implementation.", epilog="""
    Copyright (C) 2025 Lappeenrannan-Lahden teknillinen yliopisto LUT
    Author: Aleksei Romanenko <aleksei.romanenko@lut.fi>

    Funded by the European Union and UKRI. Views and opinions expressed are however those of the author(s) only and do 
    not necessarily reflect those of the European Union, CINEA or UKRI. Neither the European Union nor the granting authority 
    can be held responsible for them.""")
    argparse.add_argument("--redis_host", type=str, help="Host of Redis used by CSMS.", default="redis")
    argparse.add_argument("--redis_port", type=int, help="Port of Redis used by CSMS.", default=6379)
    argparse.add_argument("--redis_db", type=int, help="DB id of Redis used by CSMS.", default=2)
    argparse.add_argument("--ui_host", type=str, help="Host on which NiceGUI will listen to connections.",
                          default="0.0.0.0")
    argparse.add_argument("--ui_port", type=int, help="Port on which NiceGUI will open web service.", default=8000)
    return argparse.parse_args()


def log_req_response(f):
    _logger = getLogger("OCPP_PROTO")
    async def wrapped_call(self, *vargs, **kwargs):
        logger.error(f"Called log_req_response on {f.__name__}")
        _logger.info(f"\n==> {vargs=} {kwargs=}")
        result = await f(self, *vargs, **kwargs)
        _logger.info(f"\n<== {result=}")
        return result

    wrapped_call.__name__ = f.__name__
    wrapped_call.__doc__ = f.__doc__
    return wrapped_call


def with_request_model(model_class: Type[BaseModel]):
    def get_wrapper(f):
        async def wrapper(self, *vargs, **kwargs):
            logger.error(f"Called with_request_model on {f.__name__}")
            model = model_class.model_validate(kwargs)
            logger.warning(model)
            return await f(self, model, *vargs, **kwargs)

        wrapper.__name__ = f.__name__
        wrapper.__doc__ = f.__doc__
        return wrapper

    return get_wrapper


def async_camelize_kwargs(f):
    @wraps(f)
    async def wrapper(*vargs, **kwargs):
        logger.error(f"Called async_camelize_kwargs {f.__name__}")
        cckwargs = dict_to_camel(kwargs)
        return await f(*vargs, **cckwargs)
    wrapper.__name__ = f.__name__
    wrapper.__doc__ = f.__doc__
    return wrapper
