from enum import Enum
from afsm.state_base import StateBase

class ProxyConnectionFSMState(StateBase, str, Enum):
    new='new'
    autonomous_loop='autonomous_loop'
    server_disconnected='server_disconnected'
    connected='connected'
    client_disconnected='client_disconnected'
    shutting_down='shutting_down'
    finalizing='finalizing'

class ProxyConnectionFSMCondition(str, Enum):
    if_heartbeat_timeout='if_heartbeat_timeout'
    if_client_disconnected='if_client_disconnected'
    if_server_disconnected='if_server_disconnected'


class ProxyConnectionFSMEvent(str, Enum):
    on_heartbeat='on_heartbeat'
    on_server_connected='on_server_connected'
    on_termination_request='on_termination_request'
