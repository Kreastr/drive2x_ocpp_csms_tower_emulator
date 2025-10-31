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

from pydantic import BaseModel, StringConstraints
from typing import Annotated, Optional

CiString20Type = Annotated[str, StringConstraints(max_length=20)]
CiString25Type = Annotated[str, StringConstraints(max_length=25)]
CiString36Type = Annotated[str, StringConstraints(max_length=36)]
CiString50Type = Annotated[str, StringConstraints(max_length=50)]
CiString255Type = Annotated[str, StringConstraints(max_length=255)]
CiString500Type = Annotated[str, StringConstraints(max_length=500)]
CiString1000Type = Annotated[str, StringConstraints(max_length=1000)]


class EVSEType(BaseModel):
    id : int
    connectorId : Optional[int] = None

class ComponentType(BaseModel):
    name : CiString50Type
    instance : Optional[CiString50Type] = None
    evse : Optional[EVSEType] = None

class VariableType(BaseModel):
    name : CiString50Type
    instance : Optional[CiString50Type] = None
