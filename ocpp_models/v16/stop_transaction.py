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

from ocpp.v16.enums import Reason, ReadingContext, ValueFormat, Measurand, Phase, Location, UnitOfMeasure
from pydantic import BaseModel, StringConstraints

from ocpp_models.v16.base_types import CiString25Type, CiString20Type, CiString50Type

class SampledValue(BaseModel):
    value : str
    context : Optional[ReadingContext] = None
    format : Optional[ValueFormat] = None
    measurand : Optional[Measurand] = None
    phase : Optional[Phase] = None
    location : Optional[Location] = None
    unit : Optional[UnitOfMeasure] = None

class MeterValue(BaseModel):
    timestamp : datetime.datetime
    sampledValue : list[SampledValue]

class StopTransactionRequest(BaseModel):
    idTag : Optional[str]
    meterStop : int
    timestamp : datetime.datetime
    transactionId: int
    reason : Optional[Reason]
    transactionData : Optional[list[MeterValue]]