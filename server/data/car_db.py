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
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

class CarMake(StrEnum):
    D2X_CARS = "D2X Cars"

class CarModel(StrEnum):
    D2X_VEV_2025 = "D2X Virtual EV (2025-)"

class CarDetails(BaseModel):
    usable_battery_capacity_kwh : float

CAR_DB = {CarMake.D2X_CARS: {CarModel.D2X_VEV_2025 : CarDetails.model_validate({"usable_battery_capacity_kwh": 70.0})}}

class SessionInfo(BaseModel):
    car_make : CarMake = "D2X Cars"
    car_model : CarModel = "D2X Virtual EV (2025-)"
    departure_date : str = Field(default_factory=lambda :datetime.now(tz=timezone.utc).isoformat()[:10],)
    departure_time : str = "23:59"