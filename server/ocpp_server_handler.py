"""
SPDX-License-Identifier: AGPL-3.0-or-later
Copyright (C) 2025 Lappeenrannan-Lahden teknillinen yliopisto LUT
Author: Aleksei Romanenko <aleksei.romanenko@lut.fi>


This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Funded by the European Union and UKRI. Views and opinions expressed are however those of the author(s)
only and do not necessarily reflect those of the European Union, CINEA or UKRI. Neither the European
Union nor the granting authority can be held responsible for them.
"""


import asyncio
import json
import logging
from datetime import datetime, timedelta
from logging import getLogger

import dateutil.parser
from beartype import beartype
from cachetools import cached
from ocpp.routing import on
from ocpp.v201 import ChargePoint, call_result, call
from ocpp.v201.datatypes import GetVariableDataType, ComponentType, VariableType, GetVariableResultType, \
    IdTokenInfoType, MeterValueType
from ocpp.v201.enums import GetVariableStatusEnumType, Action, RegistrationStatusEnumType, AuthorizationStatusEnumType, \
    ReportBaseEnumType, ResetEnumType, ResetStatusEnumType
from redis_dict import RedisDict
from snoop.pp_module import traceback
from websockets import ConnectionClosedOK

from charge_point_fsm_enums import ChargePointFSMState, ChargePointFSMEvent
from server.transaction_manager.tx_fsm import TxFSMServer

from util.db import get_default_redis
from server.charge_point_model import get_charge_point_fsm
from server.data import ChargePointContext, EvseStatus
from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from tx_manager_fsm_enums import TxManagerFSMEvent, TxManagerFSMState
from util import get_time_str, any_of, time_based_id, broadcast_to, log_async_call, get_app_args

from server.ui.nicegui import gui_info
from util.types import *
from server.ui.ui_manager import UIManagerFSMType

from typing import Any

from server.callable_interface import CallableInterface

from server.ui import CPCard
import traceback

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

@cached(cache={})
def get_redis_caches_cp():
    redis = get_default_redis()
    session_pins = RedisDict("ocpp_server-session-pins-", expire=30, redis=redis)
    boot_notification_cache = RedisDict("ocpp_server-boot-notifications-cache", redis=redis)
    status_notification_cache = RedisDict("ocpp_server-status-notifications-cache", redis=redis)

    return session_pins, boot_notification_cache, status_notification_cache

def clamp_setpoint(evse: EvseStatus):
    if evse.setpoint > 8000:
        evse.setpoint = 8000
    if evse.setpoint < -8000:
        evse.setpoint = -8000

    upkeep_power = get_app_args().upkeep_power
    # Minimal charge/discharge for connection stability
    if evse.setpoint < 0:
        if evse.setpoint > -upkeep_power:
            evse.setpoint = -upkeep_power
    else:
        if evse.setpoint < upkeep_power:
            evse.setpoint = upkeep_power

@beartype
class OCPPServerHandler(CallableInterface, ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.events = []
        self.onl_task = asyncio.create_task(self.online_status_task())
        self.fsm = get_charge_point_fsm(ChargePointContext())
        self.fsm.context : ChargePointContext

        self.fsm.on(ChargePointFSMState.created.on_exit, self.connect_and_request_id)
        self.fsm.on(ChargePointFSMState.identified.on_enter, self.try_cached_boot_notification)
        self.fsm.on(ChargePointFSMState.identified.on_enter, self.start_boot_timeout)
        self.fsm.on(ChargePointFSMState.failing.on_enter, self.try_reboot_peer)
        self.fsm.on(ChargePointFSMState.failed.on_enter, self.close_connection)
        self.fsm.on(ChargePointFSMState.closing.on_enter, self.close_connection)
        self.fsm.on(ChargePointFSMState.booted.on_enter, self.add_to_ui)
        self.fsm.on(ChargePointFSMState.booted.on_enter, self.set_online)
        self.fsm.on(ChargePointFSMState.force_booted.on_enter, self.add_to_ui)
        self.fsm.on(ChargePointFSMState.force_booted.on_enter, self.set_online)
        self.fsm.on(ChargePointFSMState.force_booted.on_enter, self.try_cached_status_notifications)

    @log_async_call(logger.warning)
    async def call_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):
        return await self.call(payload, suppress, unique_id, skip_schema_validation)

    async def set_online(self, *vargs):
        self.fsm.context.timeout = datetime.now() + timedelta(seconds=30)
        self.fsm.context.online = True

    async def start_boot_timeout(self, *vargs):
        await asyncio.sleep(15)
        await self.fsm.handle(ChargePointFSMEvent.on_boot_timeout)

    async def try_cached_boot_notification(self, *vargs):
        session_pins, boot_notification_cache, status_notification_cache = get_redis_caches_cp()
        if self.fsm.context.id in boot_notification_cache:
            self.fsm.context.boot_notifications.append( boot_notification_cache[self.fsm.context.id] )
            await self.fsm.handle(ChargePointFSMEvent.on_cached_boot_notification)
            await self.try_cached_status_notifications()
        elif self.id in boot_notification_cache:
            self.fsm.context.boot_notifications.append( boot_notification_cache[self.id] )
            await self.fsm.handle(ChargePointFSMEvent.on_cached_boot_notification)
            await self.try_cached_status_notifications()
        else:
            if self.has_icl_v16_hacks():
                await self.fsm.handle(ChargePointFSMEvent.on_missing_boot_notification)
                await self.try_cached_status_notifications()

    async def try_cached_status_notifications(self, *vargs):
        session_pins, boot_notification_cache, status_notification_cache = get_redis_caches_cp()
        if self.fsm.context.id in status_notification_cache:
            for _, notification in status_notification_cache[self.fsm.context.id].items():
                await self.handle_status_notification_inner(EvseStatus.model_validate(json.loads(notification)))

    async def add_to_ui(self, *vargs):
        assert  self.fsm.context.id != "provisional"
        charge_points[self.fsm.context.id] = self
        await self.ui_effects_on_connected()

    async def connect_and_request_id(self, *vargs):
        start_task = asyncio.create_task(self.start())
        await self.request_serial_bg()
        await start_task

    async def request_serial_bg(self, **kwargs):
        await asyncio.sleep(3)  # toDo fix with wait for connection
        try:
            result: call_result.GetVariables | None = await self.call_payload(
                call.GetVariables([GetVariableDataType(component=ComponentType(name="ChargingStation"),
                                                       variable=VariableType(name="SerialNumber"))]))
        except TimeoutError:
            logger.error(f"Client timed out")
            result = None
        except ConnectionClosedOK:
            logger.error(f"Client ConnectionClosedOK")
            result = None
            raise

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
        self.id = result.get_variable_result[0].attribute_value
        charge_points[self.fsm.context.id] = self
        if self.fsm.context.id is None:
            await self.fsm.handle(ChargePointFSMEvent.on_serial_number_not_obtained)
            return
        await self.fsm.handle(ChargePointFSMEvent.on_serial_number_obtained)

    async def ui_effects_on_connected(self):
        from server.ui import CPCard
        await broadcast_to(app=gui_info.app,
                           kind=CPCard,
                           marker=self.fsm.context.id,
                           op=lambda x: x.delete(),
                           page="/")

        def add_card(grid):
            with grid:
                CPCard(self.fsm).mark(self.fsm.context.id)

        await broadcast_to(app=gui_info.app,
                           kind=gui_info.ui.row,
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
        session_pins, boot_notification_cache, status_notification_cache = get_redis_caches_cp()
        self.log_event(("boot_notification", (charging_station, reason, vargs, kwargs)))
        self.fsm.context.boot_notifications.append( (charging_station, reason, vargs, kwargs) )

        if "serial_number" in charging_station:
            self.id = charging_station["serial_number"]
            self.fsm.context.id = charging_station["serial_number"]
        else:
            self.fsm.context.id = self.id
        boot_notification_cache[self.id] = (charging_station, reason, vargs, kwargs)
        boot_notification_cache[self.fsm.context.id] = (charging_station, reason, vargs, kwargs)

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
            #if self.fsm.context.id in boot_notification_cache:
            #    del boot_notification_cache[self.fsm.context.id]
            await self.fsm.handle(ChargePointFSMEvent.on_boot_notification)
            return call_result.BootNotification(
                current_time=get_time_str(),
                interval=60,
                status=RegistrationStatusEnumType.rejected
            )

        await self.fsm.handle(ChargePointFSMEvent.on_boot_notification)
        return call_result.BootNotification(
            current_time=get_time_str(),
            interval=10,
            status=RegistrationStatusEnumType.accepted
        )

    @on(Action.status_notification)
    async def on_status_notification(self, **status_data):
        session_pins, boot_notification_cache, status_notification_cache = get_redis_caches_cp()
        from server.ui import CPCard
        self.log_event(("status_notification", (status_data)))
        logger.warning(f"id={self.fsm.context.id} on_status_notification {status_data=}")
        conn_status = EvseStatus(**status_data)

        if self.fsm.context.id not in status_notification_cache:
            status_data = dict()
        else:
            status_data = status_notification_cache[self.fsm.context.id]

        if self.id in status_notification_cache:
            status_data.update(status_notification_cache[self.id])

        status_data.update({conn_status.evse_id: conn_status.model_dump_json()})
        status_notification_cache[self.fsm.context.id] = status_data
        status_notification_cache[self.id] = status_data
        
        await self.handle_status_notification_inner(conn_status)
        return call_result.StatusNotification()

    async def handle_status_notification_inner(self, conn_status):
        if self.fsm.current_state in [ChargePointFSMState.identified,
                                      ChargePointFSMState.booted,
                                      ChargePointFSMState.force_booted,
                                      ChargePointFSMState.running_transaction,
                                      ChargePointFSMState.closing]:

            tx_fsm: TxFSMServer = self.fsm.context.transaction_fsms[conn_status.evse_id]

            if tx_fsm.context.cp_interface is None:
                tx_fsm.context.cp_interface = self

            tx_fsm.context.evse.connector_status = conn_status.connector_status
            tx_fsm.context.evse.evse_id = conn_status.evse_id
            tx_fsm.context.evse.connector_id = conn_status.connector_id

            await tx_fsm.try_restore_fsm(self.get_charge_point_id()+"-"+str(tx_fsm.context.evse.evse_id))

            logger.warning(" tx_fsm.loop")
            await tx_fsm.loop()

            # if conn_status.connector_status == "Occupied":
            #    await tx_fsm.handle(TxManagerFSMEvent.on_start_tx_event)

            if conn_status.evse_id not in self.fsm.context.transaction_fsms:
                self.fsm.context.transaction_fsms[conn_status.evse_id].context.evse = conn_status
                self.fsm.context.transaction_fsms[conn_status.evse_id].context.cp_interface = self
                await broadcast_to(app=gui_info.app,
                                   op=lambda x: x.on_new_evse(conn_status.evse_id),
                                   page="/",
                                   kind=CPCard, marker=self.fsm.context.id)
            else:
                self.fsm.context.transaction_fsms[
                    conn_status.evse_id].context.evse.connector_status = conn_status.connector_status

    @on(Action.heartbeat)
    async def on_heartbeat(self, **data):
        self.log_event(("heartbeat", (data)))
        logger.warning(f"id={self.fsm.context.id} on_heartbeat {data=}")
        await self.set_online()
        return call_result.Heartbeat(
            current_time=get_time_str()
        )

    @on(Action.meter_values)
    async def on_meter_values(self, evse_id : int, meter_value : list[dict], **data):
        self.log_event(("meter_values", (evse_id, meter_value, data)))
        logger.error(f"id={self.fsm.context.id} on_meter_values {evse_id=} {meter_value=}")
        try:
            for v in meter_value:
                # ToDo handle real timestamp
                #ts = dateutil.parser.parse(v["timestamp"])
                for sv in  v["sampled_value"]:
                    evse : EvseStatus = self.fsm.context.transaction_fsms[evse_id].context.evse
                    if "measurand" in sv:
                        if sv["measurand"] == "SoC":
                            evse.last_report_soc_percent = sv["value"]
                            evse.last_report_time = datetime.now()
                        if sv["measurand"] == "Power.Active.Import":
                            evse.last_reported_power = sv["value"]/1000.0
                    logger.error(f"post meter values {evse=} {sv=}")
                        
        except:
            logger.error(f"{traceback.format_exc()=}")
        finally:
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
            await tx_fsm.handle(TxManagerFSMEvent.on_tx_update_event)

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
                self.fsm.context.components[cmp].variables[var] = record
            self.fsm.context.report_datetime = report_data["generated_at"]
        finally:   
            return call_result.NotifyReport()

    def log_event(self, event_data):
        self.events.append(event_data)

    async def request_full_report(self, *vargs):
        result = await self.call_payload(
            call.GetBaseReport(request_id=time_based_id(),
                               report_base=ReportBaseEnumType.full_inventory))
        logging.warning(f"request_full_report {result=}")

    async def try_reboot_peer(self, *vargs):
        session_pins, boot_notification_cache, status_notification_cache = get_redis_caches_cp()
        if self.fsm.context.id in boot_notification_cache:
            del boot_notification_cache[self.fsm.context.id]
        if self.fsm.context.id in status_notification_cache:
            del status_notification_cache[self.fsm.context.id]
        response : call_result.Reset | None = await self.call_payload(call.Reset(type=ResetEnumType.immediate))
        if response is None:
            await self.fsm.handle(ChargePointFSMEvent.on_reset_rejected)
            return

        if response.status == ResetStatusEnumType.accepted:
            await self.fsm.handle(ChargePointFSMEvent.on_reset_accepted)
        else:
            await self.fsm.handle(ChargePointFSMEvent.on_reset_rejected)

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
        await self.fsm.context.transaction_fsms[evse_id].handle(TxManagerFSMEvent.on_authorized_by_app)

    def get_evse(self, evse_id : EVSEId):
        return self.fsm.context.transaction_fsms[evse_id].context.evse

    async def do_increase_setpoint(self, evse_id : EVSEId):
        logger.warning(f"Increased setpoint")
        if -get_app_args().upkeep_power <= self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint <= 0:
            self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint = get_app_args().upkeep_power
        else:
            self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint += 200
        clamp_setpoint(self.fsm.context.transaction_fsms[evse_id].context.evse)
        logger.warning(f"Increased setpoint to {self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint}")

    async def do_decrease_setpoint(self, evse_id : EVSEId):
        logger.warning(f"Decreased setpoint")
        if 0 <= self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint <= get_app_args().upkeep_power:
            self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint = -get_app_args().upkeep_power
        else:
            self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint -= 200
        clamp_setpoint(self.fsm.context.transaction_fsms[evse_id].context.evse)
        logger.warning(f"Decreased setpoint to {self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint}")

    async def force_setpoint_update(self, evse_id : EVSEId):
        new_setpoint = self.fsm.context.transaction_fsms[evse_id].context.evse.setpoint
        logger.warning(f"Forced setpoint update {evse_id=} {new_setpoint=}")
        await self.fsm.context.transaction_fsms[evse_id].handle(TxManagerFSMEvent.on_setpoint_apply_mark)

    def has_icl_v16_hacks(self):
        return self.id.startswith("Latiniki")

    def get_charge_point_id(self) -> str:
        return self.id

charge_points : dict[ChargePointId, OCPPServerHandler] = dict()
ui_pages : dict[ChargePointId, UIManagerFSMType] = dict()
charge_point_cards : dict[ChargePointId, Any] = dict()
