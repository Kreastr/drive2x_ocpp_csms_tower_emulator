from atfsm.atfsm import AFSM
from client.data import TxFSMContext, EvseModel

transaction_uml = """@startuml
[*] -> Idle
Idle --> Authorized : on authorized
Idle --> CableConnected : if cable connected
CableConnected --> Idle : if cable disconnected
Authorized --> TransactionAuthFirst : if cable connected
CableConnected --> TransactionCableFirst : on authorized
TransactionCableFirst --> Transaction
TransactionAuthFirst --> Transaction
Transaction --> Transaction : on report interval
Transaction --> StopTransactionDisconnected : if cable disconnected
StopTransactionDisconnected -> Idle
Transaction --> StopTransactionDeauthorized : on deauthorized
StopTransactionDeauthorized --> Idle
Authorized --> Idle : on deauthorized
@enduml
"""
_fsm = AFSM(uml=transaction_uml, context=TxFSMContext(EvseModel.model_validate(dict(id=1))), se_factory=lambda x: str(x))

_fsm.write_enums("TxFSM")

from tx_fsm_enums import TxFSMState, TxFSMCondition, TxFSMEvent

TxFSMType = AFSM[TxFSMState, TxFSMCondition, TxFSMEvent, TxFSMContext]
