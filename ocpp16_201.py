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
import uuid
from datetime import datetime, timedelta
from asyncio import CancelledError
from logging import getLogger
from time import sleep

from beartype import beartype
from ocpp.routing import on
from ocpp.v16.datatypes import IdTagInfo
from ocpp.v16.enums import RegistrationStatus, Action, AuthorizationStatus, RemoteStartStopStatus
from ocpp.v16 import ChargePoint, call_result, call
from ocpp.v201 import call_result as call_result_201
from ocpp.v201.datatypes import GetVariableResultType
from ocpp.v201.enums import SetVariableStatusEnumType, GetVariableStatusEnumType, RequestStartStopStatusEnumType
from pydantic import BaseModel
from websockets import Subprotocol, ConnectionClosedOK

from client_v16 import OCPPClientV201, OCPPServerV16Interface
from ocpp_models.v16.boot_notification import BootNotificationRequest
from ocpp_models.v16.start_transaction import StartTransactionRequest
from ocpp_models.v16.status_notification import StatusNotificationRequest
from ocpp_models.v201.get_variables import GetVariablesRequest, GetVariableDataType
from ocpp_models.v201.request_start_transaction import RequestStartTransactionRequest
from proxy.proxy_config import ProxyConfigurator, ProxyConfig
from proxy.proxy_connection_context import ProxyConnectionContext
from proxy.proxy_connection_fsm import ProxyConnectionFSM
from proxy_connection_fsm_enums import ProxyConnectionFSMEvent, ProxyConnectionFSMState
from server.callable_interface import CallableInterface
from util import get_time_str, async_camelize_kwargs, log_req_response, with_request_model, time_based_id, \
    get_proxy_app_args

from datetime import  timezone

UTC_TZ = timezone(timedelta(0))
import sys

import ssl
import certifi
from typing import Any
import websockets
import traceback

from camel_converter import dict_to_camel

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

getLogger("websockets.server").setLevel(logging.WARNING)
getLogger("ocpp").setLevel(logging.WARNING)
getLogger("websockets.client").setLevel(logging.WARNING)

CONFIGURATION_MAP = {}
STUBS_MAP = {}

AUTH_STATUS_MAP = {RemoteStartStopStatus.accepted: RequestStartStopStatusEnumType.accepted,
                   RemoteStartStopStatus.rejected: RequestStartStopStatusEnumType.rejected
                   }

TX_MAP_16_TO_201 = dict()
TX_MAP_201_TO_16 = dict()

async def connect_as_client(client_interface, uri, serial_number, on_connect):

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
                cp = OCPPClientV201(client_interface, serial_number, ws)
                await on_connect(cp)


        except asyncio.exceptions.CancelledError:
            raise
        except:
            logger.error(traceback.format_exc())
            await asyncio.sleep(fallback)
            fallback *= 1.5


@beartype
class OCPPServer16Proxy(ChargePoint, CallableInterface, OCPPServerV16Interface):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.fsm = ProxyConnectionFSM(ProxyConnectionContext(charge_point_interface=self))
        self.server_connection : OCPPClientV201 | None = None

    async def server_connection_task(self, cp : OCPPClientV201):
        self.server_connection = cp
        logger.warning("self.server_connection.start")
        server_task = asyncio.create_task(self.server_connection.start())

        try:
            logger.warning("self.start before")
            await self.start()
            logger.warning("self.start after")
        except Exception:
            await server_task
            raise
        await server_task

    async def run(self):
        await connect_as_client(client_interface=self,
                                uri=ProxyConfigurator.get_global_config().upstream_uri,
                                serial_number=self.id,
                                on_connect=self.server_connection_task)

    async def call_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):
        try:
            return await self.call(payload, suppress, unique_id, skip_schema_validation)
        except websockets.exceptions.ConnectionClosedOK:
            await self.fsm.handle(ProxyConnectionFSMEvent.on_client_disconnect)
            return 


    #@on(Action.notify_event)
    #async def on_notify_event(self, **data):
    #    return call_result.NotifyEvent()

    @on(Action.boot_notification)
    @async_camelize_kwargs
    @log_req_response
    @with_request_model(BootNotificationRequest)
    async def on_boot_notification(self, rq : BootNotificationRequest, **kwargs):
        try:
            await self.server_connection.boot_notification_request(rq)
            await self.fsm.handle(ProxyConnectionFSMEvent.on_client_boot_notification_forwarded)
            return call_result.BootNotification(
                current_time=datetime.now(UTC_TZ).isoformat(),
                interval=10,
                status=RegistrationStatus.accepted,
            )
        except ConnectionClosedOK:
            return call_result.BootNotification(
                current_time=datetime.now(UTC_TZ).isoformat(),
                interval=60,
                status=RegistrationStatus.rejected,
            )


    @on(Action.status_notification)
    @async_camelize_kwargs
    @log_req_response
    @with_request_model(StatusNotificationRequest)
    async def on_status_notification(self, rq : StatusNotificationRequest, **kwargs):

        await self.server_connection.status_notification_request(rq)
        return call_result.StatusNotification(
        )


    @on(Action.start_transaction)
    @async_camelize_kwargs
    @log_req_response
    @with_request_model(StartTransactionRequest)
    async def on_start_transaction(self, rq : StartTransactionRequest, **kwargs):
        tx_id_16 = time_based_id()
        # Use normal sleep here to guarantee that tx_id_16 are unique
        sleep(0.1)
        tx_id_201 = str(uuid.uuid4())
        TX_MAP_16_TO_201[tx_id_16] = tx_id_201
        TX_MAP_201_TO_16[tx_id_201] = tx_id_16

        await self.server_connection.start_transaction_request(rq, tx_id_201)

        return call_result.StartTransaction(
            transaction_id=tx_id_16,
            id_tag_info=IdTagInfo(status=AuthorizationStatus.accepted)
        )

    @on(Action.heartbeat)
    @log_req_response
    async def on_heartbeat(self, **data):
        response : call_result_201.Heartbeat = await self.server_connection.heartbeat_request()
        return call_result.Heartbeat(
            current_time=response.current_time
        )

    @on(Action.meter_values, skip_schema_validation=True)
    @log_req_response
    async def on_meter_values(self, **data):
        return call_result.MeterValues(
        )

    @on(Action.authorize)
    @log_req_response
    async def on_authorize(self, **data):
        return call_result.Authorize(id_tag_info=IdTagInfo(status=AuthorizationStatus.accepted))
    """
    @on(Action.transaction_event)
    @log_req_response
    async def on_transaction_event(self, **data):
        logger.warning(f"{self.id} on_transaction_event {data=}")
        response = dict()
        if "id_token_info" in data:
            response.update(dict(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted)))
        return call_result.TransactionEvent(**response)

    @on(Action.notify_report)
    @log_req_response
    async def on_notify_report(self, **report_data):
        logger.warning(f"{self.id} on_notify_report {report_data=}")
        return call_result.NotifyReport()

    async def reboot_peer_and_close_connection(self, *vargs):
        await self.call_payload(call.Reset(type=ResetEnumType.immediate))
        await self.close_connection(*vargs)


    async def close_connection(self, *vargs):
        await self._connection.close()
    """

    def get_state_machine(self) -> ProxyConnectionFSM:
        return self.fsm

    async def on_request_start_transaction(self,
                                           request: RequestStartTransactionRequest) -> call_result_201.RequestStartTransaction:
        result : call_result.RemoteStartTransaction = await self.call_payload(call.RemoteStartTransaction(
                                                               id_tag=request.idToken.idToken[:20],
                                                               connector_id=request.evseId))
        id_tag_status : RemoteStartStopStatus = result.status

        if id_tag_status in AUTH_STATUS_MAP:
            req_result = AUTH_STATUS_MAP[id_tag_status]
        else:
            req_result = RequestStartStopStatusEnumType.rejected
        return call_result_201.RequestStartTransaction(status=req_result)

    async def on_server_get_variables(self, request: GetVariablesRequest) -> call_result_201.GetVariables:
        var : GetVariableDataType
        response_variables : list[GetVariableResultType] = []
        request_list : dict[str, GetVariableDataType] = {}
        reject_list : list[GetVariableDataType] = []

        for var in request.getVariableData:
            cname = var.component.name
            vname = var.variable.name
            if cname in CONFIGURATION_MAP:
                if vname in CONFIGURATION_MAP[cname]:
                    request_list[CONFIGURATION_MAP[cname][vname]] = var
                    continue
            reject_list.append(var)

        logger.warning(f"{list(request_list)=}")
        logger.warning(f"{reject_list=}")
        if len(request_list):
            result : call_result.GetConfiguration = await self.call_payload(call.GetConfiguration(key=list(request_list)))
            logger.warning(f"get varaibles {result=}")
        else:
            result: call_result.GetConfiguration = await self.call_payload(call.GetConfiguration(key=None))
            logger.warning(f"get all varaibles {result=}")
        # ToDo: There is nothing to request yet
        #for conf_key in result.configuration_key:
        #    conf_key
        for var in reject_list:
            var_val = self.get_stub_variable_value(var)
            if var_val is not None:
                response_variables.append(GetVariableResultType(attribute_status=GetVariableStatusEnumType.accepted,
                                                                component=var.component,
                                                                variable=var.variable,
                                                                attribute_value=var_val))
            else:
                response_variables.append(GetVariableResultType(attribute_status=GetVariableStatusEnumType.unknown_variable,
                                                                component=var.component,
                                                                variable=var.variable))
        logger.warning(f"{response_variables=}")
        return call_result_201.GetVariables(response_variables)

    def get_stub_variable_value(self, var : GetVariableDataType) -> str | None:
        if var.component.name == "ChargingStation" and var.variable.name == "SerialNumber":
            return str(self.id)
        return None

async def on_connect(websocket):
    logger.warning(f"on client connect {websocket=}")

    charge_point_id = websocket.request.path.strip("/")
    
    cp = OCPPServer16Proxy(id=charge_point_id, connection=websocket)

    try:
        result = await cp.run()
    except websockets.exceptions.ConnectionClosedOK:
        result = "Connection closed"
    except Exception as e:
        result = f"\n-------Exception {e}-----\n"+traceback.format_exc()+"\n----------------------\n"
    logger.info(f"connection_task.result {result}")


async def main():
    logging.warning("main start")
    config : ProxyConfig = ProxyConfigurator.get_global_config()
    server = await websockets.serve(on_connect, '0.0.0.0', config.service_port, subprotocols=[Subprotocol('ocpp1.6')])
    logging.warning("main server ready")
    try:
        await server.serve_forever()
    except CancelledError:
        pass
    logging.warning("main exit")

if __name__ == "__main__":
    args = get_proxy_app_args()
    ProxyConfigurator.set_global_config(ProxyConfig.model_validate(args.__dict__))
    asyncio.run(main())