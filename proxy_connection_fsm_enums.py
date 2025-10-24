from enum import Enum
from afsm.state_base import StateBase

class ProxyConnectionFSMState(StateBase, str, Enum):
    new='new'
    connected='connected'
    timed_out='timed_out'
    serial_polled='serial_polled'
    server_disconnected='server_disconnected'
    client_disconnected='client_disconnected'
    shutting_down='shutting_down'
    finalizing='finalizing'

class ProxyConnectionFSMCondition(str, Enum):
    if_new_state_timeout='if_new_state_timeout'
    if_heartbeat_timeout='if_heartbeat_timeout'


class ProxyConnectionFSMEvent(str, Enum):
    on_state_changed = 'on_state_changed'
    on_client_boot_notification_forwarded='on_client_boot_notification_forwarded'
    on_client_disconnect='on_client_disconnect'
    on_server_disconnect='on_server_disconnect'
    on_termination_request='on_termination_request'
    on_heartbeat='on_heartbeat'
    on_serial_response_validated='on_serial_response_validated'
    on_serial_validation_failed='on_serial_validation_failed'
    on_finalized='on_finalized'
