from _pydatetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from server.data.evse_status import EvseStatus
from server.transaction_manager.tx_fsm import TxFSMS
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from util.types import EVSEId, TransactionId, ChargePointId


@dataclass
class ChargePointContext:
    #current_tx : dict[EVSEId, TransactionId] = field(default_factory=dict)
    boot_notifications : list[Any] = field(default_factory=list)
    remote_ip = None
    online = False
    shutdown = False
    #tx_status = ""
    timeout : datetime = field(default_factory=datetime.now)
    id : ChargePointId = "provisional"


    transaction_fsms: defaultdict[EVSEId, TxManagerFSMType] = field(default_factory=lambda : defaultdict(TxFSMS))

    connection_task : Any = None
