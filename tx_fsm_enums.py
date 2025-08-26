from enum import Enum
from state_base import StateBase

class TxFSMState(StateBase, str, Enum):
    idle='idle'
    authorized='authorized'
    reject_authorization='reject_authorization'
    cable_connected='cable_connected'
    transaction='transaction'

class TxFSMCondition(str, Enum):
    if_cable_connected='if_cable_connected'
    if_cable_disconnected='if_cable_disconnected'


class TxFSMEvent(str, Enum):
    on_authorized='on_authorized'
    on_deauthorized='on_deauthorized'
    on_every_report_interval='on_every_report_interval'
