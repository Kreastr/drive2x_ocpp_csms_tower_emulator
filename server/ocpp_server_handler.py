import asyncio
import logging
from _pydatetime import datetime, timedelta
from logging import getLogger

from beartype import beartype
from ocpp.routing import on
from ocpp.v201 import ChargePoint, call_result, call
from ocpp.v201.datatypes import GetVariableDataType, ComponentType, VariableType, GetVariableResultType, IdTokenInfoType
from ocpp.v201.enums import GetVariableStatusEnumType, Action, RegistrationStatusEnumType, AuthorizationStatusEnumType, \
    ReportBaseEnumType, ResetEnumType
from redis_dict import RedisDict

from charge_point_fsm_enums import ChargePointFSMState, ChargePointFSMEvent

from util.db import get_default_redis
from server.charge_point_model import get_charge_point_fsm
from server.data import ChargePointContext, EvseStatus
from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from tx_manager_fsm_enums import TxManagerFSMEvent, TxManagerFSMState
from util import get_time_str, any_of, time_based_id, broadcast_to

from nicegui import ui, app
from util.types import *
from server.ui.ui_manager import UIManagerFSMType

from typing import Any

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

redis = get_default_redis()
session_pins = RedisDict("ocpp_server-session-pins-", expire=30, redis=redis)
boot_notification_cache = RedisDict("ocpp_server-boot-notifications-cache", redis=redis)


@beartype
class OCPPServerHandler(ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.events = []
        self.onl_task = asyncio.create_task(self.online_status_task())
        self.fsm = get_charge_point_fsm(ChargePointContext())
        self.fsm.context : ChargePointContext
        

        self.fsm.on(ChargePointFSMState.created.on_exit, self.connect_and_request_id)
        self.fsm.on(ChargePointFSMState.identified.on_enter, self.try_cached_boot_notification)
        self.fsm.on(ChargePointFSMState.identified.on_enter, self.start_boot_timeout)
        self.fsm.on(ChargePointFSMState.failed.on_enter, self.reboot_peer_and_close_connection)
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
        from server.ui import CPCard
        await broadcast_to(app=app,
                           kind=CPCard,
                           marker=self.fsm.context.id,
                           op=lambda x: x.delete(),
                           page="/")

        def add_card(grid):
            with grid:
                CPCard(self.fsm).mark(self.fsm.context.id)

        await broadcast_to(app=app,
                           kind=ui.row,
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

    @on(Action.notify_event)
    async def on_notify_event(self, **data):
        self.log_event(("notify_event", (data)))
        return call_result.NotifyEvent()

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
        from server.ui import CPCard
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
                await broadcast_to(app=app,
                                   op=lambda x: x.on_new_evse(conn_status.evse_id),
                                   page="/",
                                   kind=CPCard, marker=self.fsm.context.id)
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
    async def on_notify_report(self, **report_data):
        self.log_event(("notify_report", (report_data)))
        logger.warning(f"id={self.fsm.context.id} on_notify_report {report_data=}")
        try:
            for record in report_data["report_data"]:
                cmp = record["component"]["name"]
                var = record["variable"]["name"]
                self.fsm.context.components[cmp][var] = record
            self.fsm.context.report_datetime = report_data["generated_at"]
        finally:   
            return call_result.NotifyReport()

    def log_event(self, event_data):
        self.events.append(event_data)
        
        
    async def request_full_report(self, *vargs):
        result = await self.call(
            call.GetBaseReport(request_id=time_based_id(),
                               report_base=ReportBaseEnumType.full_inventory))
        logging.warning(f"request_full_report {result=}")

    async def reboot_peer_and_close_connection(self, *vargs):
        if self.fsm.context.id in boot_notification_cache:
            del boot_notification_cache[self.fsm.context.id]
        await self.call(call.Reset(type=ResetEnumType.immediate))
        await self.close_connection(*vargs)


    async def close_connection(self, *vargs):
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


charge_points : dict[ChargePointId, OCPPServerHandler] = dict()
ui_pages : dict[ChargePointId, UIManagerFSMType] = dict()
charge_point_cards : dict[ChargePointId, Any] = dict()