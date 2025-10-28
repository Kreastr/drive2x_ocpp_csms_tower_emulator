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
import datetime
from abc import ABC, abstractmethod
from logging import getLogger

import websockets
from ocpp.v16.enums import ChargePointStatus
from ocpp.v201.datatypes import ChargingStationType, TransactionType
from ocpp.v201.enums import BootReasonEnumType, ConnectorStatusEnumType, TransactionEventEnumType, TriggerReasonEnumType
from ocpp.v21.enums import Action

from ocpp_models.v16.boot_notification import BootNotificationRequest
from ocpp_models.v16.start_transaction import StartTransactionRequest
from ocpp_models.v16.status_notification import StatusNotificationRequest
from ocpp_models.v201.get_variables import GetVariablesRequest
from ocpp_models.v201.request_start_transaction import RequestStartTransactionRequest
from ocpp_models.v201.reset import ResetRequest
from proxy.proxy_connection_fsm import ProxyConnectionFSM
from proxy_connection_fsm_enums import ProxyConnectionFSMEvent
from util import log_req_response, with_request_model, async_camelize_kwargs

logger = getLogger(__name__)

from ocpp.routing import on
from ocpp.v201 import ChargePoint, call, call_result


class OCPPServerV16Interface(ABC):

    @abstractmethod
    async def on_server_get_variables(self, request : GetVariablesRequest) -> call_result.GetVariables:
        pass

    @abstractmethod
    async def on_request_start_transaction(self, request : RequestStartTransactionRequest) -> call_result.RequestStartTransaction:
        pass

    @abstractmethod
    def get_state_machine(self) -> ProxyConnectionFSM:
        pass

    @abstractmethod
    async def on_reset(self, request) -> call_result.Reset:
        pass


STATUS_MAP = {ChargePointStatus.preparing: ConnectorStatusEnumType.occupied,
              ChargePointStatus.available: ConnectorStatusEnumType.available,
              ChargePointStatus.unavailable: ConnectorStatusEnumType.unavailable,
              ChargePointStatus.charging: ConnectorStatusEnumType.occupied}

class OCPPClientV201(ChargePoint):

    def __init__(self, client_interface : OCPPServerV16Interface, serial_number, ws, response_timeout=30, _logger=logger):
        super().__init__(serial_number, ws, response_timeout=response_timeout, logger=_logger)
        self.client_interface = client_interface

    async def status_notification_request(self, rq : StatusNotificationRequest) -> call_result.StatusNotification:

        if rq.status in STATUS_MAP:
            fwd_status = STATUS_MAP[rq.status]
        else:
            logger.error(f"Failed to map status notification status {rq.status}")
            fwd_status = ConnectorStatusEnumType.unavailable
        req_time = rq.timestamp
        if req_time is None:
            req_time = datetime.datetime.now(datetime.timezone.utc)
        return await self.call_payload(call.StatusNotification(timestamp=req_time.isoformat(),
                                                               connector_status=fwd_status,
                                                               evse_id=rq.connectorId,
                                                               connector_id=1))


    async def boot_notification_request(self, rq : BootNotificationRequest) -> call_result.BootNotification:
        return await self.call_payload(call.BootNotification(
                charging_station=ChargingStationType(vendor_name=rq.chargePointVendor,
                                                     model=rq.chargePointModel,
                                                     serial_number=rq.chargePointSerialNumber,
                                                     firmware_version=rq.firmwareVersion),
                reason=BootReasonEnumType.unknown
                ))

    async def start_transaction_request(self, rq : StartTransactionRequest, tx_id : str) -> call_result.TransactionEvent:
        return await self.call_payload(call.TransactionEvent(event_type=TransactionEventEnumType.started,
                                                             timestamp=rq.timestamp.isoformat(),
                                                             trigger_reason=TriggerReasonEnumType.remote_start,
                                                             seq_no=1,
                                                             transaction_info=TransactionType(tx_id)))

    async def heartbeat_request(self) -> call_result.Heartbeat:
        return await self.call_payload(call.Heartbeat())

    @on(Action.request_start_transaction)
    @log_req_response
    @async_camelize_kwargs
    @with_request_model(RequestStartTransactionRequest)
    async def on_request_start_transaction(self, request : RequestStartTransactionRequest, *vargs, **kwargs):
        return await self.client_interface.on_request_start_transaction(request)


    @on(Action.reset)
    @log_req_response
    @async_camelize_kwargs
    @with_request_model(ResetRequest)
    async def on_reset(self, request : ResetRequest, *vargs, **kwargs) -> call_result.Reset:
        return await self.client_interface.on_reset(request)
        #  ToDo: return await self.client_interface.on_server_get_variables(request)

    @on(Action.get_variables)
    @log_req_response
    @async_camelize_kwargs
    @with_request_model(GetVariablesRequest)
    async def on_get_variables(self, request : GetVariablesRequest, *vargs, **kwargs):
        return await self.client_interface.on_server_get_variables(request)

    @log_req_response
    async def call_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):

        try:
            return await self.call(payload, suppress, unique_id, skip_schema_validation)
        except websockets.exceptions.ConnectionClosedOK:
            await self.client_interface.get_state_machine().handle(ProxyConnectionFSMEvent.on_server_disconnect)

    async def close_connection(self):
        await self._connection.close()
        await self.client_interface.get_state_machine().handle(ProxyConnectionFSMEvent.on_server_disconnect)
