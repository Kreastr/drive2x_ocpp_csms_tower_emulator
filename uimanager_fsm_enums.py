from enum import Enum
from atfsm.state_base import StateBase

class UIManagerFSMState(StateBase, str, Enum):
    evsepage='evsepage'
    session_unlock='session_unlock'
    new_session='new_session'
    seesion_unlock='seesion_unlock'
    evseselect_page='evseselect_page'
    gdpraccepted='gdpraccepted'
    user_has_booking='user_has_booking'
    session_confirmed='session_confirmed'
    edit_booking='edit_booking'
    car_not_connected='car_not_connected'
    car_connected='car_connected'
    can_lock='can_lock'
    car_locked_session='car_locked_session'
    unlocking='unlocking'
    session_end_summary='session_end_summary'
    normal_session='normal_session'
    session_first_start='session_first_start'

class UIManagerFSMCondition(str, Enum):
    if_session_is_active='if_session_is_active'
    if_session_is_not_active='if_session_is_not_active'
    if_car_present='if_car_present'
    if_car_not_present='if_car_not_present'
    if_has_locking='if_has_locking'
    if_session_fault='if_session_fault'
    if_has_no_locking='if_has_no_locking'


class UIManagerFSMEvent(str, Enum):
    on_state_changed = 'on_state_changed'
    on_session_pin_correct='on_session_pin_correct'
    on_exit='on_exit'
    on_gdpr_accept='on_gdpr_accept'
    on_session_expired='on_session_expired'
    on_have_booking='on_have_booking'
    on_continue_without_booking='on_continue_without_booking'
    on_back='on_back'
    on_confirm_session='on_confirm_session'
    on_edit_booking='on_edit_booking'
    on_start_session='on_start_session'
    on_start='on_start'
    on_lock_and_start='on_lock_and_start'
    on_early_stop_and_unlock='on_early_stop_and_unlock'
    on_early_stop='on_early_stop'
