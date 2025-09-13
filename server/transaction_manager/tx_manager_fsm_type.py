from atfsm.atfsm import AFSM
from server.data.tx_manager_context import TxManagerContext

transaction_manager_uml = """@startuml
[*] -> Unknown
Unknown --> Occupied : if occupied
Available --> Occupied : if occupied
Unknown --> Available : if available
Occupied --> Available : if available
Available --> Authorizing : on authorized
Authorizing --> Authorized : on authorize accept
Authorizing --> Unknown : on authorize reject
Occupied --> Occupied : on authorized
Occupied --> Ready : on authorize accept
Occupied --> Ready : on tx update event
Authorized --> Ready : on start tx event
Authorized --> Unknown : on deauthorized
Ready --> TransitionTriggered : on setpoint apply mark
Charging --> TransitionTriggered : on setpoint apply mark
Discharging --> TransitionTriggered : on setpoint apply mark
TransitionTriggered --> Charging : if charge setpoint
TransitionTriggered --> Discharging : if discharge setpoint
TransitionTriggered --> Ready : if idle setpoint
Charging --> Terminating : on deauthorized
Discharging --> Terminating : on deauthorized
Ready --> Terminating : on deauthorized
TransitionTriggered --> Terminating : on deauthorized
Ready --> Unknown : on end tx event
Ready --> Terminating : on termination fault
Charging --> Terminating : on termination fault
Discharging --> Terminating : on termination fault
TransitionTriggered --> Terminating : on termination fault
Terminating --> Fault : on termination fault
Terminating --> Unknown : on end tx event
TransitionTriggered --> Unknown : on end tx event
Fault --> Unknown : on clear fault
@enduml
"""
_fsm = AFSM(uml=transaction_manager_uml, context=TxManagerContext(), se_factory=lambda x: str(x))

_fsm.write_enums("TxManagerFSM")

from tx_manager_fsm_enums import TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent


TxManagerFSMType = AFSM[TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent, TxManagerContext]
