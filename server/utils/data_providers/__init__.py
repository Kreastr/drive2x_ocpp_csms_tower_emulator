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

import collections.abc
import json
import logging

from beartype import beartype
from redis_dict import RedisDict

from server.data import BookingDetails
from util import get_app_args, setup_logging
from util.db import get_default_redis

logger = setup_logging(__name__)
logger.setLevel(logging.INFO)


class BookingManager(collections.abc.MutableMapping):

    def __init__(self):
        self.db = RedisDict(f"csms_booking_details",
                            redis=get_default_redis(arg_provider=get_app_args))

    @beartype
    def __setitem__(self, key: str, value: BookingDetails, /):
        data = value.model_dump_json()
        logger.info(f"Will save to bookings {key=} {data=}")
        self.db[key] = data

    def __delitem__(self, key: str):
        del self.db[key]

    def __getitem__(self, key: str) -> BookingDetails:
        data = self.db[key]
        logger.info(f"Loaded from bookings {key=} {data=}")
        return BookingDetails.model_validate(json.loads(data))

    def __len__(self):
        return len(self.db)

    def __iter__(self):
        return iter(self.db)


booking_details = BookingManager()
