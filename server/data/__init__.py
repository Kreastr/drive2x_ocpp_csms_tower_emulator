from _pydatetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from server.callable_interface import CallableInterface
from pydantic import BaseModel, Field

from server.data.evse_status import EvseStatus
from server.transaction_manager.tx_fsm import TxFSMS
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from util.types import EVSEId, TransactionId, ChargePointId

from redis_dict import RedisDict

@dataclass
class ComponentData(BaseModel):
    variables : dict[str, dict[str, Any]] = Field(default_factory=dict)

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

    components : dict[str, ComponentData] = field(default_factory=lambda *vargs, **kwargs:
                                                        defaultdict(lambda : ComponentData.model_validate(dict(variables=dict()))))
    report_datetime : str = ""

@dataclass()
class UIManagerContext:
    cp_evse_id : str = ""
    charge_point : CallableInterface | None = None
    evse : EvseStatus | None = None
    tx_fsm : TxManagerFSMType | None = None
    session_pin : int = -1
    session_pins : RedisDict | None = None
    session_info : dict[str, Any] = field(default_factory=dict)
    timeout_time : datetime = field(default_factory=datetime.now)
