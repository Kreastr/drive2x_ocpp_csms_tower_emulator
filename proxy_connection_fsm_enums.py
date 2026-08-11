from enum import Enum
from afsm.state_base import StateBase

class ProxyConnectionFSMState(StateBase, str, Enum):
    new='new'
    start_up='start_up'
    autonomous_loop='autonomous_loop'
    connected='connected'
    client_disconnected='client_disconnected'
    shutting_down='shutting_down'
    server_disconnected='server_disconnected'
    finalizing='finalizing'

class ProxyConnectionFSMCondition(str, Enum):
    if_start_up_delay_done='if_start_up_delay_done'
    if_server_connected='if_server_connected'
    if_client_disconnected='if_client_disconnected'
    if_server_disconnected='if_server_disconnected'
    if_heartbeat_timeout='if_heartbeat_timeout'


class ProxyConnectionFSMEvent(str, Enum):
    on_heartbeat='on_heartbeat'
    on_termination_request='on_termination_request'
