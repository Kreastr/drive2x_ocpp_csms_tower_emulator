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


from _pydatetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from server.callable_interface import CallableInterface
from pydantic import BaseModel, Field

from server.data.evse_status import EvseStatus
from server.transaction_manager.tx_fsm import TxFSMServer
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from util.types import EVSEId, TransactionId, ChargePointId

from redis_dict import RedisDict

@dataclass
class ComponentData(BaseModel):
    variables : dict[str, dict[str, Any]] = Field(default_factory=dict)

@dataclass
class ChargePointContext:
    #current_tx : dict[EVSEId, TransactionId] = field(default_factory=dict)
    boot_notifications : list[Any] = field(default_factory=list)
    remote_ip = None
    online = False
    shutdown = False
    #tx_status = ""
    timeout : datetime = field(default_factory=datetime.now)
    id : ChargePointId = "provisional"


    transaction_fsms: defaultdict[EVSEId, TxManagerFSMType] = field(default_factory=lambda : defaultdict(TxFSMServer))

    connection_task : Any = None

    components : dict[str, ComponentData] = field(default_factory=lambda *vargs, **kwargs:
                                                        defaultdict(lambda : ComponentData.model_validate(dict(variables=dict()))))
    report_datetime : str = ""

@dataclass()
class UIManagerContext:
    cp_evse_id : str = ""
    charge_point : CallableInterface | None = None
    evse : EvseStatus | None = None
    tx_fsm : TxManagerFSMType | None = None
    session_pin : int = -1
    session_pins : RedisDict | None = None
    session_info : dict[str, Any] = field(default_factory=dict)
    timeout_time : datetime = field(default_factory=datetime.now)
