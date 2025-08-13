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

_fsm.write_enum_module("TxFSM")

from tx_fsm_enums import TxFSMState, TxFSMCondition, TxFSMEvent

TxFSMType = AFSM[TxFSMState, TxFSMCondition, TxFSMEvent, TxFSMContext]
