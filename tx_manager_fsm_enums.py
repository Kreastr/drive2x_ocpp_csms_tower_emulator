from enum import Enum
from afsm.state_base import StateBase

class TxManagerFSMState(StateBase, str, Enum):
    unknown='unknown'
    occupied='occupied'
    available='available'
    authorizing='authorizing'
    authorized='authorized'
    upkeep='upkeep'
    ready='ready'
    transition_triggered='transition_triggered'
    charging='charging'
    discharging='discharging'
    terminating='terminating'
    fault='fault'

class TxManagerFSMCondition(str, Enum):
    if_occupied='if_occupied'
    if_available='if_available'
    if_charge_setpoint='if_charge_setpoint'
    if_discharge_setpoint='if_discharge_setpoint'
    if_idle_setpoint='if_idle_setpoint'


class TxManagerFSMEvent(str, Enum):
    on_state_changed = 'on_state_changed'
    on_authorize_accept='on_authorize_accept'
    on_tx_update_event='on_tx_update_event'
    on_authorized_by_app='on_authorized_by_app'
    on_authorize_reject='on_authorize_reject'
    on_start_tx_event='on_start_tx_event'
    on_deauthorized='on_deauthorized'
    on_setpoint_apply_mark='on_setpoint_apply_mark'
    on_end_tx_event='on_end_tx_event'
    on_termination_fault='on_termination_fault'
    on_clear_fault='on_clear_fault'
