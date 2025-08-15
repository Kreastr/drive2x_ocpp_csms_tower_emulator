import asyncio
import logging
import ssl
from datetime import datetime
from time import sleep

import certifi
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
    uri = "wss://drive2x.lut.fi:443/ocpp/CP_ESS_01"

    ctx = ssl.create_default_context(cafile=certifi.where())  # <- CA bundle
    async with websockets.connect(uri, ssl=ctx,
            subprotocols=["ocpp2.0.1"],    # <-- or "ocpp2.0.1"
            open_timeout=20) as ws:              # optional: make errors clearer)
        cp = OCPPClient("CP_ESS_01", ws)
        asyncio.create_task(cp.start())

        boot_notification = BootNotification(
            charging_station=ChargingStationType(vendor_name="ACME Inc",
                                                 model="ACME Battery 1",
                                                 serial_number="00001",
                                                 firmware_version="0.0.1"),
            reason=BootReasonEnumType.power_up,
            custom_data={"vendorId": "ACME labs", "sn": 234}
        )
        boot_notification.extra_field = 5
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