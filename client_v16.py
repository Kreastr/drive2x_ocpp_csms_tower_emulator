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

>>> import json
>>> from camel_converter import dict_to_camel
>>> data='{"connector_id": 1, "transaction_id": 282683992, "meter_value": [{"timestamp": "2025-11-26T13:20:51.934Z", "sampled_value": [{"unit": "Wh", "value": 0, "location": "Outlet", "measurand": "Energy.Active.Import.Register"}, {"unit": "W", "value": 180000, "location": "Outlet", "measurand": "Power.Active.Import"}, {"unit": "W", "value": 180000, "location": "Outlet", "measurand": "Power.Offered"}, {"unit": "Percent", "value": 19.5444, "location": "EV", "measurand": "SoC"}]}]}'
>>> jdata = dict_to_camel(json.loads(data))
>>> jdata
{'connectorId': 1, 'transactionId': 282683992, 'meterValue': [{'timestamp': '2025-11-26T13:20:51.934Z', 'sampledValue': [{'unit': 'Wh', 'value': 0, 'location': 'Outlet', 'measurand': 'Energy.Active.Import.Register'}, {'unit': 'W', 'value': 180000, 'location': 'Outlet', 'measurand': 'Power.Active.Import'}, {'unit': 'W', 'value': 180000, 'location': 'Outlet', 'measurand': 'Power.Offered'}, {'unit': 'Percent', 'value': 19.5444, 'location': 'EV', 'measurand': 'SoC'}]}]}
>>> rq = MeterValuesRequest.model_validate(jdata)
>>> convert_meter_values_to_201(rq)
[MeterValueType(timestamp='2025-11-26 13:20:51.934000+00:00', sampled_value=[SampledValueType(value=0.0, context=None, measurand=<MeasurandEnumType.energy_active_import_register: 'Energy.Active.Import.Register'>, phase=None, location=None, signed_meter_value=None, unit_of_measure=<UnitOfMeasureType.wh: 'Wh'>), SampledValueType(value=180000.0, context=None, measurand=<MeasurandEnumType.power_active_import: 'Power.Active.Import'>, phase=None, location=None, signed_meter_value=None, unit_of_measure=<UnitOfMeasureType.w: 'W'>), SampledValueType(value=180000.0, context=None, measurand=<MeasurandEnumType.power_offered: 'Power.Offered'>, phase=None, location=None, signed_meter_value=None, unit_of_measure=<UnitOfMeasureType.w: 'W'>), SampledValueType(value=19.5444, context=None, measurand=<MeasurandEnumType.soc: 'SoC'>, phase=None, location=None, signed_meter_value=None, unit_of_measure=<UnitOfMeasureType.percent: 'Percent'>)])]
"""
import datetime
from abc import ABC, abstractmethod
from logging import getLogger

import websockets
from ocpp.v16.enums import ChargePointStatus, Reason, Measurand, UnitOfMeasure
from ocpp.v201.datatypes import ChargingStationType, TransactionType, MeterValueType, SampledValueType
from ocpp.v201.enums import BootReasonEnumType, ConnectorStatusEnumType, TransactionEventEnumType, TriggerReasonEnumType
from ocpp.v201.enums import Action

from ocpp_models.v16.boot_notification import BootNotificationRequest
from ocpp_models.v16.meter_values import MeterValuesRequest, MeterValue, SampledValue
from ocpp_models.v16.start_transaction import StartTransactionRequest
from ocpp_models.v16.status_notification import StatusNotificationRequest
from ocpp_models.v16.stop_transaction import StopTransactionRequest
from ocpp_models.v201.get_variables import GetVariablesRequest
from ocpp_models.v201.request_start_transaction import RequestStartTransactionRequest
from ocpp_models.v201.reset import ResetRequest
from ocpp_models.v201.set_variables import SetVariablesRequest
from proxy.proxy_connection_fsm import ProxyConnectionFSM
from proxy_connection_fsm_enums import ProxyConnectionFSMEvent
from util import log_req_response, with_request_model, async_camelize_kwargs

logger = getLogger(__name__)

from ocpp.routing import on
from ocpp.v201 import ChargePoint, call, call_result
from ocpp.v201 import enums as enums201



class OCPPServerV16Interface(ABC):

    @abstractmethod
    async def on_server_get_variables(self, request : GetVariablesRequest) -> call_result.GetVariables:
        pass

    @abstractmethod
    async def on_server_set_variables(self, request : SetVariablesRequest) -> call_result.SetVariables:
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

MEASURAND_MAPPING = {Measurand.soc : enums201.MeasurandEnumType.soc,
                     Measurand.energy_active_import_register : enums201.MeasurandEnumType.energy_active_import_register,
                     Measurand.energy_active_export_register : enums201.MeasurandEnumType.energy_active_export_register,
                     Measurand.power_active_import : enums201.MeasurandEnumType.power_active_import,
                     Measurand.power_active_export : enums201.MeasurandEnumType.power_active_export,
                     Measurand.power_offered : enums201.MeasurandEnumType.power_offered}


#UNIT_MAP = {UnitOfMeasure.w: UnitOfMeasureType(,
#            UnitOfMeasure.wh: enums201.UnitOfMeasureType.wh,
#            UnitOfMeasure.percent: enums201.UnitOfMeasureType.percent}

STATUS_MAP = {ChargePointStatus.preparing: ConnectorStatusEnumType.available,
              ChargePointStatus.available: ConnectorStatusEnumType.available,
              ChargePointStatus.unavailable: ConnectorStatusEnumType.unavailable,
              ChargePointStatus.suspended_evse: ConnectorStatusEnumType.occupied,
              ChargePointStatus.suspended_ev: ConnectorStatusEnumType.occupied,
              ChargePointStatus.charging: ConnectorStatusEnumType.occupied}

STOP_REASON_MAP = {Reason.emergency_stop: TriggerReasonEnumType.abnormal_condition,
              Reason.ev_disconnected: TriggerReasonEnumType.ev_communication_lost,
                Reason.hard_reset: TriggerReasonEnumType.reset_command,
                Reason.local: TriggerReasonEnumType.stop_authorized,
                Reason.other: TriggerReasonEnumType.abnormal_condition,
                Reason.power_loss: TriggerReasonEnumType.abnormal_condition,
                Reason.reboot: TriggerReasonEnumType.reset_command,
                Reason.remote: TriggerReasonEnumType.remote_stop,
                Reason.soft_reset: TriggerReasonEnumType.reset_command,
                Reason.unlock_command: TriggerReasonEnumType.unlock_command,
                Reason.de_authorized: TriggerReasonEnumType.deauthorized}


def convert_meter_values_to_201(rq):
    v201_meter_values: list[MeterValueType] = list()
    mv: MeterValue
    for mv in rq.meterValue:
        v201_sampled_values: list[SampledValueType] = list()
        sv: SampledValue
        for sv in mv.sampledValue:
            try:
                fv = float(sv.value)
            except:
                logger.warning(f"Failed to convert sampled value {sv} to destination format (float)")
                continue
            reading_context = enums201.ReadingContextEnumType
            measurand = None
            if sv.measurand is not None:
                if sv.measurand in MEASURAND_MAPPING:
                    measurand = MEASURAND_MAPPING[sv.measurand]
                else:
                    logger.warning(f"Failed to convert measurand info {sv.measurand}")
            unit = None
            #if sv.unit is not None:
            #    if sv.unit in UNIT_MAP:
            #        unit = UNIT_MAP[sv.unit]
            #    else:
            #        logger.warning(f"Failed to convert measurand unit {sv.unit}")
            v201_sampled_values.append(SampledValueType(fv,
                                                        measurand=measurand,
                                                        unit_of_measure=unit))
        v201_meter_values.append(MeterValueType(timestamp=str(mv.timestamp),
                                                sampled_value=v201_sampled_values))
    return v201_meter_values


class OCPPClientV201(ChargePoint):

    def __init__(self, client_interface : OCPPServerV16Interface, serial_number, ws, response_timeout=30, _logger=logger):
        super().__init__(serial_number, ws, response_timeout=response_timeout, logger=_logger)
        self.client_interface = client_interface
        # ToDo store in redis
        self.tx_seq_no = 1

    async def meter_values_request(self, rq: MeterValuesRequest, tx_id : str | None):
        v201_meter_values = convert_meter_values_to_201(rq)
        if tx_id is not None:
            self.tx_seq_no += 1
            if len(rq.meterValue):
                await self.call_payload(call.TransactionEvent(event_type=TransactionEventEnumType.updated,
                                                              timestamp=rq.meterValue[0].timestamp.isoformat(),
                                                              trigger_reason=TriggerReasonEnumType.meter_value_periodic,
                                                              seq_no=self.tx_seq_no,
                                                              transaction_info=TransactionType(tx_id)))
        await self.call_payload(call.MeterValues(evse_id=rq.connectorId, meter_value=v201_meter_values))


    async def status_notification_request(self, rq : StatusNotificationRequest) -> call_result.StatusNotification:

        if rq.status == ChargePointStatus.preparing and rq.info is not None: 
            if rq.info == 'EVConnected':
                fwd_status = ConnectorStatusEnumType.occupied
            else:
                fwd_status = ConnectorStatusEnumType.available
        elif rq.status in STATUS_MAP:        
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

    async def send_transaction_event(self, rq : call.TransactionEvent):
        self.tx_seq_no += 1
        rq.seq_no = self.tx_seq_no
        await self.call_payload(rq)

    async def start_transaction_request(self, rq : StartTransactionRequest, tx_id : str) -> call_result.TransactionEvent:
        self.tx_seq_no = 1
        return await self.call_payload(call.TransactionEvent(event_type=TransactionEventEnumType.started,
                                                             timestamp=rq.timestamp.isoformat(),
                                                             trigger_reason=TriggerReasonEnumType.remote_start,
                                                             seq_no=self.tx_seq_no,
                                                             transaction_info=TransactionType(tx_id)))


    async def stop_transaction_request(self, rq : StopTransactionRequest, tx_id : str) -> call_result.TransactionEvent:
        self.tx_seq_no += 1
        if rq.reason in STOP_REASON_MAP:
            reason = STOP_REASON_MAP[rq.reason]
        else:
            reason = TriggerReasonEnumType.abnormal_condition
        return await self.call_payload(call.TransactionEvent(event_type=TransactionEventEnumType.ended,
                                                             timestamp=rq.timestamp.isoformat(),
                                                             trigger_reason=reason,
                                                             seq_no=self.tx_seq_no,
                                                             transaction_info=TransactionType(tx_id),
                                                             custom_data={"original_reason": str(rq.reason), "vendor_id": "OCPP v16 Proxy"}))


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


    @on(Action.set_variables)
    @log_req_response
    @async_camelize_kwargs
    @with_request_model(SetVariablesRequest)
    async def on_set_variables(self, request : SetVariablesRequest, *vargs, **kwargs):
        return await self.client_interface.on_server_set_variables(request)

    @log_req_response
    async def call_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):

        try:
            return await self.call(payload, suppress, unique_id, skip_schema_validation)
        except websockets.exceptions.ConnectionClosedOK:
            await self.client_interface.get_state_machine().handle(ProxyConnectionFSMEvent.on_server_disconnect)
        except websockets.exceptions.ConnectionClosedError:
            await self.client_interface.get_state_machine().handle(ProxyConnectionFSMEvent.on_server_disconnect)

    async def close_connection(self):
        await self._connection.close()
        await self.client_interface.get_state_machine().handle(ProxyConnectionFSMEvent.on_server_disconnect)
