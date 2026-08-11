from enum import Enum
from afsm.state_base import StateBase

class ProxyConnectionFSMState(StateBase, str, Enum):
    new='new'
    start_up='start_up'
    autonomous_loop='autonomous_loop'
    connecting='connecting'
    client_disconnected='client_disconnected'
    connected='connected'
    shutting_down='shutting_down'
    server_disconnected='server_disconnected'
    finalizing='finalizing'

class ProxyConnectionFSMCondition(str, Enum):
    if_start_up_delay_done='if_start_up_delay_done'
    if_server_connected='if_server_connected'
    if_client_disconnected='if_client_disconnected'
    if_downstream_heartbeat_timeout='if_downstream_heartbeat_timeout'
    if_server_disconnected='if_server_disconnected'


class ProxyConnectionFSMEvent(str, Enum):
    on_downstream_heartbeat='on_downstream_heartbeat'
    on_termination_request='on_termination_request'
    on_upstream_accepted_boot_notification='on_upstream_accepted_boot_notification'
