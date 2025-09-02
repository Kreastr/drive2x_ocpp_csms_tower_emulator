from atfsm.atfsm import AFSM
from server.charge_point_model.charge_point_uml import charge_point_uml
from server.data import ChargePointContext
from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType, transaction_manager_uml
from tx_manager_fsm_enums import TxManagerFSMState

_fsm = AFSM(uml=charge_point_uml, context=ChargePointContext(), se_factory=lambda x: str(x))
_fsm.write_enums("ChargePointFSM")

from charge_point_fsm_enums import ChargePointFSMState, ChargePointFSMCondition, ChargePointFSMEvent

ChargePointFSMType = AFSM[ChargePointFSMState, ChargePointFSMCondition, ChargePointFSMEvent, ChargePointContext]

def get_charge_point_fsm(context : ChargePointContext) -> ChargePointFSMType:
    fsm = ChargePointFSMType(uml=charge_point_uml,
                           context=context,
                           se_factory=ChargePointFSMState)

    return fsm




def get_connector_manager_fsm(context : TxManagerContext) -> TxManagerFSMType:
    fsm = TxManagerFSMType(uml=transaction_manager_uml,
                           context=context,
                           se_factory=TxManagerFSMState)

    return fsm