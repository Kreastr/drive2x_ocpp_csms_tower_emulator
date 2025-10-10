from enum import Enum
from afsm.state_base import StateBase

class TxFSMState(StateBase, str, Enum):
    idle='idle'
    authorized='authorized'
    cable_connected='cable_connected'
    transaction_auth_first='transaction_auth_first'
    transaction_cable_first='transaction_cable_first'
    transaction='transaction'
    stop_transaction_disconnected='stop_transaction_disconnected'
    stop_transaction_deauthorized='stop_transaction_deauthorized'

class TxFSMCondition(str, Enum):
    if_cable_connected='if_cable_connected'
    if_cable_disconnected='if_cable_disconnected'


class TxFSMEvent(str, Enum):
    on_state_changed = 'on_state_changed'
    on_authorized='on_authorized'
    on_deauthorized='on_deauthorized'
    on_report_interval='on_report_interval'
