import asyncio
import logging
import ssl
import sys
from copy import deepcopy
from datetime import datetime
from uuid import uuid4
from zipimport import cp437_table

import certifi
import websockets
from ocpp.routing import on
from ocpp.v201 import ChargePoint, call_result, call
from logging import getLogger

from ocpp.v201.call import BootNotification, Heartbeat, StatusNotification, SetVariables
from ocpp.v201.datatypes import ChargingStationType, SetVariableDataType, ComponentType, GetVariableDataType, \
    GetVariableResultType, VariableType, SetVariableResultType, TransactionType
from ocpp.v201.enums import ConnectorStatusEnumType, GetVariableStatusEnumType, SetVariableStatusEnumType, \
    RequestStartStopStatusEnumType, TransactionEventEnumType, TriggerReasonEnumType
from ocpp.v201.enums import BootReasonEnumType, Action, AttributeEnumType
from nicegui import ui, app, background_tasks
from ocpp.v201 import enums
logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

plug_tgl = None

def get_time_str():
    return datetime.now().isoformat()

class OCPPClient(ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.settings: dict[str, dict[str, str]] = deepcopy({"ChargingStation": {}})

        self.settings["ChargingStation"]["SerialNumber"] = self.id
        self.tid = None
        self.auth_status = None
        self.cable_connected = False
        self.tx_task = None
        self.soc_kwh = 50.0
        self.total_capacity_kwh = 70.0
        self._tx_seq_no = 0

        self.hb_task = asyncio.create_task(self.heartbeat_task())
        self.st_task = asyncio.create_task(self.status_task())

    @property
    def seq_no(self):
        self._tx_seq_no += 1
        return self._tx_seq_no - 1

    async def transaction_task(self, remote_start_id):
        self._tx_seq_no = 0
        tx_id = str(uuid4())
        await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.started,
                                        timestamp=get_time_str(),
                                        trigger_reason=TriggerReasonEnumType.authorized,
                                        seq_no=self.seq_no,
                                        transaction_info=TransactionType(transaction_id=tx_id,
                                                                         remote_start_id=remote_start_id,
                                                                         ),
                                        id_token=self.auth_status
                                        ))

        while not self.cable_connected:
            if self.auth_status is None:
                break
            await asyncio.sleep(1)

        if self.auth_status is not None:
            await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.updated,
                                                  timestamp=get_time_str(),
                                                  trigger_reason=TriggerReasonEnumType.cable_plugged_in,
                                                  seq_no=self.seq_no,
                                                  transaction_info=TransactionType(transaction_id=tx_id
                                                                                     )
                                                    ))

        while True:
            if self.auth_status is None:
                await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.ended,
                                                      timestamp=get_time_str(),
                                                      trigger_reason=TriggerReasonEnumType.authorized,
                                                      seq_no=self.seq_no,
                                                      transaction_info=TransactionType(transaction_id=tx_id
                                                                                     )
                                                      ))
                break
            if not self.cable_connected:
                await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.ended,
                                                      timestamp=get_time_str(),
                                                      trigger_reason=TriggerReasonEnumType.cable_plugged_in,
                                                      seq_no=self.seq_no,
                                                      transaction_info=TransactionType(transaction_id=tx_id
                                                                                     )
                                                      ))
                break

            await asyncio.sleep(1)

    async def heartbeat_task(self):
        while True:
            await asyncio.sleep(10)
            heartbeat = Heartbeat()
            await self.call(heartbeat)

    async def status_task(self):
        prev_status = self.cable_connected
        await self.post_status_notification()
        while True:
            await asyncio.sleep(1)
            if prev_status != self.cable_connected:
                await self.post_status_notification()
                prev_status = self.cable_connected

    async def post_status_notification(self):
        status_notification = StatusNotification(timestamp=datetime.now().isoformat(),
                                                 connector_status=ConnectorStatusEnumType.occupied if self.cable_connected else ConnectorStatusEnumType.available,
                                                 evse_id=1,
                                                 connector_id=1)
        await self.call(status_notification)

    @on(Action.request_stop_transaction)
    async def request_stop_transaction(self, **data):
        logger.warning(f"on request_stop_transaction {data}")
        self.auth_status = None
        await self.tx_task
        return call_result.RequestStopTransaction(status=RequestStartStopStatusEnumType.accepted)

    @on(Action.request_start_transaction)
    async def request_start_transaction(self, remote_start_id, id_token, **data):
        logger.warning(f"on request_start_transaction {(remote_start_id, id_token, data)}")
        self.auth_status = id_token
        self.tx_task = asyncio.create_task(self.transaction_task(remote_start_id))
        return call_result.RequestStartTransaction(status=RequestStartStopStatusEnumType.accepted,
                                                   transaction_id=None
                                                   )

    @on(Action.get_variables)
    async def get_variables(self, get_variable_data):
        logger.warning(f"on get_variables {get_variable_data}")
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
                value = self.settings[v.component.name][v.variable.name]

                results.append(GetVariableResultType(variable=v.variable,
                                                     component=v.component,
                                                     attribute_value=value,
                                                     attribute_type=AttributeEnumType.actual,
                                                     attribute_status=GetVariableStatusEnumType.accepted))
            else:
                results.append(GetVariableResultType(variable=v.variable,
                                                     component=v.component,
                                                     attribute_status=GetVariableStatusEnumType.unknown_variable))
        return call_result.GetVariables(results)

    @on(Action.set_variables)
    async def set_variables(self, set_variable_data):
        logger.warning(f"on set_variables {set_variable_data}")
        results = list()
        for dv in map(lambda x: SetVariableDataType(**x), set_variable_data):
            v: SetVariableDataType = SetVariableDataType(
                variable=VariableType(**dv.variable),
                component=ComponentType(**dv.component),
                attribute_value=dv.attribute_value)
            if v.component.name not in self.settings:
                results.append(SetVariableResultType(variable=v.variable,
                                                     component=v.component,
                                                     attribute_status=SetVariableStatusEnumType.unknown_component))
            elif v.variable.name not in self.settings[v.component.name]:
                results.append(SetVariableResultType(variable=v.variable,
                                                     component=v.component,
                                                     attribute_status=SetVariableStatusEnumType.unknown_variable))
            else:
                self.settings[v.component.name][v.variable.name] = v.attribute_value

                results.append(SetVariableResultType(variable=v.variable,
                                                     component=v.component,
                                                     attribute_type=AttributeEnumType.actual,
                                                     attribute_status=SetVariableStatusEnumType.accepted))
        return call_result.SetVariables(results)

@ui.page("/")
async def main():
    #uri = "ws://localhost:9000"
    #"wss://emotion-test.eu/ocpp/1"
    uri = "wss://drive2x.lut.fi:443/ocpp/CP_ESS_01"

    ctx = ssl.create_default_context(cafile=certifi.where())  # <- CA bundle
    async with websockets.connect(uri, ssl=ctx,
            subprotocols=["ocpp2.0.1"],    # <-- or "ocpp2.0.1"
            open_timeout=20) as ws:              # optional: make errors clearer)
        serial_number = "CP_ACME_BAT_" + (sys.argv[1] if len(sys.argv) > 1 else "0000")
        cp = OCPPClient(serial_number, ws)

        while plug_tgl is None:
            await asyncio.sleep(1)

        logger.warning("plug_tgl is ready")

        plug_tgl.bind_value(cp, "cable_connected")

        cp_task = asyncio.create_task(cp.start())

        boot_notification = BootNotification(
            charging_station=ChargingStationType(vendor_name="ACME Inc",
                                                 model="ACME Battery 1",
                                                 serial_number=serial_number,
                                                 firmware_version="0.0.1"),
            reason=BootReasonEnumType.power_up,
            custom_data={"vendorId": "ACME labs", "sn": 234}
        )
        boot_notification.extra_field = 5
        result : call_result.BootNotification = await cp.call(boot_notification)
        logger.warning(result)
        if result.status != enums.RegistrationStatusEnumType.accepted:
            raise Exception("Boot notification rejected")

        await cp_task
        await cp.hb_task
        await cp.st_task

@ui.page("/")
async def index():
    background_tasks.create_lazy(main(),name="main")
    ui.navigate.to("/status")

@ui.page("/status")
async def status():
    global plug_tgl
    ui.label("Power plug status")
    plug_tgl = ui.toggle({True: "CONNECTED", False: "DISCONNECTED"})
    ui.label("SoC")
    ui.button("Reset SoC", on_click=lambda: None)
ui.run(host="0.0.0.0", port=7500)
