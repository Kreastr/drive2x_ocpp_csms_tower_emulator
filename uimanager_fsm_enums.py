from enum import Enum
from afsm.state_base import StateBase

class UIManagerFSMState(StateBase, str, Enum):
    evsepage='evsepage'
    enter_booking_pin='enter_booking_pin'
    new_session='new_session'
    evseselect_page='evseselect_page'
    booking_pincorrect='booking_pincorrect'
    booking_details='booking_details'
    normal_session='normal_session'
    booking_pinincorrect='booking_pinincorrect'
    car_not_connected='car_not_connected'
    car_connected='car_connected'
    session_end_summary='session_end_summary'
    car_connected_too_soon='car_connected_too_soon'

class UIManagerFSMCondition(str, Enum):
    if_session_is_ready='if_session_is_ready'
    if_session_is_not_ready='if_session_is_not_ready'
    if_car_present='if_car_present'
    if_car_not_present='if_car_not_present'
    if_session_fault='if_session_fault'


class UIManagerFSMEvent(str, Enum):
    on_state_changed = 'on_state_changed'
    on_exit='on_exit'
    on_correct_pin='on_correct_pin'
    on_incorrect_pin='on_incorrect_pin'
    on_gdpr_accept='on_gdpr_accept'
    on_confirm_session='on_confirm_session'
    on_early_stop='on_early_stop'
    on_back='on_back'
