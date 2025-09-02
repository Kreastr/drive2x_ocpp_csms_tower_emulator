from nicegui import binding
from ocpp.v201 import ChargePoint


@binding.bindable_dataclass
class ConnectorStatus:
    connector_id : int = 0
    connector_status : str = "Unknown"
    timestamp : str = "1970.01.01"
    evse_id : int = -1
    tx_id = str
    cp_interface : ChargePoint | None = None
    setpoint : float = 0.0
