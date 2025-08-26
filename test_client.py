import asyncio
import logging
import ssl
import sys
import traceback
from copy import deepcopy
from datetime import datetime
from http.cookiejar import LoadError
from uuid import uuid4

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
from nicegui import ui, app, background_tasks, ElementFilter
from ocpp.v201 import enums

from itertools import count

from atfsm import AFSM, test_data_1 
from dataclasses import dataclass

from pyee.asyncio import AsyncIOEventEmitter

from typing import Any, Callable, Iterator, TypeVar, Generic


transaction_uml = """@startuml
[*] -> Idle
Idle -> Authorized : on authorized
Authorized -> RejectAuthorization : on authorized
RejectAuthorization -> Authorized
Idle -> CableConnected : if cable connected
CableConnected -> Idle : if cable disconnected
Authorized -> Transaction : if cable connected
CableConnected -> Transaction : on authorized
Transaction -> Transaction : on every report interval
Transaction -> Idle : if cable disconnected
Transaction -> Idle : on deauthorized
Authorized -> Idle : on deauthorized
@enduml
"""


_fsm = AFSM(uml=transaction_uml, se_factory=lambda x: str(x))
_fsm.write_enums("TxFSM")
    
from txfsm_enums import TxFSMState, TxFSMCondition, TxFSMEvent


logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_time_str():
    return datetime.now().isoformat()

@dataclass
class ConnectorModel:
    id : int
    auth : bool = False
    cable_connected : bool = False
    soc_wh : float = 50000.0
    usable_capacity : float = 70000.0

def get_transaction_fsm(connector : ConnectorModel):
    global TxFSMState, TxFSMCondition, TxFSMEvent
    fsm = AFSM[TxFSMState, TxFSMCondition, TxFSMEvent](uml=transaction_uml, se_factory=TxFSMState)

    fsm.apply_to_all_conditions(TxFSMCondition.if_cable_connected, lambda x: True)
    fsm.apply_to_all_conditions(TxFSMCondition.if_cable_disconnected, lambda x: False)
    return fsm

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

ET = TypeVar("ET")
class ResettableValue(Generic[ET]):

    def __init__(self, factory: Callable[[], ET]) -> None:
        self._factory = factory
        self._current : ET | None = None
        self.reset()

    def value(self) -> ET:
        if self._current is None:
            raise Exception("Value is not ready")
        return self._current
    
    def reset(self) -> None:
        self._current = self._factory()


class OCPPClient(ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.settings: dict[str, dict[str, str]] = deepcopy({"ChargingStation": {}})

        self.settings["ChargingStation"]["SerialNumber"] = self.id
        self.tid = None
        self.connectors  = dict((i+1, ConnectorModel(i+1)) for i in range(3))
        self.exit_flag = False

        self.hb_task = asyncio.create_task(self.heartbeat_task())
        self.st_task = asyncio.create_task(self.status_task())
        self._events = AsyncIOEventEmitter()
        self.tx_tasks = dict(map(lambda x: (
            x[0], asyncio.create_task(self.transaction_task(x[1]))), self.connectors.items()))


    async def transaction_task(self, connector : ConnectorModel):
        fsm = get_transaction_fsm(connector)


        _seq_no = ResettableIterator[int](factory=lambda:count(start=0,step=1))
        

        tx_id = ResettableValue[str](factory= lambda : str(uuid4()))

        #fsm.on(

        while True:
            await asyncio.sleep(1)

        await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.started,
                                        timestamp=get_time_str(),
                                        trigger_reason=TriggerReasonEnumType.authorized,
                                        seq_no=next(_seq_no),
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
                                                  seq_no=next(_seq_no),
                                                  transaction_info=TransactionType(transaction_id=tx_id
                                                                                     )
                                                    ))

        while True:
            if self.auth_status is None:
                await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.ended,
                                                      timestamp=get_time_str(),
                                                      trigger_reason=TriggerReasonEnumType.authorized,
                                                      seq_no=next(_seq_no),
                                                      transaction_info=TransactionType(transaction_id=tx_id
                                                                                     )
                                                      ))
                break
            if not self.cable_connected:
                await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.ended,
                                                      timestamp=get_time_str(),
                                                      trigger_reason=TriggerReasonEnumType.cable_plugged_in,
                                                      seq_no=next(_seq_no),
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
        if self.tx_task is None:
            return call_result.RequestStopTransaction(status=RequestStartStopStatusEnumType.rejected)
        logger.warning(f"on request_stop_transaction {data}")
        self.auth_status = None
        await self.tx_task
        self.tx_task = None
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


cp : OCPPClient | None = None

@ui.page("/")
async def main():
    global cp
    uri = "ws://localhost:9000"
    if len(sys.argv) > 1:
        uri = sys.argv[1]
    if len(sys.argv) > 2:
        uri = sys.argv[2]
        serial_number = "CP_ACME_BAT_" + sys.argv[2]
    else:
        serial_number = "CP_ACME_BAT_0000"
        
    #"wss://emotion-test.eu/ocpp/1"
    #uri = "wss://drive2x.lut.fi:443/ocpp/CP_ESS_01"

    ctx = ssl.create_default_context(cafile=certifi.where())  # <- CA bundle
    ws_args: dict[str, Any] = dict(subprotocols=["ocpp2.0.1"],
               open_timeout=5)
    if uri.startswith("wss://"):
        ws_args["ssl"] = ctx
    async with websockets.connect(uri, **ws_args) as ws:
        cp = OCPPClient(serial_number, ws)

        for client in app.clients('/'):
            with client:
                for tgl in ElementFilter(kind=ui.toggle,marker="plug_tgl"):
                    tgl.bind_value(cp, "cable_connected")

        cp_task = asyncio.create_task(cp.start())

        boot_notification = BootNotification(
            charging_station=ChargingStationType(vendor_name="ACME Inc",
                                                 model="ACME Battery 1",
                                                 serial_number=serial_number,
                                                 firmware_version="0.0.1"),
            reason=BootReasonEnumType.power_up,
            custom_data={"vendorId": "ACME labs", "sn": 234}
        )
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
    ui.label("Power plug status")
    tgl = ui.toggle({True: "CONNECTED", False: "DISCONNECTED"}).mark("plug_tgl")
    if cp is not None:
        tgl.bind_value(cp, "cable_connected")
    ui.label("SoC")
    ui.button("Reset SoC", on_click=lambda: None)

# Dummy call to generate enum modules on every run
get_transaction_fsm(ConnectorModel(id=0))

ui.run(host="0.0.0.0", port=7500)
