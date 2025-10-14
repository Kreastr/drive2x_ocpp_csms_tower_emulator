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