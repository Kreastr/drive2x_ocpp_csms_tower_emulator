import asyncio
import logging
from datetime import datetime

import websockets
from ocpp.routing import on
from ocpp.v16.enums import RegistrationStatus
from ocpp.v201 import ChargePoint
from ocpp.v201 import call_result
from ocpp.v201.call import GetVariables
from ocpp.v201.datatypes import GetVariableDataType, ComponentType
from ocpp.v201.enums import Action
from ocpp.v21.enums import RegistrationStatusEnumType
from websockets.asyncio.server import serve
from logging import getLogger

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_time_str():
    return datetime.now().isoformat()


class OCPPServerHandler(ChargePoint):

    @on(Action.boot_notification)
    async def on_boot_notification(self,  charging_station, reason):
        logger.warning(f"id={self.id} boot_notification {charging_station=} {reason=}")
        #asyncio.create_task(self.call(GetVariables([GetVariableDataType(ComponentType.)])))
        return call_result.BootNotification(
            current_time=get_time_str(),
            interval=10,
            status=RegistrationStatusEnumType.accepted
        )

    @on(Action.status_notification)
    async def on_status_notification(self, **data):
        logger.warning(f"id={self.id} on_status_notification {data=}")
        return call_result.StatusNotification(
        )

    @on(Action.heartbeat)
    async def on_heartbeat(self, **data):
        logger.warning(f"id={self.id} on_heartbeat {data=}")
        return call_result.Heartbeat(
            current_time=get_time_str()
        )

async def on_connect(websocket):
    logger.warning(f"on client connect {websocket=}")
    cp = OCPPServerHandler("same_id", websocket)
    await cp.start()

async def main():
    logging.warning("main start")
    server = await websockets.serve(on_connect, '0.0.0.0', 9000)
    logging.warning("main server ready")
    await server.serve_forever()
    logging.warning("main exit")


if __name__ == '__main__':
    asyncio.run(main())