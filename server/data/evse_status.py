from nicegui import binding
from ocpp.v201 import ChargePoint

from util.types import ConnectorId, EVSEId, TransactionId


@binding.bindable_dataclass
class EvseStatus:
    connector_id : ConnectorId = 0
    connector_status : str = "Unknown"
    timestamp : str = "1970.01.01"
    evse_id : EVSEId = -1
    tx_id = TransactionId
    cp_interface : ChargePoint | None = None
    setpoint : float = 0.0
