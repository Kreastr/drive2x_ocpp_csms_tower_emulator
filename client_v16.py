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
from abc import ABC, abstractmethod
from logging import getLogger

from ocpp.v201.datatypes import ChargingStationType
from ocpp.v201.enums import BootReasonEnumType
from ocpp.v21.enums import Action

from ocpp_models.v16.boot_notification import BootNotificationRequest
from ocpp_models.v201.get_variables import GetVariablesRequest
from util import log_req_response, with_request_model, async_camelize_kwargs

logger = getLogger(__name__)

from ocpp.routing import on
from ocpp.v201 import ChargePoint, call, call_result


class OCPPServerV16Interface(ABC):

    @abstractmethod
    async def on_server_get_variables(self, request : GetVariablesRequest) -> call_result.GetVariables:
        pass


class OCPPClientV201(ChargePoint):

    def __init__(self, client_interface : OCPPServerV16Interface, serial_number, ws, response_timeout=30, _logger=logger):
        super().__init__(serial_number, ws, response_timeout=response_timeout, logger=_logger)
        self.client_interface = client_interface


    async def boot_notification_request(self, rq : BootNotificationRequest):
        return await self.call_payload(call.BootNotification(
                charging_station=ChargingStationType(vendor_name=rq.chargePointVendor,
                                                     model=rq.chargePointModel,
                                                     serial_number=rq.chargePointSerialNumber,
                                                     firmware_version=rq.firmwareVersion),
                reason=BootReasonEnumType.unknown
                ))

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
        return await self.call(payload, suppress, unique_id, skip_schema_validation)


