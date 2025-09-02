from dataclasses import dataclass
from typing import Any

from ocpp.v201 import ChargePoint


@dataclass
class ConnectorModel:
    id : int
    auth : bool = False
    cable_connected : bool = False
    soc_wh : float = 50000.0
    usable_capacity : float = 70000.0
    
    @property
    def evse_id(self):
        return self.id


@dataclass
class TxFSMContext:
    connector : ConnectorModel
    auth_status : Any = None
    remote_id : int = -1
    cp_interface : ChargePoint | None = None
