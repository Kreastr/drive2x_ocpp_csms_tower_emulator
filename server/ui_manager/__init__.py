import random
from typing import TYPE_CHECKING

from ocpp.v201 import ChargePoint

import server.ocpp_server_handler
from atfsm.atfsm import AFSM
from server.data import UIManagerContext

import snoop
from dateutil.parser import parse as dtparse
from datetime import datetime
import math

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
CarConnected --> SessionFirstStart : on start
SessionFirstStart --> NormalSession
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

        self.on(UIManagerFSMState.session_first_start.on_exit, self.set_new_pin)
        self.on(UIManagerFSMState.session_first_start.on_exit, self.trigger_remote_start)
        self.on(UIManagerFSMState.normal_session.on_exit, self.clear_pin)
        self.on(UIManagerFSMState.normal_session.on_exit, self.trigger_remote_stop)

    @snoop
    def load_from_redis(self):
        ctxt : UIManagerContext = self.context
        if ctxt.cp_evse_id in ctxt.session_pins:
            stored_val = ctxt.session_pins[ctxt.cp_evse_id]
            if stored_val != ctxt.session_pin:
                ctxt.session_pin = stored_val

    @snoop
    def get_session_remaining_duration(self):
        ts =  dtparse(self.context.session_info["departure_date"] + "T" + self.context.session_info["departure_time"])
        return int(math.ceil((ts-datetime.now()).total_seconds()))


    async def trigger_remote_stop(self, *vargs, **kwargs):
        if TYPE_CHECKING:
            from server.ocpp_server_handler import OCPPServerHandler
        ctxt : UIManagerContext = self.context
        cp : OCPPServerHandler | ChargePoint = ctxt.charge_point
        if isinstance(cp, OCPPServerHandler):
            cp.do_remote_stop(evse_id=ctxt.evse.evse_id)
            
    async def trigger_remote_start(self, *vargs, **kwargs):
        from server.ocpp_server_handler import OCPPServerHandler
        ctxt : UIManagerContext = self.context
        cp : OCPPServerHandler | ChargePoint = ctxt.charge_point
        if isinstance(cp, OCPPServerHandler):
            cp.do_remote_start(evse_id=ctxt.evse.evse_id)
        #ctxt.session_pin = random.randint(100000,999999)
        #ctxt.session_pins[ctxt.cp_evse_id] = ctxt.session_pin
        #ctxt.session_pins.redis.expire(ctxt.session_pins._format_key(ctxt.cp_evse_id), 100)
        
    async def set_new_pin(self, *vargs, **kwargs):
        ctxt : UIManagerContext = self.context
        ctxt.session_pin = random.randint(100000,999999)
        ctxt.session_pins[ctxt.cp_evse_id] = ctxt.session_pin
        server.ocpp_server_handler.redis.expire(ctxt.session_pins._format_key(ctxt.cp_evse_id), 100)

    async def clear_pin(self, *vargs, **kwargs):
        ctxt : UIManagerContext = self.context
        server.ocpp_server_handler.redis.expire(ctxt.session_pins._format_key(ctxt.cp_evse_id), 1)
        ctxt.session_pin = -1

    def if_session_is_active(self, *vargs):
        ctxt : UIManagerContext = self.context
        return ctxt.evse.connector_status == "Occupied" and ctxt.session_pin > 0

    def if_session_is_not_active(self, *vargs):
        return not self.if_session_is_active(*vargs)

    def if_car_present(self, *vargs):
        ctxt : UIManagerContext = self.context
        return ctxt.evse.connector_status == "Occupied"

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

