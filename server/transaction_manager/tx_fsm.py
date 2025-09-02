from typing import Any
from uuid import uuid4

from ocpp.v201 import call
from ocpp.v201.datatypes import IdTokenType
from ocpp.v201.enums import IdTokenEnumType

from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from server.transaction_manager.tx_manager_uml_provider import transaction_manager_uml
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

        self.on(TxManagerFSMState.authorized.on_enter, self.send_auth_to_cp)
        self.on(TxManagerFSMState.occupied.on_loop, self.send_auth_to_cp)

    async def send_auth_to_cp(self, *vargs):
        if self.context.cp_interface is not None:
            result = await self.context.cp_interface.call(
                call.RequestStartTransaction(evse_id=self.context.connector.evse_id,
                                             remote_start_id=time_based_id(),
                                             id_token=IdTokenType(id_token=str(uuid4()), type=IdTokenEnumType.central)))
            logger.warning(f"send_auth_to_cp {result=}")
        else:
            await self.handle(TxManagerFSMEvent.on_deauthorized)

    @staticmethod
    def if_available(ctxt: TxManagerContext, optional: Any):
        logger.warning("Testing if available")
        return ctxt.connector.connector_status == "Available"

    @staticmethod
    def if_occupied(ctxt: TxManagerContext, optional: Any):
        logger.warning("Testing if occupied")
        return ctxt.connector.connector_status == "Occupied"
