from atfsm.atfsm import AFSM
from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_manager_uml_provider import transaction_manager_uml

_fsm = AFSM(uml=transaction_manager_uml, context=TxManagerContext(), se_factory=lambda x: str(x))


_fsm.write_enums("TxManagerFSM")

from tx_manager_fsm_enums import TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent

TxManagerFSMType = AFSM[TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent, TxManagerContext]
