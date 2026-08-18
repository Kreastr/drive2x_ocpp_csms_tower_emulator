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

from proxy.proxy_connection_context import ProxyConnectionContext
from server.data.tx_manager_context import TxManagerContext

proxy_connection_uml = """@startuml
[*] --> New
New --> StartUp
StartUp --> AutonomousLoop : if start up delay done
AutonomousLoop --> AutonomousLoop : on downstream heartbeat
AutonomousLoop --> Connecting : if server connected
AutonomousLoop --> ShuttingDown : if termination requested
AutonomousLoop --> ClientDisconnected : if client disconnected
Connecting --> Connecting : on downstream heartbeat
Connecting --> Connected : on upstream accepted boot notification
Connecting --> ClientDisconnected : if client disconnected
Connecting --> ShuttingDown : if termination requested
Connecting --> AutonomousLoop : if downstream heartbeat timeout
Connected --> ClientDisconnected : if client disconnected
Connected --> AutonomousLoop : if server disconnected
Connected --> ShuttingDown : if termination requested
Connected --> ClientDisconnected : if downstream heartbeat timeout
Connected --> Connected : on downstream heartbeat
ShuttingDown --> ShutDownServerDisconnected : if server disconnected
ShutDownServerDisconnected --> Finalizing : if client disconnected
ClientDisconnected --> Finalizing : if server disconnected
ServerDisconnected --> Finalizing : if client disconnected
Finalizing --> [*]
@enduml
"""
_fsm = AFSM(uml=proxy_connection_uml, context=ProxyConnectionContext(), se_factory=lambda x: str(x))

_fsm.write_enum_module("ProxyConnectionFSM")

from proxy_connection_fsm_enums import ProxyConnectionFSMState, ProxyConnectionFSMCondition, ProxyConnectionFSMEvent


ProxyConnectionFSMType = AFSM[ProxyConnectionFSMState, ProxyConnectionFSMCondition, ProxyConnectionFSMEvent, ProxyConnectionContext]
