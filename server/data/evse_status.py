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


from datetime import datetime

from attr.filters import exclude
from nicegui import binding
from ocpp.v201 import ChargePoint

from util.types import ConnectorId, EVSEId, TransactionId
from pydantic import BaseModel, field_serializer, ConfigDict, Field


class EvseStatus(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    connector_id : ConnectorId = 0
    connector_status : str = "Unknown"
    timestamp : str = "1970.01.01"
    evse_id : EVSEId = -1
    tx_id : TransactionId = ""
    cp_interface : ChargePoint | None = Field(default=None, exclude=True)
    setpoint : float = 0.0
    next_setpoint : float = 0.0
    last_cycle_soc_percent : float | None = None
    last_report_soc_percent : float | None = None
    last_report_time : datetime | None = None
    last_reported_power : float = 0.0

