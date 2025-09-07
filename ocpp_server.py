import asyncio
import logging
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from math import ceil
from typing import cast, Self
from uuid import uuid4

import websockets
from beartype import beartype
from nicegui.binding import BindableProperty, bind_from
from nicegui.element import Element
from ocpp.routing import on
from ocpp.v201 import ChargePoint, call
from ocpp.v201 import call_result
from ocpp.v201.datatypes import GetVariableDataType, ComponentType, GetVariableResultType, IdTokenInfoType, VariableType, \
    SetVariableDataType, EVSEType
from ocpp.v201.enums import Action, RegistrationStatusEnumType, AuthorizationStatusEnumType, ReportBaseEnumType, \
    ResetEnumType, GetVariableStatusEnumType

from nicegui import ui, app, background_tasks, ElementFilter
from typing import Any

from redis import Redis
from snoop import snoop
from websockets import Subprotocol

from charge_point_fsm_enums import ChargePointFSMState, ChargePointFSMEvent
from server.charge_point_model import get_charge_point_fsm, ChargePointFSMType
from server.data import ChargePointContext
from server.data.evse_status import EvseStatus
from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from tx_manager_fsm_enums import TxManagerFSMEvent, TxManagerFSMState
from util import get_time_str, setup_logging, time_based_id, any_of
from util.types import *

from server.ui_manager import UIManagerFSMType, UIManagerContext

from redis import Redis

async def broadcast_to(op, page, **filters):
    for client in app.clients(page):
        with client:
            for old in ElementFilter(**filters):
                op(old)



logger = setup_logging(__name__)
logger.setLevel(logging.DEBUG)

boot_notification_cache = dict()

redis_host = "localhost"
redis_port = 6379
redis_db = 2
redis = Redis(host=redis_host, port=redis_port, db=redis_db)
ui_manager_fsms = defaultdict(default_factory=lambda : UIManagerFSMType(UIManagerContext()))

@beartype
class OCPPServerHandler(ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.events = []
        self.onl_task = asyncio.create_task(self.online_status_task())
        self.fsm = get_charge_point_fsm(ChargePointContext())
        

        self.fsm.on(ChargePointFSMState.created.on_exit, self.connect_and_request_id)
        self.fsm.on(ChargePointFSMState.identified.on_enter, self.try_cached_boot_notification)
        self.fsm.on(ChargePointFSMState.identified.on_enter, self.start_boot_timeout)
        self.fsm.on(ChargePointFSMState.failed.on_enter, self.close_connection)
        self.fsm.on(ChargePointFSMState.closing.on_enter, self.close_connection)
        self.fsm.on(ChargePointFSMState.booted.on_enter, self.add_to_ui)
        self.fsm.on(ChargePointFSMState.booted.on_enter, self.set_online)

    async def set_online(self, *vargs):
        self.fsm.context.timeout = datetime.now() + timedelta(seconds=30)
        self.fsm.context.online = True

    async def start_boot_timeout(self, *vargs):
        await asyncio.sleep(15)
        await self.fsm.handle(ChargePointFSMEvent.on_boot_timeout)

    async def try_cached_boot_notification(self, *vargs):
        if self.fsm.context.id in boot_notification_cache:
            self.fsm.context.boot_notifications.append( boot_notification_cache[self.fsm.context.id] )
            await self.fsm.handle(ChargePointFSMEvent.on_cached_boot_notification)

    async def add_to_ui(self, *vargs):
        assert  self.fsm.context.id != "provisional"
        charge_points[self.fsm.context.id] = self
        await self.ui_effects_on_connected()

    async def connect_and_request_id(self, *vargs):

        self.fsm.context.connection_task = asyncio.create_task(self.start())

        result: call_result.GetVariables | None = await self.call(
            call.GetVariables([GetVariableDataType(component=ComponentType(name="ChargingStation"),
                                                   variable=VariableType(name="SerialNumber"))]))
        if result is None:
            await self.fsm.handle(ChargePointFSMEvent.on_serial_number_not_obtained)
            return

        result.get_variable_result = list(map(lambda x: GetVariableResultType(**x), result.get_variable_result))
        self.log_event(f"Charger S/N variable {result=}")

        if result.get_variable_result[0].attribute_status != GetVariableStatusEnumType.accepted:
            self.log_event("Failed to read CP serial number. Refusing to operate.")
            #await self.close_connection()
            await self.fsm.handle(ChargePointFSMEvent.on_serial_number_not_obtained)
            return

        self.fsm.context.id = result.get_variable_result[0].attribute_value
        if self.fsm.context.id is None:
            await self.fsm.handle(ChargePointFSMEvent.on_serial_number_not_obtained)
            return
        await self.fsm.handle(ChargePointFSMEvent.on_serial_number_obtained)


    async def ui_effects_on_connected(self):
        await broadcast_to(kind=CPCard,
                           marker=self.fsm.context.id,
                           op=lambda x: x.delete(),
                           page="/")

        def add_card(grid):
            with grid:
                CPCard(self.fsm).mark(self.fsm.context.id)

        await broadcast_to(kind=ui.row,
                           marker="cp_card_container",
                           op=add_card,
                           page="/")

    async def online_status_task(self):
        while not self.fsm.context.shutdown:
            await asyncio.sleep(1)
            try:
                if self.fsm.context.timeout < datetime.now():
                    self.fsm.context.online = False
            except:
                self.fsm.context.online = False
            for k,v in self.fsm.context.transaction_fsms.items():
                await v.loop()
            await self.fsm.loop()


    @on(Action.boot_notification)
    async def on_boot_notification(self,  charging_station, reason, *vargs, **kwargs):
        self.log_event(("boot_notification", (charging_station, reason, vargs, kwargs)))
        self.fsm.context.boot_notifications.append( (charging_station, reason, vargs, kwargs) )

        self.fsm.context.id = charging_station["serial_number"]

        logger.warning(f"id={self.fsm.context.id} boot_notification {charging_station=} {reason=} {vargs=} {kwargs=}")

        if self.fsm.current_state == ChargePointFSMState.unknown and "serial_number" not in charging_station:
            await self.fsm.handle(ChargePointFSMEvent.on_serial_number_not_obtained)
            return call_result.BootNotification(
                current_time=get_time_str(),
                interval=60,
                status=RegistrationStatusEnumType.rejected
            )

        if self.fsm.current_state not in [ChargePointFSMState.unknown,
                                          ChargePointFSMState.identified]:
            #await self.fsm.handle(ChargePointFSMEvent.on_serial_number_not_obtained)
            return call_result.BootNotification(
                current_time=get_time_str(),
                interval=60,
                status=RegistrationStatusEnumType.rejected
            )

        self.fsm.context.id = charging_station["serial_number"]
        boot_notification_cache[self.fsm.context.id] = (charging_station, reason, vargs, kwargs)
        await self.fsm.handle(ChargePointFSMEvent.on_boot_notification)
        return call_result.BootNotification(
            current_time=get_time_str(),
            interval=10,
            status=RegistrationStatusEnumType.accepted
        )

    @on(Action.status_notification)
    async def on_status_notification(self, **data):
        self.log_event(("status_notification", (data)))
        logger.warning(f"id={self.fsm.context.id} on_status_notification {data=}")
        conn_status = EvseStatus(**data)

        if self.fsm.current_state in [ChargePointFSMState.identified,
                                      ChargePointFSMState.booted,
                                      ChargePointFSMState.running_transaction,
                                      ChargePointFSMState.closing]:
        

            tx_fsm : TxManagerFSMType = self.fsm.context.transaction_fsms[conn_status.evse_id]

            if tx_fsm.context.cp_interface is None:
                tx_fsm.context.cp_interface = self

            tx_fsm.context.evse.connector_status = conn_status.connector_status
            tx_fsm.context.evse.evse_id = conn_status.evse_id
            tx_fsm.context.evse.connector_id = conn_status.connector_id

            logger.warning(" tx_fsm.loop")
            await tx_fsm.loop()

            #if conn_status.connector_status == "Occupied":
            #    await tx_fsm.handle(TxManagerFSMEvent.on_start_tx_event)

            if conn_status.evse_id not in self.fsm.context.transaction_fsms:
                self.fsm.context.transaction_fsms[conn_status.evse_id].context.evse = conn_status
                self.fsm.context.transaction_fsms[conn_status.evse_id].context.cp_interface = self
                await broadcast_to(lambda x: x.on_new_evse(conn_status.evse_id), "/", kind=CPCard, marker=self.fsm.context.id)
            else:
                self.fsm.context.transaction_fsms[conn_status.evse_id].context.evse.connector_status = conn_status.connector_status
        return call_result.StatusNotification(
        )

    @on(Action.heartbeat)
    async def on_heartbeat(self, **data):
        self.log_event(("heartbeat", (data)))
        logger.warning(f"id={self.fsm.context.id} on_heartbeat {data=}")
        await self.set_online()
        return call_result.Heartbeat(
            current_time=get_time_str()
        )

    @on(Action.meter_values)
    async def on_meter_values(self, **data):
        self.log_event(("meter_values", (data)))
        logger.warning(f"id={self.fsm.context.id} on_meter_values {data=}")
        return call_result.MeterValues(
        )

    @on(Action.authorize)
    async def on_authorize(self, **data):
        self.log_event(("authorize", (data)))
        logger.warning(f"id={self.fsm.context.id} on_authorize {data=}")
        return call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.invalid))

    @on(Action.transaction_event)
    async def on_transaction_event(self, **data):
        self.log_event(("transaction_event", (data)))
        logger.warning(f"id={self.fsm.context.id} on_transaction_event {data=}")

        if any_of(lambda: self.fsm.current_state not in [ChargePointFSMState.booted, ChargePointFSMState.running_transaction],
                  lambda: "event_type" not in data,
                  lambda: "transaction_info" not in data,
                  lambda: "transaction_id" not in data["transaction_info"],
                  lambda: "evse" not in data,
                  lambda: "id" not in data["evse"]):
            return call_result.TransactionEvent()

        evse_id = EVSEId(data["evse"]["id"])

        tx_fsm = self.fsm.context.transaction_fsms[evse_id]

        event_type = data["event_type"]

        reported_tx_id = TransactionId(data["transaction_info"]["transaction_id"])

        logger.warning(f"{event_type=} {evse_id} {reported_tx_id=} {tx_fsm.context.tx_id=}")

        tx_fsm.context : TxManagerContext

        if reported_tx_id != tx_fsm.context.tx_id:
            await tx_fsm.handle(TxManagerFSMEvent.on_end_tx_event)
            tx_fsm.context.tx_id = reported_tx_id
            self.fsm.context.transaction_fsms[evse_id].context.tx_id = reported_tx_id
            await tx_fsm.handle(TxManagerFSMEvent.on_start_tx_event)
            
        if event_type == "Started":
            await tx_fsm.handle(TxManagerFSMEvent.on_start_tx_event)

        if event_type == "Updated" and tx_fsm.current_state in [TxManagerFSMState.occupied]:
            await tx_fsm.handle(TxManagerFSMEvent.on_start_tx_event)

        if event_type == "Ended" and tx_fsm.context.tx_id is not None:
            await tx_fsm.handle(TxManagerFSMEvent.on_end_tx_event)
            tx_fsm.context.tx_id = None

        response = dict()
        if "id_token_info" in data:
            response.update(dict(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted)))
        #self.tx_status
        return call_result.TransactionEvent(**response)

        #return call_result.TransactionEvent()

    @on(Action.notify_report)
    async def on_notify_report(self, **data):
        self.log_event(("notify_report", (data)))
        logger.warning(f"id={self.fsm.context.id} on_notify_report {data=}")
        return call_result.NotifyReport()

    def log_event(self, event_data):
        self.events.append(event_data)

    async def close_connection(self):
        self.fsm.context.shutdown = True
        self.fsm.context.online = False
        await self._connection.close()
        await self.onl_task

    
    async def do_clear_fault(self, evse_id : EVSEId):
        await self.fsm.context.transaction_fsms[evse_id].handle(TxManagerFSMEvent.on_clear_fault)
    
    async def do_remote_stop(self, evse_id : EVSEId):
        await self.fsm.context.transaction_fsms[evse_id].handle(TxManagerFSMEvent.on_deauthorized)
    
    async def do_remote_start(self, evse_id : EVSEId):
        await self.fsm.context.transaction_fsms[evse_id].handle(TxManagerFSMEvent.on_authorized)

    def get_evse(self, evse_id : EVSEId):
        return self.fsm.context.transaction_fsms[evse_id].context.evse

    def clamp_setpoint(self, evse: EvseStatus):
        if evse.setpoint > 11000:
            evse.setpoint = 11000
        if evse.setpoint < -11000:
            evse.setpoint = -11000

    async def do_increase_setpoint(self, evse_id : EVSEId):
        logger.warning(f"Increased setpoint")
        self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint += 1000
        self.clamp_setpoint(self.fsm.context.transaction_fsms[evse_id].context.evse)
        logger.warning(f"Increased setpoint to {self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint}")
        await self.fsm.context.transaction_fsms[evse_id].handle(TxManagerFSMEvent.on_setpoint_update)

    async def do_decrease_setpoint(self, evse_id : EVSEId):
        logger.warning(f"Decreased setpoint")
        self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint -= 1000
        self.clamp_setpoint(self.fsm.context.transaction_fsms[evse_id].context.evse)
        logger.warning(f"Decreased setpoint to {self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint}")
        await self.fsm.context.transaction_fsms[evse_id].handle(TxManagerFSMEvent.on_setpoint_update)

cp_card_container : ui.grid | None = None
charge_points : dict[ChargePointId, OCPPServerHandler] = dict()
ui_pages : dict[ChargePointId, UIManagerFSMType] = dict()
charge_point_cards : dict[ChargePointId, Any] = dict()




async def on_connect(websocket):
    logger.warning(f"on client connect {websocket=}")
    cp = OCPPServerHandler("provisional", websocket)

    await get_remote_ip(cp, websocket)

    await cp.fsm.handle(ChargePointFSMEvent.on_start)

    if 0:
        await set_measurement_variables(cp)
    while cp.fsm.context.connection_task is None or not cp.fsm.context.connection_task.done():
        await asyncio.sleep(1)
    await cp.close_connection()
    try:
        result = cp.fsm.context.connection_task.result()
    except Exception as e:
        result = f"Exception {e}"
    cp.log_event(f"start_task.result {result}")


async def get_remote_ip(cp, websocket):
    if "X-Real-IP" in websocket.request.headers:
        real_ip = websocket.request.headers["X-Real-IP"]
    else:
        real_ip = websocket.remote_address[0]
    cp.fsm.context.remote_ip = real_ip


async def set_measurement_variables(cp):
    result: call_result.SetVariables = await cp.call(
        call.SetVariables(set_variable_data=[SetVariableDataType(
            attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
            component=ComponentType(name="AlignedDataCtrlr"),
            variable=VariableType(name="Measurands")),
            SetVariableDataType(
                attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                component=ComponentType(name="AlignedDataCtrlr"),
                variable=VariableType(name="TxEndedMeasurands")),
            SetVariableDataType(
                attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                component=ComponentType(name="SampledDataCtrlr"),
                variable=VariableType(name="TxStartedMeasurands")),
            SetVariableDataType(
                attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                component=ComponentType(name="SampledDataCtrlr"),
                variable=VariableType(name="TxUpdatedMeasurands")),
            SetVariableDataType(
                attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                component=ComponentType(name="SampledDataCtrlr"),
                variable=VariableType(name="TxEndedMeasurands"))
        ]))
    logger.warning(f"Charger measurands set {result=}")


async def main():
    logging.warning("main start")
    server = await websockets.serve(on_connect, '0.0.0.0', 9000, subprotocols=[Subprotocol('ocpp2.0.1')])
    logging.warning("main server ready")
    await server.serve_forever()
    logging.warning("main exit")

@app.get("/cp")
async def cp_list():
    return {"charge_points": list(charge_points)}

@app.get("/cp/{cp_id}/events/")
async def events(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"events": charge_points[cp_id].events}

@app.get("/cp/{cp_id}/reboot")
async def reboot(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].call(call.Reset(type=ResetEnumType.immediate))}

@app.get("/cp/{cp_id}/transactions")
async def transactions(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"events": charge_points[cp_id].fsm.context.transactions}


@app.get("/cp/{cp_id}/remote_start/{evse_id}")
async def remote_start(cp_id : str, evse_id : int):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].do_remote_start(evse_id)}


@app.get("/cp/{cp_id}/remote_stop/{evse_id}")
async def remote_stop(cp_id : str, evse_id : int):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].do_remote_stop(evse_id)}

@app.get("/cp/{cp_id}/report_full")
async def report_full(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].call(
            call.GetBaseReport(request_id=time_based_id(),
                               report_base=ReportBaseEnumType.full_inventory))}


@app.get("/cp/{cp_id}/setpoint/{value}")
async def setpoint(cp_id : str, value : int):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        if value > 4000:
            value = 4000
        if value < -2000:
            value = -2000
        return {"result": await charge_points[cp_id].call(
            call.SetVariables(set_variable_data=[SetVariableDataType(attribute_value=str(value),
                                                                     component=ComponentType(name="V2XChargingCtrlr", instance="1", evse=EVSEType(id=1)),
                                                                     variable=VariableType(name="Setpoint"))]))}



@beartype
class CPCard(Element):
    online = BindableProperty(
        on_change=lambda sender, value: cast(Self, sender)._handle_online_change(value))

    def __init__(self, fsm : ChargePointFSMType, **kwargs):
        super().__init__(tag="div")
        self.fsm = fsm
        self.cp_context : ChargePointContext = fsm.context
        self.card = ui.card()
        self.bind_online_from(self.cp_context, "online")
        self._handle_online_change(self.cp_context.online)
        with self.card:
            with ui.row():
                ui.label("ID")
                ui.label().bind_text(self.cp_context, "id")
            with ui.row():
                ui.label("Remote IP")
                ui.label().bind_text(self.cp_context, "remote_ip")
            with ui.row():
                ui.label("Status")
                ui.label().bind_text(self.fsm, "current_state")
            ui.separator()
            self.connector_container = ui.column()
            ui.separator()

        for connid in self.cp_context.transaction_fsms:
            self.on_new_evse(connid)

    def bind_online_from(self, var, name):
        bind_from(self_obj=self, self_name="online",
                  other_obj=var, other_name=name)

    def _handle_online_change(self, card_online_status):
        logger.warning(f"online changes {card_online_status}")
        self.card.classes(remove="bg-green bg-red")
        self.card.classes(add="bg-green" if card_online_status else "bg-red")
        self.card.update()

    def on_new_evse(self, evse_id : EVSEId):
        logger.warning(f"on new connector {evse_id}")
        with self.connector_container:
            with ui.row(align_items='center'):
                cp = charge_points[self.cp_context.id]
                evse = cp.get_evse(evse_id)
                new_label = ui.label(text=f"{evse_id}: {evse.connector_status}")
                new_label.bind_text_from(evse, "connector_status", backward=lambda x, cid=evse_id: f"{cid}: {x}")
                tx_fsm = self.cp_context.transaction_fsms[evse_id]
                tx_label = ui.label(text=f"{str(tx_fsm.current_state)}")
                tx_label.bind_text_from(tx_fsm, "current_state")
                def exec_async(_evse_id, operation):
                    async def executable():
                        try:
                            logger.warning(f"operation result {await operation(_evse_id)}")
                        except:
                            logger.error(traceback.format_exc())
                    return executable
                ui.button("Start", on_click=exec_async(evse_id, cp.do_remote_start))
                ui.button("Stop", on_click=exec_async(evse_id, cp.do_remote_stop))
                ui.button("Clear", on_click=exec_async(evse_id, cp.do_clear_fault))
                ui.button("+", on_click=exec_async(evse_id, cp.do_increase_setpoint))
                ui.label("0").bind_text_from(self.fsm.context.transaction_fsms[evse_id].context.evse, "setpoint", backward=str)
                ui.button("-", on_click=exec_async(evse_id, cp.do_decrease_setpoint))


@ui.page("/")
async def index():
    background_tasks.create_lazy(main(),name="main")
    ui.label(text="Charge Point status")
    with ui.row().mark("cp_card_container"):
        for cpid in charge_points:
            if cpid != "provisional":
                CPCard(charge_points[cpid].fsm).mark(cpid)


class FairSemaphoreRedis:

    def __init__(self, name : str, n_users : int, redis : Redis, session_timeout : int = 10):
        self.session_timeout = session_timeout
        self.my_id = str(uuid4()).encode("utf-8")
        self.redis = redis
        self.name = name
        self.name_lock = name + ":lock"
        self.name_zset = name + ":queue"
        self.name_ctr = name + ":cntr"
        self.n_users = n_users
        self.acquired = False
        self.rank = None

    def __enter__(self):
        self.acquire()
        assert self.acquired
        return self

    def acquire(self):
        session_timeout = self.session_timeout
        t_now = datetime.now().timestamp()
        pipeline = self.redis.pipeline(True)
        lock_current = self.redis.get(self.name_lock)
        mid =self.my_id
        if lock_current == mid:
            self.redis.expire(self.name_lock, int(ceil(session_timeout)))
            pipeline.zadd(self.name, {self.my_id: t_now})
            self.acquired = True
            self.rank = -1
            return
        # Delete stale requests and get them out of the queue
        pipeline.zremrangebyscore(self.name, '-inf', t_now - session_timeout)
        pipeline.zinterstore(self.name_zset, {self.name_zset: 1, self.name: 0})
        pipeline.incr(self.name_ctr)
        nonce = pipeline.execute()[-1]
        # Add myself to semaphore set and queue
        pipeline.zadd(self.name, {self.my_id: t_now})
        pipeline.zadd(self.name_zset, {self.my_id: nonce}, nx=True)
        pipeline.zrank(self.name_zset, self.my_id)
        rank = pipeline.execute()[-1]
        if rank < self.n_users:
            if self.redis.get(self.name_lock) == self.my_id or self.redis.setnx(self.name_lock, self.my_id):
                self.redis.expire(self.name_lock, int(ceil(session_timeout)))
                self.acquired = True
                self.rank = -1
                return
            elif not self.redis.ttl(self.name_lock):
                self.redis.expire(self.name_lock, int(ceil(session_timeout)))
                self.acquired = False
                self.rank = rank
                return

        self.acquired = False
        self.rank = rank
        return

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.free()

    def free(self):
        self.redis.expire(self.name_lock, 1)
        pipeline = self.redis.pipeline(True)
        pipeline.zrem(self.name, self.my_id)
        pipeline.zrem(self.name_zset, self.my_id)
        assert pipeline.execute()[0]


@ui.page("/d2x_ui/{cp_id}")
async def d2x_ui(cp_id : ChargePointId):
    fsm = ui_manager_fsms[cp_id]
    semaphore = FairSemaphoreRedis(name="page-access-"+cp_id, n_users=1, redis=redis, session_timeout=5)
    semaphore.acquire()

    with ui.card().classes('fixed-center').bind_visibility_from(semaphore, "acquired"):
        if cp_id not in charge_points:
            ui.label(f"Charge Point with this ID is not active. Please try later.")
        else:
            cp = charge_points[cp_id]
            ui.label(cp_id)

    (ui.label(format_queue_position(semaphore.rank)).bind_visibility_from(semaphore, "acquired", backward=lambda x: not x)
                                                    .bind_text_from(semaphore,
                                                                    "rank",
                                                                          backward=format_queue_position))
    ui.timer(1, lambda : semaphore.acquire())


def format_queue_position(rank):
    return (f"This resource is busy. "
            f"You are in queue. "
            f"Your place in queue is {rank}")


ui.run(host="0.0.0.0", port=8000)
