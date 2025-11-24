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


import asyncio
import pyee.asyncio
from datetime import timedelta, datetime

from logging import getLogger, DEBUG

logger = getLogger(__name__)
logger.setLevel(DEBUG)


class AIOIntervalTrigger:

    def __init__(self, period : timedelta, name :str = ""):
        self.events = pyee.asyncio.AsyncIOEventEmitter()
        self.period = period
        self.keep_running = True
        self.task = asyncio.create_task(self._loop())
        self.name = name

    def subscribe(self, callback):
        self.events.on("timer", callback)

    def floor_period_towards_last_midnight(self, time : datetime):
        since = datetime.now().replace(microsecond=0,second=0,hour=0,minute=0)
        raw_s = (time - since).total_seconds()
        period_s = self.period.total_seconds()
        return since + timedelta(seconds=(raw_s // period_s) * period_s)


    async def _loop(self):
        last_event = self.floor_period_towards_last_midnight(datetime.now())
        while self.keep_running:
            await asyncio.sleep(1)
            floored = self.floor_period_towards_last_midnight(datetime.now())
            if floored > last_event:
                self.events.emit("timer")
                logger.warning(f"Emitting Timer interval {self.name}")
                last_event = floored

_main_setpoint_loop = None
def main_setpoint_loop():
    global _main_setpoint_loop
    if _main_setpoint_loop is None:
        _main_setpoint_loop = AIOIntervalTrigger(period=timedelta(minutes=5), name="Setpoint Timer")
    return _main_setpoint_loop


_client_measurand_loop = None
def client_measurand_loop():
    global _client_measurand_loop
    if _client_measurand_loop is None:
        _client_measurand_loop = AIOIntervalTrigger(period=timedelta(seconds=15), name="Measurand Timer")
    return _client_measurand_loop
