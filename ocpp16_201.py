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
import logging
import socket
import uuid
from datetime import datetime, timedelta, UTC
from asyncio import CancelledError, Lock
from logging import getLogger
from pathlib import Path
from time import sleep

import ocpp.v16.enums
from afsm import AFSM
from beartype import beartype
from ocpp.exceptions import TypeConstraintViolationError, GenericError
from ocpp.messages import CallError
from ocpp.routing import on
from ocpp.v16.datatypes import IdTagInfo
from ocpp.v16.enums import RegistrationStatus, Action, AuthorizationStatus, RemoteStartStopStatus, ResetType
from ocpp.v16 import ChargePoint, call_result, call
from ocpp.v16 import enums as v16enums
from ocpp.v201 import call_result as call_result_201
from ocpp.v201.datatypes import GetVariableResultType, VariableType, ComponentType, SetVariableResultType, EVSEType, \
    StatusInfoType
from ocpp.v201.enums import SetVariableStatusEnumType, GetVariableStatusEnumType, RequestStartStopStatusEnumType, \
    ResetEnumType, ResetStatusEnumType, RegistrationStatusEnumType, AuthorizationStatusEnumType

from redis_dict import RedisDict
from typing_extensions import TypeVar
from websockets import Subprotocol, ConnectionClosedOK, ConnectionClosedError

from client_v16 import OCPPClientV201, OCPPServerV16Interface
from ocpp_models.v16.authorize import AuthorizeRequest
from ocpp_models.v16.boot_notification import BootNotificationRequest
from ocpp_models.v16.meter_values import MeterValuesRequest
from ocpp_models.v16.security_event_notification import SecurityEventNotification
from ocpp_models.v16.start_transaction import StartTransactionRequest
from ocpp_models.v16.status_notification import StatusNotificationRequest
from ocpp_models.v16.stop_transaction import StopTransactionRequest
from ocpp_models.v201.composite_types import ChargingProfileType
from ocpp_models.v201.get_variables import GetVariablesRequest, GetVariableDataType
from ocpp_models.v201.request_start_transaction import RequestStartTransactionRequest
from ocpp_models.v201.request_stop_transaction import RequestStopTransactionRequest
from ocpp_models.v201.reset import ResetRequest
from ocpp_models.v201.set_variables import SetVariablesRequest, SetVariableDataType
from proxy.proxy_config import ProxyConfigurator, ProxyConfig
from proxy.proxy_connection_context import ProxyConnectionContext, CPInterface
from proxy.proxy_connection_fsm import ProxyConnectionFSM
from proxy_connection_fsm_enums import ProxyConnectionFSMEvent, ProxyConnectionFSMState
from server.callable_interface import CallableInterface
from util import async_camelize_kwargs, log_req_response, with_request_model, time_based_id, \
    get_proxy_app_args

from datetime import  timezone

from util.db import get_default_redis
from util.interval_trigger import proxy_setpoint_update_loop, proxy_fsm_update_loop

UTC_TZ = timezone(timedelta(0))

import ssl
import certifi
from typing import Any, Optional
import websockets
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

getLogger("websockets.server").setLevel(logging.WARNING)
getLogger("ocpp").setLevel(logging.WARNING)
getLogger("websockets.client").setLevel(logging.WARNING)
getLogger("afsm").setLevel(logging.DEBUG)

CONFIGURATION_MAP = {"V2XChargingCtrlr": {"Setpoint": "pBaseline"}}
STUBS_MAP = {}

AUTH_STATUS_MAP = {RemoteStartStopStatus.accepted: RequestStartStopStatusEnumType.accepted,
                   RemoteStartStopStatus.rejected: RequestStartStopStatusEnumType.rejected
                   }

TX_MAP_16_TO_201 = RedisDict("proxy-TX_MAP_16_TO_201-", redis=get_default_redis(get_proxy_app_args))
TX_MAP_201_TO_16 = RedisDict("proxy-TX_MAP_201_TO_16-", redis=get_default_redis(get_proxy_app_args))

RESET_TYPE_MAP = {ResetEnumType.immediate: ResetType.hard,
                  ResetEnumType.on_idle: ResetType.soft}

RESET_STATUS_MAP = {ocpp.v16.enums.ResetStatus.accepted : ResetStatusEnumType.accepted,
                    ocpp.v16.enums.ResetStatus.rejected : ResetStatusEnumType.rejected}

async def connect_as_client(client_interface : OCPPServerV16Interface, uri : str , serial_number, on_connect_cb, fsm : AFSM):

    #"wss://emotion-test.eu/ocpp/1"
    #uri = "wss://drive2x.lut.fi:443/ocpp/CP_ESS_01"

    ctx = ssl.create_default_context(cafile=certifi.where())  # <- CA bundle
    ws_args = dict(subprotocols=["ocpp2.0.1"],
                   open_timeout=15)


    if uri.startswith("wss://"):
        ws_args["ssl"] = ctx
    try:
        logger.info(f"Connecting to {uri=} {ws_args=}")
        async with websockets.connect(uri, **ws_args) as ws:
            cp = OCPPClientV201(client_interface, serial_number, ws)
            client_interface.upstream_interface = cp
            await on_connect_cb(cp)
            await cp.start()

    except websockets.exceptions.InvalidStatus as e:
            logger.info(str(e))
            await asyncio.sleep(15)
    except asyncio.exceptions.CancelledError:
        await asyncio.sleep(15)
        raise
    except Exception as e:
        if "[Errno 8]" in str(e):
            logger.info(str(e))
            await asyncio.sleep(15)
        else:
            logger.error(traceback.format_exc())

def find_value_from_v16_response(result, v16key) -> Optional[Any]:
    value = None
    for key_data in result.configuration_key:
        if key_data["key"] == v16key:
            value = key_data["value"]
            break
    return value

T = TypeVar("T")


def categorize_variables(rq_list : list[T]):
    request_list: dict[str, T] = {}
    reject_list: list[T] = []
    request_serial = False
    for var in rq_list:
        cname = var.component.name
        vname = var.variable.name
        if cname == "ChargingStation" and vname == "SerialNumber":
            request_serial = True
            continue
        if cname in CONFIGURATION_MAP:
            if vname in CONFIGURATION_MAP[cname]:
                request_list[CONFIGURATION_MAP[cname][vname]] = var
                continue
        reject_list.append(var)
    return reject_list, request_list, request_serial


def serial_var_component(serial_number):
    resp_cmpnt = ComponentType(name="ChargePoint",
                               instance=None)
    resp_var = VariableType(name="SerialNumber",
                            instance=var.variable.instance)
    return resp_cmpnt, resp_var

def clone_var_component(var):
    if var.component.evse:
        resp_cmpnt = ComponentType(name=var.component.name,
                                   instance=var.component.instance,
                                   evse=EVSEType(id=var.component.evse.id,
                                                 connector_id=var.component.evse.connectorId) )
    else:
        resp_cmpnt = ComponentType(name=var.component.name,
                                   instance=var.component.instance)
    resp_var = VariableType(name=var.variable.name,
                            instance=var.variable.instance)
    return resp_cmpnt, resp_var


def get_version_tag():
    version = ""
    version_file = Path("VERSION")
    if version_file.exists() and version_file.is_file():
        version = Path("VERSION").read_text()
    return version

@beartype
class OCPPServer16Proxy(ChargePoint, CPInterface, OCPPServerV16Interface):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.remote_start_id : int | None = None
        self.pending_tx_profiles = dict()
        self.fsm = ProxyConnectionFSM(ProxyConnectionContext(charge_point_interface=self),
                                                             fsm_name=f"OCPPServer16Proxy <{self.id} {datetime.now(tz=UTC).isoformat()}>")
        self.fsm.on(ProxyConnectionFSMState.server_disconnected.on_enter, self.close_downstream_connection)
        self.fsm.on(ProxyConnectionFSMState.client_disconnected.on_enter, self.close_upstream_connection)
        self.upstream_interface : OCPPClientV201 | None = None
        self.downstream_connected : bool = True
        self.cached_boot_notification : Optional[BootNotificationRequest] = None
        self.lock_try_forward : Lock = Lock()
        proxy_setpoint_update_loop().subscribe(self.periodic_setpoint_update)
        proxy_fsm_update_loop().subscribe(self.fsm_loop_runner)

    @log_req_response
    async def fsm_loop_runner(self, *vargs, **kwargs):
        if self.fsm.current_state != ProxyConnectionFSMState.finalizing:
            await self.fsm.loop()
            self.logger.warning(f"FSM state is {self.fsm.current_state}")
        else:
            self.logger.warning(f"{self.fsm} Unsubscribed from periodic loops.")
            proxy_fsm_update_loop().unsubscribe(self.fsm_loop_runner)
            proxy_setpoint_update_loop().unsubscribe(self.periodic_setpoint_update)
            await self.close_downstream_connection()
            await self.close_upstream_connection()

    @log_req_response
    async def try_connect_to_upstream(self):
        if self.upstream_interface is not None:
            await self.upstream_interface.close_connection()

        async def connect_cb(cp, s=self):
            s.fsm.context : ProxyConnectionContext
            s.fsm.context.csms_interface = cp
        # Callback will set upstream_interface for this class
        await connect_as_client(client_interface=self,
                                uri=ProxyConfigurator.get_global_config().upstream_uri,
                                serial_number=self.id,
                                on_connect_cb=connect_cb,
                                fsm=self.fsm)

    @log_req_response
    async def periodic_setpoint_update(self, *vargs, **kwargs):
        
        if self.upstream_interface is not None and self.upstream_interface.cpc is not None:
            next_setpoint = self.upstream_interface.cpc.get_power_setpoint(1, datetime.now(tz=UTC))
            try:
                result: call_result.ChangeConfiguration = await self.call_downstream_payload(
                    call.ChangeConfiguration(key="pBaseline", value=str(next_setpoint)))
            except Exception:
                self.logger.error("ToDo. Cleanup periodic_setpoint_update for dead connections")
                pass

    async def upstream_connection_task(self):
        logger.warning("upstream_connection_task()")

        try:
            await self.try_connect_to_upstream()
        except ConnectionClosedOK:
            self.upstream_interface = None
            logger.info("Upstream connection closed OK.")
            await asyncio.sleep(10)
        except ConnectionClosedError:
            self.upstream_interface = None
            logger.warning("Upstream connection closed with error.")
            await asyncio.sleep(10)
        except Exception as e:
            try:
                self.upstream_interface.close_connection()
            except:
                pass

            self.upstream_interface = None
            logger.warning(f"Exception in server_task start: {e} {traceback.format_exc()}")


    @log_req_response
    async def call_downstream_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):
        try:
            if self.downstream_connected:
                return await self.call(payload, suppress, unique_id, skip_schema_validation)
            else:
                logger.info(f"Downstream is already disconnected while calling downstream payload {payload=}. Raising ")
                raise ocpp.exceptions.GenericError(description="Downstream is disconnected. Cannot deliver.",
                                                   details=dict(retryable=True))
        except asyncio.TimeoutError:
            # Do not mark downstream as disconnected. This is not the hard fault yet.
            logger.warning(f"Got asyncio.TimeoutError while calling downstream payload {payload=}")
        except websockets.exceptions.ConnectionClosedOK:
            self.downstream_connected = False
            logger.info(f"Got ConnectionClosedOK while calling downstream payload {payload=}")
            raise ocpp.exceptions.GenericError(description="Downstream is disconnected. Cannot deliver.",
                                               details=dict(retryable=True))
        except websockets.exceptions.ConnectionClosedError:
            self.downstream_connected = False
            logger.warning(f"Got websockets.exceptions.ConnectionClosedError while calling downstream payload {payload=}")
            raise ocpp.exceptions.GenericError(description="Downstream is disconnected. Cannot deliver.",
                                               details=dict(retryable=True))


    #@on(Action.notify_event)
    #async def on_notify_event(self, **data):
    #    return call_result.NotifyEvent()

    @on(Action.boot_notification)
    @async_camelize_kwargs
    @log_req_response
    @with_request_model(BootNotificationRequest)
    async def on_boot_notification(self, rq : BootNotificationRequest, **kwargs):
        if rq.chargePointSerialNumber is None:
            rq.chargePointSerialNumber = self.id
        rq.firmwareVersion += "," + get_version_tag()
        self.cached_boot_notification = rq

        return call_result.BootNotification(
            current_time=datetime.now(UTC_TZ).isoformat(),
            interval=10,
            status=RegistrationStatus.accepted,
        )

    async def try_forward_data_to_upstream(self):
        logger.warning("try_forward_data_to_upstream")
        if self.upstream_interface is None:
            await asyncio.sleep(5)

        if self.lock_try_forward.locked():
            return

        async with self.lock_try_forward:
            for i in range(30):
                if self.cached_boot_notification is not None:
                    if self.upstream_interface is None:
                        return
                    else:
                        result = await self.upstream_interface.boot_notification_request(self.cached_boot_notification)
                        if result is not None:
                            if result.status == RegistrationStatusEnumType.accepted:
                                logger.info(f"Upstream accepted cached boot notification: {result=}")
                                await self.fsm.handle(ProxyConnectionFSMEvent.on_upstream_accepted_boot_notification)
                            else:
                                logger.warning(f"Upstream rejected cached boot notification: {result=}")
                        return result
                await asyncio.sleep(1)
            await self.fsm.handle(ProxyConnectionFSMEvent.on_upstream_accepted_boot_notification)




    @on(Action.status_notification)
    @async_camelize_kwargs
    @log_req_response
    @with_request_model(StatusNotificationRequest)
    async def on_status_notification(self, rq : StatusNotificationRequest, **kwargs):
        await self._ensure_upstream()
        await self.upstream_interface.status_notification_request(rq)

        return call_result.StatusNotification(
        )

    async def _ensure_upstream(self):
        if self.upstream_interface is None:
            await asyncio.sleep(5)
            if self.upstream_interface is None:
                self.logger.error(f"Upstream disconnected while FSM is in state {self.fsm.current_state}")
                if self.fsm.current_state == ProxyConnectionFSMState.finalizing:
                    await self.close_downstream_connection()
                raise GenericError(description=f"Failed to forward upstream. {self.fsm.current_state} {self.fsm}",
                                   details=dict(retryable=True))

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
        
        self.upstream_interface.cpc.on_tx_start(rq.connectorId, tx_id_201)

        if (self.remote_start_id is not None and 
            self.remote_start_id in self.pending_tx_profiles):
            profile : ChargingProfileType = self.pending_tx_profiles[self.remote_start_id]
            profile.transactionId = tx_id_201
            install_result = self.upstream_interface.cpc.install_profile_if_possible(profile, rq.connectorId)
            if install_result is not None:
                logger.error(f"Failed installing pending Tx Profile: {profile} Reason: {install_result} for {tx_id_201=}/{tx_id_16=}")
            
        await self.upstream_interface.start_transaction_request(rq, tx_id_201, self.remote_start_id)
        
        rsid = self.remote_start_id
        self.remote_start_id = None
        if rsid is not None and rsid in self.pending_tx_profiles:
            del self.pending_tx_profiles[rsid]

        return call_result.StartTransaction(
            transaction_id=tx_id_16,
            id_tag_info=IdTagInfo(status=AuthorizationStatus.accepted)
        )

    @on(Action.stop_transaction)
    @async_camelize_kwargs
    @log_req_response
    @with_request_model(StopTransactionRequest)
    async def on_stop_transaction(self, rq : StopTransactionRequest, **kwargs):
        #tx_id_16 = time_based_id()
        # Use normal sleep here to guarantee that tx_id_16 are unique
        #sleep(0.1)
        #tx_id_201 = str(uuid.uuid4())
        #TX_MAP_16_TO_201[tx_id_16] = tx_id_201
        #TX_MAP_201_TO_16[tx_id_201] = tx_id_16

        if str(rq.transactionId) in TX_MAP_16_TO_201:
            tx_id_201 = TX_MAP_16_TO_201[str(rq.transactionId)]
            self.upstream_interface.cpc.on_tx_end(tx_id_201)
            await self.upstream_interface.stop_transaction_request(rq, tx_id_201)
        else:
            logger.warning(f"Unknown transaction has ended {rq.transactionId=}. Cannot notify CSMS. {rq=}")

        return call_result.StopTransaction()

    @on(Action.heartbeat)
    async def on_heartbeat(self, **data):
        await self.fsm.handle(ProxyConnectionFSMEvent.on_downstream_heartbeat)

        if self.is_connected_to_ocpp_upstream():
            try:
                response = await self.upstream_interface.heartbeat_request()

                if response is not None and getattr(response, "current_time", None):
                    return call_result.Heartbeat(
                        current_time=response.current_time
                    )

            except Exception:
                self.logger.exception(
                    "Upstream heartbeat failed; replying locally"
                )
                await self.close_upstream_connection()

        # Autonomous/offline fallback.
        return call_result.Heartbeat(
            current_time=datetime.now(tz=UTC).isoformat()
        )

    @on(Action.meter_values, skip_schema_validation=True)
    @log_req_response
    @async_camelize_kwargs
    @with_request_model(MeterValuesRequest)
    async def on_meter_values(self, request : MeterValuesRequest, *vargs, **kwargs):
        txid16 = request.transactionId
        txid = None
        if txid16 is not None:
            if txid16 not in TX_MAP_16_TO_201:
                tx_id_201 = str(uuid.uuid4())
                TX_MAP_16_TO_201[str(txid16)] = tx_id_201
                TX_MAP_201_TO_16[tx_id_201] = txid16
            txid = TX_MAP_16_TO_201[str(txid16)]
        if self.upstream_interface is not None:
            # Todo cache meter values
            await self.upstream_interface.meter_values_request(request, tx_id=txid)
        return call_result.MeterValues(
        )

    @on(Action.authorize)
    @log_req_response
    @async_camelize_kwargs
    @with_request_model(AuthorizeRequest)
    async def on_authorize(self, request: AuthorizeRequest, **data):
        await self._ensure_upstream()

        result : call_result_201.Authorize = await self.upstream_interface.on_authorize_request(request)
        logger.info(f"Server responded to auth request {result.id_token_info=}")
        if result.id_token_info["status"] == AuthorizationStatusEnumType.accepted:
            return call_result.Authorize(id_tag_info=IdTagInfo( status=AuthorizationStatus.accepted))

        return call_result.Authorize(id_tag_info=IdTagInfo(status=AuthorizationStatus.invalid))


    @on(Action.security_event_notification)
    @log_req_response
    @async_camelize_kwargs
    @with_request_model(SecurityEventNotification)
    async def on_security_event_notification(self, request : SecurityEventNotification, *vargs, **kwargs):
        return call_result.SecurityEventNotification()

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
    """

    def is_connected_to_ocpp_upstream(self) -> bool:
        return self.upstream_interface is not None

    def is_connected_to_ocpp_downstream(self) -> bool:
        return self.downstream_connected

    def get_charge_point_id(self) -> str:
        return  self.id

    async def on_server_set_variables(self, request: SetVariablesRequest) -> call_result_201.SetVariables:
        var: SetVariableDataType
        response_variables: list[SetVariableResultType] = []
        reject_list, request_list, request_serial = categorize_variables(request.setVariableData)

        logger.warning(f"{list(request_list)=}")
        logger.warning(f"{reject_list=}")

        for key, var in request_list.items():
            response = await self.forward_set_variable(key, var)
            response_variables.append(response)

        for var in reject_list:
            resp_cmpnt, resp_var = clone_var_component(var)

            response_variables.append(SetVariableResultType(attribute_status=SetVariableStatusEnumType.rejected,
                                                            component=resp_cmpnt,
                                                            variable=resp_var))
        logger.warning(f"{response_variables=}")
        return call_result_201.SetVariables(response_variables)

    async def forward_set_variable(self, key, var):
        resp_cmpnt, resp_var = clone_var_component(var)
        value = var.attributeValue
        result: call_result.ChangeConfiguration = await self.call_downstream_payload(
            call.ChangeConfiguration(key=key, value=value))
        logger.info(f"forward set varaible {key=} {value=} {result=}")
        if result.status == v16enums.ConfigurationStatus.accepted:
            response = SetVariableResultType(attribute_status=SetVariableStatusEnumType.accepted,
                                             component=resp_cmpnt,
                                             variable=resp_var)
        else:
            response = SetVariableResultType(attribute_status=SetVariableStatusEnumType.rejected,
                                             component=resp_cmpnt,
                                             variable=resp_var)
        return response

    @log_req_response
    @beartype
    async def on_reset(self, request : ResetRequest) -> call_result_201.Reset:
        logger.warning(f"on_reset {self.id=}")
        #if self.has_icl_latiniki_hack:
        #    v16_type = ResetType.soft
        #else:
        if request.type in RESET_TYPE_MAP:
            v16_type = RESET_TYPE_MAP[request.type]
        else:
            v16_type = ResetType.hard
        logger.warning(f"on_reset pre-call {self.id=}")
        try:
            response : Optional[call_result.Reset] = await self.call_downstream_payload(call.Reset(type=v16_type))
        except GenericError:
            response = None

        logger.warning(f"on_reset post-call {response=}")

        if response is not None and response.status in RESET_STATUS_MAP:
            v201_status = RESET_STATUS_MAP[response.status]
        else:
            v201_status = ResetStatusEnumType.rejected

        self.fsm.context : ProxyConnectionContext
        self.fsm.context.termination_flag = True
        logger.warning(f"{self.fsm.context=}")

        return call_result_201.Reset(status=v201_status)

    async def close_upstream_connection(self, *vargs):
        if self.upstream_interface:
            tmp_ref = self.upstream_interface
            self.upstream_interface = None
            await tmp_ref.close_connection()

    async def close_downstream_connection(self, *vargs):
        self.downstream_connected = False
        await self._connection.close()


    def get_state_machine(self) -> ProxyConnectionFSM:
        return self.fsm

    @log_req_response
    async def on_request_start_transaction(self,
                                           request: RequestStartTransactionRequest) -> call_result_201.RequestStartTransaction:
        self.remote_start_id = request.remoteStartId
        result : call_result.RemoteStartTransaction = await self.call_downstream_payload(call.RemoteStartTransaction(
                                                               id_tag=request.idToken.idToken[:20],
                                                               connector_id=request.evseId))


        id_tag_status : RemoteStartStopStatus = result.status

        if id_tag_status in AUTH_STATUS_MAP:
            req_result = AUTH_STATUS_MAP[id_tag_status]
        else:
            req_result = RequestStartStopStatusEnumType.rejected

        if req_result == req_result.accepted:
            if request.chargingProfile is not None:
                self.pending_tx_profiles[request.remoteStartId] = request.chargingProfile

        return call_result_201.RequestStartTransaction(status=req_result)

    @log_req_response
    async def on_request_stop_transaction(self,
                                          request: RequestStopTransactionRequest) -> call_result_201.RequestStopTransaction:
        if request.transactionId not in TX_MAP_201_TO_16:
            return call_result_201.RequestStopTransaction(status=RequestStartStopStatusEnumType.rejected,
                                                          status_info=StatusInfoType(reason_code="UNKNOWN_TX", additional_info=f"Transaction {request.transactionId} not found in transaction mapping."))
        tx_id_16 = TX_MAP_201_TO_16[request.transactionId]
        result : call_result.RemoteStopTransaction = await self.call_downstream_payload(call.RemoteStopTransaction(transaction_id=tx_id_16))
        if result is None:
            return call_result_201.RequestStopTransaction(status=RequestStartStopStatusEnumType.rejected,
                                                          status_info=StatusInfoType(reason_code="CS_CONNECTION_FAILED",
                                                                                     additional_info=f"Not possible to send stop transaction request due to connection problem."))

        if result.status in AUTH_STATUS_MAP:
            req_result = AUTH_STATUS_MAP[result.status]
        else:
            req_result = RequestStartStopStatusEnumType.rejected
        return call_result_201.RequestStopTransaction(status=req_result)


    async def on_server_get_variables(self, request: GetVariablesRequest) -> call_result_201.GetVariables:
        var : GetVariableDataType
        response_variables : list[GetVariableResultType] = []
        reject_list, request_list, request_serial = categorize_variables(request.getVariableData)

        logger.warning(f"{list(request_list)=}")
        logger.warning(f"{reject_list=}")
        try:
            if len(request_list):
                #try:
                #    result : call_result.GetConfiguration = await self.call_downstream_payload(call.GetConfiguration(key=list(request_list)))
                #except GenericError:
                result = None
                if result is None:
                    reject_list += list(request_list)
                    request_list = dict()
                else:
                    logger.info(f"get varaibles {result=}")
            else:
                #result = await self.call_downstream_payload(call.GetConfiguration(key=None))
                result = None
                if result is None:
                    reject_list += list(request_list)
                    request_list = dict()
                else:
                    logger.info(f"get all varaibles {result=}")

        except TypeConstraintViolationError:
            result = None


        for v16key, var in request_list.items():
            resp_cmpnt, resp_var = clone_var_component(var)
            if result is not None:
                value = find_value_from_v16_response(result, v16key)
                response_variables.append(GetVariableResultType(attribute_status=GetVariableStatusEnumType.accepted,
                                                                component=resp_cmpnt,
                                                                variable=resp_var,
                                                                attribute_value=str(value)))
            else:
                response_variables.append(GetVariableResultType(attribute_status=GetVariableStatusEnumType.unknown_variable,
                                                                component=resp_cmpnt,
                                                                variable=resp_var))

        if request_serial:
            response_variables.append(GetVariableResultType(attribute_status=GetVariableStatusEnumType.accepted,
                                                            component=ComponentType(name="ChargePoint"),
                                                            variable=VariableType(name="SerialNumber"),
                                                            attribute_value=str(self.id)))
        for var in reject_list:
            var_val = self.get_stub_variable_value(var)
            resp_cmpnt, resp_var = clone_var_component(var)
            if var_val is not None:
                response_variables.append(GetVariableResultType(attribute_status=GetVariableStatusEnumType.accepted,
                                                                component=resp_cmpnt,
                                                                variable=resp_var,
                                                                attribute_value=var_val))
            else:
                response_variables.append(GetVariableResultType(attribute_status=GetVariableStatusEnumType.unknown_variable,
                                                                component=resp_cmpnt,
                                                                variable=resp_var))
        logger.warning(f"{response_variables=}")
        return call_result_201.GetVariables(response_variables)

    def get_stub_variable_value(self, var : GetVariableDataType) -> str | None:
        if var.component.name == "ChargingStation" and var.variable.name == "SerialNumber":
            return str(self.id)
        return None

ChargePointInstances = dict()

async def on_connect(websocket):
    logger.warning(f"on client connect {websocket=}")

    charge_point_id = websocket.request.path.strip("/").split("/")[-1]


    cp = OCPPServer16Proxy(id=charge_point_id, connection=websocket)
    task = asyncio.create_task(cp.upstream_connection_task())

    if charge_point_id in ChargePointInstances:
        old_cp = ChargePointInstances[charge_point_id]
        #await old_cp.
        cp.remote_start_id = old_cp.remote_start_id
        cp.pending_tx_profiles = old_cp.pending_tx_profiles

    ChargePointInstances[charge_point_id] = cp

    try:
        result = await cp.start()
    except websockets.exceptions.ConnectionClosedOK:
        result = "Connection closed"
    except Exception as e:
        result = f"\n-------Exception {e}-----\n"+traceback.format_exc()+"\n----------------------\n"
    logger.info(f"connection_task.result {result}")
    await task


async def main():
    logging.warning("main start")
    config : ProxyConfig = ProxyConfigurator.get_global_config()
    server = await websockets.serve(on_connect, config.service_host, config.service_port, subprotocols=[Subprotocol('ocpp1.6')])
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
