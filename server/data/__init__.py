from _pydatetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


from server.transaction_manager.tx_fsm import TxFSMS
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType



@dataclass
class ChargePointContext:
    transactions : set[Any] = field(default_factory=set)
    current_tx : dict[int, str] = field(default_factory=dict)
    boot_notifications : list[Any] = field(default_factory=list)
    remote_ip = None
    online = False
    shutdown = False
    connectors : dict[int, Any] = field(default_factory=dict)
    tx_status = ""
    timeout : datetime = field(default_factory=datetime.now)
    id : str = "provisional"


    transaction_fsms: defaultdict[int, TxManagerFSMType] = field(default_factory=lambda : defaultdict(TxFSMS))

    connection_task : Any = None
