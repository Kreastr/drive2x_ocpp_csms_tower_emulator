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
[*] -> New
New --> Connected : on client boot notification forwarded
New --> TimedOut : if new state timeout
TimedOut --> SerialPolled : on serial response validated
TimedOut --> ServerDisconnected : on serial validation failed
TimedOut --> Connected : on client boot notification forwarded
SerialPolled --> Connected : on heartbeat
SerialPolled --> ServerDisconnected : if heartbeat timeout
Connected --> ClientDisconnected : on client disconnect
Connected --> ServerDisconnected : on server disconnect
Connected --> ShuttingDown : on termination request
Connected --> ShuttingDown : if heartbeat timeout
Connected --> Connected : on heartbeat
ShuttingDown --> ServerDisconnected : on server disconnect
ClientDisconnected --> Finalizing : on server disconnect
ServerDisconnected --> Finalizing : on client disconnect
Finalizing --> [*] : on finalized
@enduml
"""
_fsm = AFSM(uml=proxy_connection_uml, context=ProxyConnectionContext(), se_factory=lambda x: str(x))

_fsm.write_enum_module("ProxyConnectionFSM")

from proxy_connection_fsm_enums import ProxyConnectionFSMState, ProxyConnectionFSMCondition, ProxyConnectionFSMEvent


ProxyConnectionFSMType = AFSM[ProxyConnectionFSMState, ProxyConnectionFSMCondition, ProxyConnectionFSMEvent, ProxyConnectionContext]
