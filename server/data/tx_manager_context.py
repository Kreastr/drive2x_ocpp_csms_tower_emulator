from dataclasses import field, dataclass

from server.data.connector_status import ConnectorStatus


@dataclass 
class TxManagerContext:
    connector : ConnectorStatus = field(default_factory=ConnectorStatus)