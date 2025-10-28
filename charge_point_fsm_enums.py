from enum import Enum
from afsm.state_base import StateBase

class ChargePointFSMState(StateBase, str, Enum):
    created='created'
    unknown='unknown'
    identified='identified'
    rejected='rejected'
    booted='booted'
    failing='failing'
    failed='failed'
    force_booted='force_booted'
    running_transaction='running_transaction'
    closing='closing'

class ChargePointFSMCondition(str, Enum):
    if_no_active_transactions='if_no_active_transactions'


class ChargePointFSMEvent(str, Enum):
    on_state_changed = 'on_state_changed'
    on_start='on_start'
    on_serial_number_obtained='on_serial_number_obtained'
    on_serial_number_not_obtained='on_serial_number_not_obtained'
    on_boot_notification='on_boot_notification'
    on_cached_boot_notification='on_cached_boot_notification'
    on_boot_timeout='on_boot_timeout'
    on_transaction_manager_request='on_transaction_manager_request'
    on_reboot_confirmed='on_reboot_confirmed'
    on_reset_accepted='on_reset_accepted'
    on_reset_rejected='on_reset_rejected'
