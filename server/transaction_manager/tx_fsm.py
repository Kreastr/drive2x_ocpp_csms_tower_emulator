from typing import Any
from uuid import uuid4

from ocpp.v201 import call
from ocpp.v201.datatypes import IdTokenType
from ocpp.v201.enums import IdTokenEnumType

from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType, transaction_manager_uml
from tx_manager_fsm_enums import TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent
from util import setup_logging, time_based_id

logger = setup_logging(__name__)



class TxFSMS(TxManagerFSMType):

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

    @staticmethod
    def if_charge_setpoint(self, context : TxManagerContext, other):
        return context.connector.setpoint > 0

    @staticmethod
    def if_idle_setpoint(self, context : TxManagerContext, other):
        return context.connector.setpoint == 0.0

    @staticmethod
    def if_discharge_setpoint(self, context : TxManagerContext, other):
        return context.connector.setpoint < 0

    async def send_deauth_to_cp(self, *vargs):
        if self.context.cp_interface is not None:
            if self.context.tx_id is None:
                await self.handle(TxManagerFSMEvent.on_end_tx_event)
                return
            
            result = await self.context.cp_interface.call(
                call.RequestStopTransaction(transaction_id=self.context.tx_id))
            logger.warning(f"send_deauth_to_cp {result=}")
            if result.status == "Accepted":
                await self.handle(TxManagerFSMEvent.on_end_tx_event)
                return

        await self.handle(TxManagerFSMEvent.on_termination_fault)

    async def send_auth_to_cp(self, *vargs):
        if self.context.cp_interface is not None:
            result = await self.context.cp_interface.call(
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
        return ctxt.connector.connector_status == "Available"

    @staticmethod
    def if_occupied(ctxt: TxManagerContext, optional: Any):
        return ctxt.connector.connector_status == "Occupied"
