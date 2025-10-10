from enum import Enum
from afsm.state_base import StateBase

class testfsmState(StateBase, str, Enum):
    state_1='state_1'
    state_2='state_2'
    state_3='state_3'
    state_4='state_4'

class testfsmCondition(str, Enum):
    if_aborted='if_aborted'


class testfsmEvent(str, Enum):
    on_succeeded='on_succeeded'
    on_aborted_2='on_aborted_2'
    on_failed='on_failed'
    on_succeeded_save_result='on_succeeded_save_result'
    on_aborted='on_aborted'
