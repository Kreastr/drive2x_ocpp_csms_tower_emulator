import datetime
from typing import Optional

from .base_types import CiString50Type, CiString255Type
from pydantic import BaseModel

class SecurityEventNotification(BaseModel):
    type : CiString50Type
    timestamp : datetime.datetime
    techInfo : Optional[CiString255Type]
