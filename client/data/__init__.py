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

import datetime
from dataclasses import dataclass
from typing import Any

from ocpp.v201 import ChargePoint
from pydantic import BaseModel, Field

from util.types import TransactionId, ConnectorId, EVSEId


class EvseModel(BaseModel):
    id : EVSEId
    connector_id : ConnectorId = 1
    auth : bool = False
    cable_connected : bool = False
    soc_wh : float = 50000.0
    usable_capacity : float = 70000.0
    km_driven : float = 0.0
    metered_power : float = 0.0
    metered_power_charge : float = 0.0
    metered_power_discharge : float = 0.0
    setpoint : float = 0.0
    last_meter_update : datetime.datetime = Field(default_factory=datetime.datetime.now)
    tx_id : TransactionId | None = None
    


@dataclass
class TxFSMContext:
    evse : EvseModel
    auth_status : Any = None
    remote_start_id : int = -1
    cp_interface : ChargePoint | None = None
