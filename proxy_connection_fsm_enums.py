from enum import Enum
from afsm.state_base import StateBase

class ProxyConnectionFSMState(StateBase, str, Enum):
    new='new'
    start_up='start_up'
    autonomous_loop='autonomous_loop'
    connecting='connecting'
    shutting_down='shutting_down'
    client_disconnected='client_disconnected'
    connected='connected'
    shut_down_server_disconnected='shut_down_server_disconnected'
    finalizing='finalizing'
    server_disconnected='server_disconnected'

class ProxyConnectionFSMCondition(str, Enum):
    if_start_up_delay_done='if_start_up_delay_done'
    if_server_connected='if_server_connected'
    if_termination_requested='if_termination_requested'
    if_client_disconnected='if_client_disconnected'
    if_downstream_heartbeat_timeout='if_downstream_heartbeat_timeout'
    if_server_disconnected='if_server_disconnected'


class ProxyConnectionFSMEvent(str, Enum):
    on_downstream_heartbeat='on_downstream_heartbeat'
    on_upstream_accepted_boot_notification='on_upstream_accepted_boot_notification'
