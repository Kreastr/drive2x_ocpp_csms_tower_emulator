from dataclasses import field, dataclass

from server.callable_interface import CallableInterface

from server.data.evse_status import EvseStatus
from util.types import TransactionId


@dataclass 
class TxManagerContext:
    evse : EvseStatus = field(default_factory=EvseStatus)
    tx_id : TransactionId | None = None
    cp_interface : CallableInterface | None = None