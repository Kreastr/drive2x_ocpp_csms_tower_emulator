import asyncio
import logging
from datetime import datetime
from time import sleep

import websockets
from ocpp.routing import on
from ocpp.v201 import ChargePoint, call_result
from logging import getLogger

from ocpp.v201.call import BootNotification, Heartbeat, StatusNotification, SetVariables
from ocpp.v201.datatypes import ChargingStationType, SetVariableDataType, ComponentType
from ocpp.v201.enums import ConnectorStatusEnumType
from ocpp.v21.enums import BootReasonEnumType, Action

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

class OCPPClient(ChargePoint):
    @on(Action.get_variables)
    async def get_variables(self):
        logger.warning("on get_variables")
        return call_result.GetVariables([])


async def main():
    uri = "ws://localhost:9000/CP_ESS_01"
    async with websockets.connect(uri) as ws:
        cp = OCPPClient("CP_ESS_01", ws)
        asyncio.create_task(cp.start())

        boot_notification = BootNotification(
            charging_station=ChargingStationType(vendor_name="ACME Inc",
                                                 model="ACME Battery 1",
                                                 serial_number="00001",
                                                 firmware_version="0.0.1"),
            reason=BootReasonEnumType.power_up
        )
        await cp.call(boot_notification)

        while True:
            await asyncio.sleep(3)
            heartbeat = Heartbeat()
            await cp.call(heartbeat)
            status_notification = StatusNotification(timestamp=datetime.now().isoformat(),
                                                     connector_status=ConnectorStatusEnumType.occupied,
                                                     evse_id=0,
                                                     connector_id=0)
            await cp.call(status_notification)


        #await cp.send_periodic_soc()


if __name__ == '__main__':
    asyncio.run(main())