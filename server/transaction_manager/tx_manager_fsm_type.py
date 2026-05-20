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


from afsm import AFSM
from server.data.tx_manager_context import TxManagerContext

transaction_manager_uml = """@startuml
[*] -> Unknown
Unknown --> Occupied : if occupied
Available --> Occupied : if occupied
Unknown --> Available : if available
Occupied --> Available : if available
Available --> Authorizing : on authorized by app
Authorizing --> Authorized : on authorize accept
Authorizing --> Unknown : on authorize reject
Authorizing --> Unknown : on deauthorized
Occupied --> Upkeep : on authorize accept
Occupied --> Upkeep : on tx update event
Occupied --> Upkeep : on soc info updated event
Upkeep --> Ready : on authorized by app
Upkeep --> Terminating : on deauthorized
Authorized --> Ready : if occupied
Authorized --> Unknown : on deauthorized
Upkeep --> Available : if available
Ready --> Terminating : on deauthorized
Ready --> Unknown : on end tx event
Ready --> Terminating : on termination fault
Terminating --> Fault : on termination fault
Terminating --> Unknown : on end tx event
Fault --> Unknown : on clear fault
Fault --> Available : if available
@enduml
"""
_fsm = AFSM(uml=transaction_manager_uml, context=TxManagerContext(), se_factory=lambda x: str(x))

_fsm.write_enum_module("TxManagerFSM")

from tx_manager_fsm_enums import TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent


TxManagerFSMType = AFSM[TxManagerFSMState, TxManagerFSMCondition, TxManagerFSMEvent, TxManagerContext]
