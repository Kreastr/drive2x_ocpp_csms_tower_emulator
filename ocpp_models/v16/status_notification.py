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
from typing import Annotated, Optional

from ocpp.v16.enums import ChargePointErrorCode, ChargePointStatus
from pydantic import BaseModel, StringConstraints

from ocpp_models.v16.base_types import CiString25Type, CiString20Type, CiString50Type


class StatusNotificationRequest(BaseModel):
    connectorId : int
    errorCode : ChargePointErrorCode
    info : Optional[CiString50Type] = None
    status : ChargePointStatus
    timestamp : Optional[datetime.datetime] = None
    vendorId : Optional[CiString25Type] = None
    vendorErrorCode : Optional[CiString50Type] = None
    