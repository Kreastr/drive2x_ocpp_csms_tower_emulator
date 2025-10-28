from typing import Optional

from ocpp.v201.enums import ResetEnumType
from pydantic import BaseModel


class ResetRequest(BaseModel):
    type : ResetEnumType
    evseId : Optional[int] = None
