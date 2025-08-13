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
from server.charge_point_model.charge_point_uml import charge_point_uml
from server.data import ChargePointContext
from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType, transaction_manager_uml
from tx_manager_fsm_enums import TxManagerFSMState

_fsm = AFSM(uml=charge_point_uml, context=ChargePointContext(), se_factory=lambda x: str(x))
_fsm.write_enum_module("ChargePointFSM")

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