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

