import asyncio
import logging
import ssl
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from email.policy import default
from time import sleep

import certifi
import websockets
from ocpp.routing import on
from ocpp.v201 import ChargePoint, call_result
from logging import getLogger

from ocpp.v201.call import BootNotification, Heartbeat, StatusNotification, SetVariables
from ocpp.v201.datatypes import ChargingStationType, SetVariableDataType, ComponentType, GetVariableDataType, \
    GetVariableResultType, VariableType
from ocpp.v201.enums import ConnectorStatusEnumType, GetVariableStatusEnumType
from ocpp.v201.enums import BootReasonEnumType, Action, AttributeEnumType

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)


class OCPPClient(ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.settings: dict[str, dict[str, str]] = deepcopy({"ChargingStation": {}})

        self.settings["ChargingStation"]["SerialNumber"] = self.id

    @on(Action.get_variables)
    async def get_variables(self, get_variable_data):
        logger.warning("on get_variables")
        results = list()
        for dv in map(lambda x: GetVariableDataType(**x), get_variable_data):
            v : GetVariableDataType = GetVariableDataType(
                                variable = VariableType(**dv.variable),
                                component = ComponentType(**dv.component))
            if v.component.name not in self.settings:
                results.append(GetVariableResultType(variable=v.variable,
                                                     component=v.component,
                                                     attribute_status=GetVariableStatusEnumType.unknown_component))
            elif v.variable.name in self.settings[v.component.name]:
                results.append(GetVariableResultType(variable=v.variable,
                                                     component=v.component,
                                                     attribute_value=self.settings[v.component.name][v.variable.name],
                                                     attribute_type=AttributeEnumType.actual,
                                                     attribute_status=GetVariableStatusEnumType.accepted))
            else:
                results.append(GetVariableResultType(variable=v.variable,
                                                     component=v.component,
                                                     attribute_status=GetVariableStatusEnumType.unknown_variable))
        return call_result.GetVariables(results)


async def main():
    uri = "wss://drive2x.lut.fi:443/ocpp/CP_ESS_01"

    ctx = ssl.create_default_context(cafile=certifi.where())  # <- CA bundle
    async with websockets.connect(uri, ssl=ctx,
            subprotocols=["ocpp2.0.1"],    # <-- or "ocpp2.0.1"
            open_timeout=20) as ws:              # optional: make errors clearer)
        serial_number = "CP_ACME_BAT_00001"
        cp = OCPPClient(serial_number, ws)
        asyncio.create_task(cp.start())

        boot_notification = BootNotification(
            charging_station=ChargingStationType(vendor_name="ACME Inc",
                                                 model="ACME Battery 1",
                                                 serial_number=serial_number,
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