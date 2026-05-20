from datetime import timedelta

from pydantic import BaseModel
from datetime import datetime as dt

class BookingDetails(BaseModel):
    arrival_time : dt
    original_departure_time : dt
    departure_time : dt
    session_duration : timedelta
