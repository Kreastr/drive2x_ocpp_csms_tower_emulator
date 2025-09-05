from dataclasses import field, dataclass

from ocpp.v201 import ChargePoint

from server.data.evse_status import EvseStatus
from util.types import TransactionId


@dataclass 
class TxManagerContext:
    evse : EvseStatus = field(default_factory=EvseStatus)
    tx_id : TransactionId | None = None
    cp_interface : ChargePoint | None = None