from dataclasses import field, dataclass

from server.data.evse_status import EvseStatus


@dataclass 
class TxManagerContext:
    evse : EvseStatus = field(default_factory=EvseStatus)
    tx_id : str | None = None