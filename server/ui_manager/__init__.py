from atfsm.atfsm import AFSM
from server.data import UIManagerContext

ui_manager_uml="""@startuml
[*] --> EVSEPage
EVSEPage --> SessionUnlock : if session is active
EVSEPage --> NewSession : if session is not active
SeesionUnlock --> EVSESelectPage : on exit
NewSession --> EVSESelectPage : on exit
NewSession --> GDPRAccepted : on gdpr accept
GDPRAccepted --> EVSESelectPage : on exit
GDPRAccepted --> UserHasBooking : on have booking
UserHasBooking --> GDPRAccepted : on back
UserHasBooking --> SessionConfirmed : on confirm session
SessionConfirmed --> GDPRAccepted : on back
UserHasBooking --> EditBooking : on edit booking
EditBooking --> GDPRAccepted : on back
GDPRAccepted --> EditBooking : on continue without booking
EditBooking --> SessionConfirmed : on confirm session
SessionConfirmed --> CarNotConnected : on start session
CarNotConnected --> EVSESelectPage : on exit
CarNotConnected --> CarConnected : if car present
CarConnected --> CarNotConnected : if car not present
CarConnected --> CanLock : if has locking
CarConnected --> EVSESelectPage : on exit
CanLock --> CarNotConnected : if car not present
CanLock --> CarLockedSession : on lock and start
CanLock --> EVSESelectPage : on exit
CarLockedSession --> EVSESelectPage : on exit
SessionUnlock --> Unlocking : on session pin correct
SeesionUnlock --> SessionEndSummary : on session expired
Unlocking --> CarLockedSession : if has locking
Unlocking --> NormalSession : if has no locking
CarLockedSession --> SessionEndSummary : on early stop and unlock
CarLockedSession --> SessionEndSummary : if session fault
CarConnected --> NormalSession : on start
NormalSession --> EVSESelectPage : on exit
NormalSession --> SessionEndSummary : on early stop
NormalSession --> SessionEndSummary : if session fault
SessionEndSummary --> EVSESelectPage : on exit
@enduml
"""
_fsm = AFSM(uml=ui_manager_uml, context=UIManagerContext(), se_factory=lambda x: str(x))

_fsm.write_enums("UIManagerFSM")

from uimanager_fsm_enums import UIManagerFSMState, UIManagerFSMCondition, UIManagerFSMEvent


class UIManagerFSMType(AFSM[UIManagerFSMState, UIManagerFSMCondition, UIManagerFSMEvent, UIManagerContext]):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)

        self.apply_to_all_conditions(UIManagerFSMCondition.if_session_is_active, self.if_session_is_active)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_session_is_not_active, self.if_session_is_not_active)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_car_present, self.if_car_present)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_car_not_present, self.if_car_not_present)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_has_locking, self.if_has_locking)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_has_no_locking, self.if_has_no_locking)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_session_fault, self.if_session_fault)

    @staticmethod
    def if_session_is_active(*vargs):
        return False

    def if_session_is_not_active(self, *vargs):
        return not self.if_session_is_active(*vargs)

    @staticmethod
    def if_car_present(*vargs):
        return False

    def if_car_not_present(self, *vargs):
        return not self.if_car_present(*vargs)

    @staticmethod
    def if_has_locking(*vargs):
        return False

    def if_has_no_locking(self, *vargs):
        return not self.if_has_locking(*vargs)

    @staticmethod
    def if_session_fault(*vargs):
        return False

