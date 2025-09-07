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


UIManagerFSMType = AFSM[UIManagerFSMState, UIManagerFSMCondition, UIManagerFSMEvent, UIManagerContext]
