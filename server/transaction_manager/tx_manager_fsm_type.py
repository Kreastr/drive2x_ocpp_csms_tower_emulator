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
Occupied --> Ready : on start tx event
Authorized --> Ready : on start tx event
Authorized --> Unknown : on deauthorized
Ready --> Charging : if charge setpoint
Discharging --> Charging : if charge setpoint
Ready --> Discharging : if discharge setpoint
Charging --> Discharging : if discharge setpoint
Charging --> Ready : if idle setpoint
Charging --> Charging : on setpoint update
Discharging --> Discharging : on setpoint update
Discharging --> Ready : if idle setpoint
Charging --> Terminating : on deauthorized
Discharging --> Terminating : on deauthorized
Ready --> Terminating : on deauthorized
Terminating --> Fault : on termination fault
Fault --> Unknown : on clear fault
Terminating --> Unknown : on end tx event
@enduml
"""
_fsm = AFSM(uml=transaction_manager_uml, context=TxManagerContext(), se_factory=lambda x: str(x))

_fsm.write_enums("TxManagerFSM")

from tx_manager_fsm_enums import TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent


TxManagerFSMType = AFSM[TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent, TxManagerContext]
