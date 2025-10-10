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


from typing import Any
from uuid import uuid4

from ocpp.v201 import call
from ocpp.v201.datatypes import IdTokenType, SetVariableDataType, ComponentType, EVSEType, VariableType
from ocpp.v201.enums import IdTokenEnumType

from server.data.tx_manager_context import TxManagerContext
from util.interval_trigger import main_setpoint_loop
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType, transaction_manager_uml
from tx_manager_fsm_enums import TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent
from util import setup_logging, time_based_id

logger = setup_logging(__name__)



class TxFSMServer(TxManagerFSMType):

    def __init__(self):
        super().__init__(transaction_manager_uml,
                         se_factory=TxManagerFSMState,
                         context=TxManagerContext())
        self.apply_to_all_conditions(TxManagerFSMCondition.if_available, self.if_available)
        self.apply_to_all_conditions(TxManagerFSMCondition.if_occupied, self.if_occupied)
        self.apply_to_all_conditions(TxManagerFSMCondition.if_charge_setpoint, self.if_charge_setpoint)
        self.apply_to_all_conditions(TxManagerFSMCondition.if_idle_setpoint, self.if_idle_setpoint)
        self.apply_to_all_conditions(TxManagerFSMCondition.if_discharge_setpoint, self.if_discharge_setpoint)

        self.on(TxManagerFSMState.authorizing.on_enter, self.send_auth_to_cp)
        self.on(TxManagerFSMState.occupied.on_loop, self.send_auth_to_cp)
        self.on(TxManagerFSMState.terminating.on_enter, self.send_deauth_to_cp)

        self.on(TxManagerFSMState.transition_triggered.on_exit, self.send_new_setpoint)

        main_setpoint_loop().subscribe(lambda s=self: s.handle(TxManagerFSMEvent.on_setpoint_apply_mark))
        
        
    @staticmethod
    def if_charge_setpoint(context : TxManagerContext, other):
        return context.evse.setpoint > 0

    @staticmethod
    def if_idle_setpoint(context : TxManagerContext, other):
        return context.evse.setpoint == 0.0

    @staticmethod
    def if_discharge_setpoint(context : TxManagerContext, other):
        return context.evse.setpoint < 0

    async def send_new_setpoint(self, *vargs):
        self.context: TxManagerContext
        setpoint = int(self.context.evse.setpoint)
        if self.context.cp_interface is not None:
            result = await self.context.cp_interface.call_payload(
                call.SetVariables(set_variable_data=[SetVariableDataType(attribute_value=str(setpoint),
                                                                         component=ComponentType(
                                                                             name="V2XChargingCtrlr", instance="1",
                                                                             evse=EVSEType(id=self.context.evse.evse_id)),
                                                                         variable=VariableType(name="Setpoint"))]))
            logger.warning(f"send_new_setpoint {setpoint=} {result=}")
            self.context.evse.setpoint = 0
            for v in result.set_variable_result:
                status = v["attribute_status"]
                logger.warning(status)
                #if status == AttributeStatusType()
                pass

    async def send_deauth_to_cp(self, *vargs):
        self.context : TxManagerContext
        if self.context.cp_interface is not None:
            if self.context.tx_id is None:
                await self.handle(TxManagerFSMEvent.on_end_tx_event)
                return

            stop_request = call.RequestStopTransaction(transaction_id=self.context.tx_id)
            
            result = await self.context.cp_interface.call_payload(
                stop_request)
            logger.warning(f"send_deauth_to_cp {stop_request=} {result=}")
            if result.status == "Accepted":
                await self.handle(TxManagerFSMEvent.on_end_tx_event)
                return

        await self.handle(TxManagerFSMEvent.on_termination_fault)

    async def send_auth_to_cp(self, *vargs):
        self.context : TxManagerContext
        if self.context.cp_interface is not None:
            result = await self.context.cp_interface.call_payload(
                call.RequestStartTransaction(evse_id=self.context.evse.evse_id,
                                             remote_start_id=time_based_id(),
                                             id_token=IdTokenType(id_token=str(uuid4()), type=IdTokenEnumType.central)))
            logger.warning(f"send_auth_to_cp {result=}")
            if result.status == "Accepted":
                await self.handle(TxManagerFSMEvent.on_authorize_accept)
                return

        await self.handle(TxManagerFSMEvent.on_authorize_reject)

    @staticmethod
    def if_available(ctxt: TxManagerContext, optional: Any):
        return ctxt.evse.connector_status == "Available"

    @staticmethod
    def if_occupied(ctxt: TxManagerContext, optional: Any):
        return ctxt.evse.connector_status == "Occupied"
