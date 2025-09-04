import asyncio
import logging
import ssl
import sys
from copy import deepcopy
from datetime import datetime
from functools import wraps
from uuid import uuid4

import certifi
import websockets
from beartype import beartype
from ocpp.routing import on
from ocpp.v201 import ChargePoint, call_result, call

from ocpp.v201.call import BootNotification, Heartbeat, StatusNotification
from ocpp.v201.datatypes import ChargingStationType, SetVariableDataType, ComponentType, GetVariableDataType, \
    GetVariableResultType, VariableType, SetVariableResultType, TransactionType, EVSEType
from ocpp.v201.enums import ConnectorStatusEnumType, GetVariableStatusEnumType, SetVariableStatusEnumType, \
    RequestStartStopStatusEnumType, TransactionEventEnumType, TriggerReasonEnumType
from ocpp.v201.enums import BootReasonEnumType, Action, AttributeEnumType
from nicegui import ui, app, background_tasks, ElementFilter
from ocpp.v201 import enums

from itertools import count

from pyee.asyncio import AsyncIOEventEmitter

from typing import Any

from redis import Redis

from client.data import EvseModel, TxFSMContext
from client.transaction_model import TxFSMType, transaction_uml
from tx_fsm_enums import TxFSMState, TxFSMCondition, TxFSMEvent
from util import ResettableValue, ResettableIterator, get_time_str, setup_logging

from redis_dict import RedisDict

from util.types import EVSEId, TransactionId

logger = setup_logging(__name__)
logger.setLevel(logging.DEBUG)


@beartype
class TxFSM(TxFSMType):
    def __init__(self, context : TxFSMContext):
        super().__init__(uml=transaction_uml,
                         context=context,
                         se_factory=TxFSMState)

        self._seq_no = ResettableIterator[int](factory=lambda: count(start=0, step=1))

        self.tx_id = ResettableValue[str](factory=lambda: str(uuid4()))

        self.on(TxFSMState.idle.on_exit, self.setup_transaction)
        self.on(TxFSMState.authorized.on_enter, self.inform_on_remote_start)
        self.on(TxFSMState.cable_connected.on_enter, self.inform_on_first_plugged_in)
        self.on(TxFSMState.transaction_cable_first.on_enter, self.inform_on_authorized_when_plugged)
        self.on(TxFSMState.stop_transaction_disconnected.on_enter, self.inform_on_end_transaction_disconnected)
        self.on(TxFSMState.stop_transaction_deauthorized.on_enter, self.inform_on_end_transaction_deauthorized)

        self.apply_to_all_conditions(TxFSMCondition.if_cable_connected, self.if_cable_connected)
        self.apply_to_all_conditions(TxFSMCondition.if_cable_disconnected, self.if_cable_disconnected)

    @staticmethod
    def if_cable_connected(ctxt : TxFSMContext, optional : Any):
        return ctxt.evse.cable_connected

    @staticmethod
    def if_cable_disconnected(ctxt : TxFSMContext, optional : Any):
        return not ctxt.evse.cable_connected


    async def setup_transaction(self, *vargs):
        self._seq_no.reset()
        self.tx_id.reset()
        self.context.evse.tx_id = self.tx_id.value

    async def call(self, *vargs, **kwargs):
        logger.warning(f"Calling {vargs} {kwargs}")
        assert self.context.cp_interface is not None
        await self.context.cp_interface.call(*vargs, **kwargs)

    async def inform_on_end_transaction_deauthorized(self, *vargs):
        await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.ended,
                                              timestamp=get_time_str(),
                                              trigger_reason=TriggerReasonEnumType.deauthorized,
                                              seq_no=next(self._seq_no),
                                              transaction_info=TransactionType(transaction_id=self.tx_id.value
                                                                               ),
                                              evse=EVSEType(id=self.context.evse.id)
                                              ))

    async def inform_on_end_transaction_disconnected(self, *vargs):
        await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.ended,
                                              timestamp=get_time_str(),
                                              trigger_reason=TriggerReasonEnumType.ev_communication_lost,
                                              seq_no=next(self._seq_no),
                                              transaction_info=TransactionType(transaction_id=self.tx_id.value,),
                                              evse=EVSEType(id=self.context.evse.id)
                                              ))

    async def inform_on_remote_start(self, *vargs):
        await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.started,
                                              timestamp=get_time_str(),
                                              trigger_reason=TriggerReasonEnumType.remote_start,
                                              seq_no=next(self._seq_no),
                                              transaction_info=TransactionType(transaction_id=self.tx_id.value,
                                                                               remote_start_id=self.context.remote_start_id,
                                                                               ),
                                              id_token=self.context.auth_status,
                                              evse=EVSEType(id=self.context.evse.id)
                                              ))

    async def inform_on_first_plugged_in(self, *vargs):
        await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.started,
                                              timestamp=get_time_str(),
                                              trigger_reason=TriggerReasonEnumType.cable_plugged_in,
                                              seq_no=next(self._seq_no),
                                              transaction_info=TransactionType(transaction_id=self.tx_id.value,
                                                                               ),
                                              id_token=self.context.auth_status,
                                              evse=EVSEType(id=self.context.evse.id)
                                              ))

    async def inform_on_authorized_when_plugged(self, *vargs):
        await self.call(call.TransactionEvent(event_type=TransactionEventEnumType.updated,
                                              timestamp=get_time_str(),
                                              trigger_reason=TriggerReasonEnumType.authorized,
                                              seq_no=next(self._seq_no),
                                              transaction_info=TransactionType(transaction_id=self.tx_id.value,
                                                                               remote_start_id=self.context.remote_start_id,
                                                                               ),
                                              id_token=self.context.auth_status,
                                              evse=EVSEType(id=self.context.evse.id)
                                              ))

def log_async_call(log_sink):

    def log_call_inner(f):

        @wraps(f)
        async def wrapped_function(*vargs, **kwargs):
            log_sink(f"Called {f.__name__} with {vargs} {kwargs}")
            return await f(*vargs, **kwargs)

        wrapped_function.__name__ = f.__name__
        return wrapped_function

    return log_call_inner


@beartype
class OCPPClient(ChargePoint):

    def __init__(self, redis_data, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.redis_data = redis_data
        self.settings: dict[str, dict[str, str]] = deepcopy({"ChargingStation": {}})

        self.settings["ChargingStation"]["SerialNumber"] = self.id
        self.tid = None
        self.task_contexts  = dict((i + 1, TxFSMContext(self.get_evse_data(i+1))) for i in range(3))
        self.exit_flag = False

        self.hb_task = asyncio.create_task(self.heartbeat_task())
        self._events = AsyncIOEventEmitter()

        self.tx_fsms : dict[int, TxFSMType] = dict(map(lambda x: (
            x[0], TxFSM(x[1])), self.task_contexts.items()))
        self.tx_tasks = dict(map(lambda x: (
            x[0], asyncio.create_task(self.transaction_task(x[1], 
                                                            self.tx_fsms[x[0]]))), 
                                      self.task_contexts.items()))
        self.st_tasks = dict(map(lambda x: (
            x[0], asyncio.create_task(self.status_task(x[1].evse))),
                                      self.task_contexts.items()))
    
    async def data_saver_task(self):
        while True:
            await asyncio.sleep(10)
            map(self.save_evse_data, self.task_contexts.items())

    def save_evse_data(self, i, v : EvseModel):
        record_hash = self.get_evse_hash(i)
        self.redis_data[record_hash] = v.to_json()
    
    @staticmethod
    def get_evse_hash(i):
        return f"evse-data-{i}"
        
    def get_evse_data(self, i) -> EvseModel:
        record_hash = self.get_evse_hash(i)
        if record_hash in self.redis_data:
            data = self.redis_data[record_hash]
        else:
            data = dict(id=i)
        return EvseModel.model_validate(data)

    async def transaction_task(self, context : TxFSMContext, fsm : TxFSMType):
        fsm.context.cp_interface = self

        while True:
            await asyncio.sleep(1)
            await fsm.loop()


    async def heartbeat_task(self):
        while True:
            await asyncio.sleep(10)
            heartbeat = Heartbeat()
            await self.call(heartbeat)

    async def status_task(self, evse : EvseModel):

        prev_status = evse.cable_connected
        await self.post_status_notification(evse)
        while True:
            await asyncio.sleep(1)

            if prev_status != evse.cable_connected:
                await self.post_status_notification(evse)
                prev_status = evse.cable_connected
            
            if evse.cable_connected:
                pass
            else:
                if evse.soc_wh > 2:
                    evse.soc_wh -= 5000/3600
                    evse.km_driven += 25/3600


    async def post_status_notification(self, evse : EvseModel):
        status_notification = StatusNotification(timestamp=datetime.now().isoformat(),
                                                 connector_status=ConnectorStatusEnumType.occupied if evse.cable_connected else ConnectorStatusEnumType.available,
                                                 evse_id=evse.id,
                                                 connector_id=evse.connector_id)
        result = await self.call(status_notification)
        logger.warning(f"{status_notification=} {result=}")

    @on(Action.request_stop_transaction)
    @log_async_call(logger.warning)
    async def request_stop_transaction(self, **data):
        
        tx_found = False
        
        request_tx_id : TransactionId = data["transaction_id"]
        
        context : TxFSMContext
        for i_evse_id, context in self.task_contexts.items():
            if context.evse.tx_id == request_tx_id:
                tx_found = True
                evse_id = i_evse_id
                logger.warning(f"Fonud {request_tx_id=} in {i_evse_id=}")
                break
        
        if not tx_found:
            return call_result.RequestStopTransaction(status=RequestStartStopStatusEnumType.rejected)
            
        ctxt = self.task_contexts[evse_id]
        fsm = self.tx_fsms[evse_id]

        if ctxt.auth_status is None:
            return call_result.RequestStopTransaction(status=RequestStartStopStatusEnumType.rejected)
        
        ctxt.auth_status = None
        
        await fsm.handle(TxFSMEvent.on_deauthorized)

        return call_result.RequestStopTransaction(status=RequestStartStopStatusEnumType.accepted)

    @on(Action.request_start_transaction)
    @log_async_call(logger.warning)
    async def request_start_transaction(self, remote_start_id, id_token, **data):
        # self.auth_status = id_token
        # self.tx_task = asyncio.create_task(self.transaction_task(remote_start_id))
        if "evse_id" in data:
            evse_id = int(data["evse_id"])
        else:
            return call_result.RequestStartTransaction(status=RequestStartStopStatusEnumType.rejected,
                                                       transaction_id=None,
                                                       )
            
        ctxt = self.task_contexts[evse_id]
        ctxt.remote_start_id = remote_start_id
        fsm = self.tx_fsms[evse_id]
        if ctxt.auth_status is not None:
            return call_result.RequestStartTransaction(status=RequestStartStopStatusEnumType.rejected,
                                                       transaction_id=None,
                                                       )
        ctxt.auth_status = id_token
        await fsm.handle_as_deferred(TxFSMEvent.on_authorized)
        return call_result.RequestStartTransaction(status=RequestStartStopStatusEnumType.accepted,
                                                   transaction_id=None
                                                   )

    @on(Action.get_variables)
    @log_async_call(logger.warning)
    async def get_variables(self, get_variable_data):
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
    @log_async_call(logger.warning)
    async def set_variables(self, set_variable_data):
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

async def main():
    global cp

    serial_number = "CP_ACME_BAT_0000"

    uri = "ws://localhost:9000"
    if len(sys.argv) > 1:
        uri = sys.argv[1]
    if len(sys.argv) > 2:
        serial_number = "CP_ACME_BAT_" + sys.argv[2]
        
    #"wss://emotion-test.eu/ocpp/1"
    #uri = "wss://drive2x.lut.fi:443/ocpp/CP_ESS_01"

    ctx = ssl.create_default_context(cafile=certifi.where())  # <- CA bundle
    ws_args: dict[str, Any] = dict(subprotocols=["ocpp2.0.1"],
               open_timeout=5)
    if uri.startswith("wss://"):
        ws_args["ssl"] = ctx
    async with websockets.connect(uri, **ws_args) as ws:
        redis_data = RedisDict(redis=Redis(host="localhost", port=6379, db=1), namespace=f"ocpp-client-{serial_number}-")
        cp = OCPPClient(redis_data, serial_number, ws)

        for client in app.clients('/'):
            with client:
                for cont in  ElementFilter(kind=ui.column, marker="power_plug_container"):
                    with cont:
                        for cid in cp.task_contexts:
                            await evse_row(cid, cp)

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
        for k, t in cp.st_tasks.items():
            await t

@ui.page("/")
async def index():
    background_tasks.create_lazy(main(),name="main")
    ui.label("Power plug status")
    with ui.column().mark("power_plug_container"):
        if cp is not None:
            for cid in cp.task_contexts:
                await evse_row(cid, cp)
    ui.label("SoC")
    ui.button("Reset SoC", on_click=lambda: None)


async def evse_row(cid : EVSEId, cp : OCPPClient):
    with ui.row(align_items="center"):
        tgl = ui.toggle({True: "CONNECTED", False: "DISCONNECTED"}).mark(f"plug_tgl_{cid}")
        tgl.bind_value(cp.task_contexts[cid].evse, "cable_connected")
        ui.label("test").bind_text_from(cp.tx_fsms[cid], "current_state", backward=str)
        ui.label("test").bind_text_from(cp.task_contexts[cid].evse, "soc_wh", 
                                        backward=lambda x,c=cp.task_contexts[cid].evse: f"Charge: {(x/c.usable_capacity*100):0.2f}%")
        ui.label("test").bind_text_from(cp.task_contexts[cid].evse, "km_driven", backward=lambda x: f"Driven {x:0.1f} km")


# Dummy call to generate enum modules on every run
TxFSM(TxFSMContext(EvseModel(id=0)))

ui.run(host="0.0.0.0", port=7500)
