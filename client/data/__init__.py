import datetime
from dataclasses import dataclass
from typing import Any

from ocpp.v201 import ChargePoint
from pydantic import BaseModel, Field

from util.types import TransactionId, ConnectorId, EVSEId


class EvseModel(BaseModel):
    id : EVSEId
    connector_id : ConnectorId = 1
    auth : bool = False
    cable_connected : bool = False
    soc_wh : float = 50000.0
    usable_capacity : float = 70000.0
    km_driven : float = 0.0
    metered_power : float = 0.0
    setpoint : float = 0.0
    last_meter_update : datetime.datetime = Field(default_factory=datetime.datetime.now)
    tx_id : TransactionId | None = None
    


@dataclass
class TxFSMContext:
    evse : EvseModel
    auth_status : Any = None
    remote_start_id : int = -1
    cp_interface : ChargePoint | None = None
