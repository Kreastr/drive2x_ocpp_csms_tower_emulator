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
from _pydatetime import datetime, timedelta
from logging import getLogger

from beartype import beartype
from ocpp.routing import on
from ocpp.v201 import ChargePoint, call_result, call
from ocpp.v201.datatypes import GetVariableDataType, ComponentType, VariableType, GetVariableResultType, IdTokenInfoType
from ocpp.v201.enums import GetVariableStatusEnumType, Action, RegistrationStatusEnumType, AuthorizationStatusEnumType, \
    ReportBaseEnumType, ResetEnumType
from util import get_time_str

import sys

import ssl
import certifi
from typing import Any
import websockets
import traceback

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)



async def connect_as_client(serial_number = None):
    #global cp

    if serial_number is None:
        serial_number = "CP_ACME_BAT_0000"

    uri = "ws://localhost:9000"
    if len(sys.argv) > 1:
        uri = sys.argv[1]
        
    #"wss://emotion-test.eu/ocpp/1"
    #uri = "wss://drive2x.lut.fi:443/ocpp/CP_ESS_01"

    ctx = ssl.create_default_context(cafile=certifi.where())  # <- CA bundle
    ws_args: dict[str, Any] = dict(subprotocols=["ocpp2.0.1"],
               open_timeout=5)
    if uri.startswith("wss://"):
        ws_args["ssl"] = ctx
    fallback = 5
    while True:
        try:
            async with websockets.connect(uri, **ws_args) as ws:
                cp = OCPPClient(redis_data, serial_number, ws)
                return cp


        except asyncio.exceptions.CancelledError:
            raise
        except:
            logger.error(traceback.format_exc())
            await asyncio.sleep(fallback)
            fallback *= 1.5

@beartype
class OCPPServer16Proxy(ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)

    @property
    def id(self):
        return ""

    async def call_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):
        return await self.call(payload, suppress, unique_id, skip_schema_validation)


    @on(Action.notify_event)
    async def on_notify_event(self, **data):
        return call_result.NotifyEvent()

    @on(Action.boot_notification)
    async def on_boot_notification(self,  charging_station, reason, *vargs, **kwargs):
        return call_result.BootNotification(
            current_time=get_time_str(),
            interval=10,
            status=RegistrationStatusEnumType.accepted
        )

    @on(Action.status_notification)
    async def on_status_notification(self, **status_data):
        logger.warning(f"{self.id} on_status_notification {status_data=}")
        return call_result.StatusNotification(
        )

    @on(Action.heartbeat)
    async def on_heartbeat(self, **data):
        logger.warning(f"{self.id} on_heartbeat {data=}")
        return call_result.Heartbeat(
            current_time=get_time_str()
        )

    @on(Action.meter_values)
    async def on_meter_values(self, **data):
        logger.warning(f"{self.id} on_meter_values {data=}")
        return call_result.MeterValues(
        )

    @on(Action.authorize)
    async def on_authorize(self, **data):
        logger.warning(f"{self.id} on_authorize {data=}")
        return call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.invalid))

    @on(Action.transaction_event)
    async def on_transaction_event(self, **data):
        logger.warning(f"{self.id} on_transaction_event {data=}")
        response = dict()
        if "id_token_info" in data:
            response.update(dict(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted)))
        return call_result.TransactionEvent(**response)

    @on(Action.notify_report)
    async def on_notify_report(self, **report_data):
        logger.warning(f"{self.id} on_notify_report {report_data=}")
        return call_result.NotifyReport()

    async def reboot_peer_and_close_connection(self, *vargs):
        await self.call_payload(call.Reset(type=ResetEnumType.immediate))
        await self.close_connection(*vargs)


    async def close_connection(self, *vargs):
        await self._connection.close()

