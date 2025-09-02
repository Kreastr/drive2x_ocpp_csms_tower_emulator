from atfsm.atfsm import AFSM
from client.data import TxFSMContext, ConnectorModel
from client.transaction_model.transaction_uml import transaction_uml
_fsm = AFSM(uml=transaction_uml, context=TxFSMContext(ConnectorModel(1)), se_factory=lambda x: str(x))

_fsm.write_enums("TxFSM")

from tx_fsm_enums import TxFSMState, TxFSMCondition, TxFSMEvent

TxFSMType = AFSM[TxFSMState, TxFSMCondition, TxFSMEvent, TxFSMContext]
