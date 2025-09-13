import asyncio
import pyee.asyncio
from datetime import timedelta, datetime


class SetpointIntervalTrigger:

    def __init__(self, period : timedelta):
        self.events = pyee.asyncio.AsyncIOEventEmitter()
        self.period = period
        self.keep_running = True
        self.task = asyncio.create_task(self._loop())

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
                last_event = floored

_main_setpoint_loop = None
def main_setpoint_loop():
    global _main_setpoint_loop
    if _main_setpoint_loop is None:
        _main_setpoint_loop = SetpointIntervalTrigger(period=timedelta(minutes=15))
    return _main_setpoint_loop