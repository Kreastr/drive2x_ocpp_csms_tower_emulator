"""
SPDX-License-Identifier: AGPL-3.0-or-later
Copyright (C) 2025 Lappeenrannan-Lahden teknillinen yliopisto LUT
Author: Aleksei Romanenko <aleksei.romanenko@lut.fi>


This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Funded by the European Union and UKRI. Views and opinions expressed are however those of the author(s)
only and do not necessarily reflect those of the European Union, CINEA or UKRI. Neither the European
Union nor the granting authority can be held responsible for them.
"""


import random
from typing import TYPE_CHECKING


import server.ocpp_server_handler
from afsm import AFSM
from server.data import UIManagerContext

from snoop import snoop
from dateutil.parser import parse as dtparse
from datetime import datetime, timedelta
import math

from server.callable_interface import CallableInterface
from tx_manager_fsm_enums import TxManagerFSMEvent, TxManagerFSMState

if TYPE_CHECKING:
    from server.ocpp_server_handler import OCPPServerHandler
else:
    OCPPServerHandler = object
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from tx_fsm_enums import TxFSMState

ui_manager_uml="""@startuml
[*] --> EVSEPage
EVSEPage --> SessionUnlock : if session is active
EVSEPage --> NewSession : if session is not active
SeesionUnlock --> EVSESelectPage : on exit
NewSession --> EVSESelectPage : on exit
NewSession --> EditBooking : on gdpr accept
GDPRAccepted --> EVSESelectPage : on exit
GDPRAccepted --> UserHasBooking : on have booking
GDPRAccepted --> EditBooking : if booking not supported
UserHasBooking --> GDPRAccepted : on back
UserHasBooking --> SessionConfirmed : on confirm session
SessionConfirmed --> GDPRAccepted : on back
UserHasBooking --> EditBooking : on edit booking
EditBooking --> NewSession : on back
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
CarConnected --> NormalSession : if session ready
SessionFirstStart --> NormalSession : if session ready
SessionFirstStart --> CarConnected : if timeout
SessionFirstStart --> NormalSession : on ready status
NormalSession --> EVSESelectPage : on exit
NormalSession --> SessionEndSummary : on early stop
NormalSession --> SessionEndSummary : if session fault
SessionEndSummary --> EVSESelectPage : on exit
@enduml
"""
_fsm = AFSM(uml=ui_manager_uml, context=UIManagerContext(), se_factory=lambda x: str(x))

_fsm.write_enum_module("UIManagerFSM")

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
        self.apply_to_all_conditions(UIManagerFSMCondition.if_timeout, self.if_timeout)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_session_ready, self.if_session_ready)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_booking_not_supported, self.if_booking_not_supported)

        self.on(UIManagerFSMState.session_first_start.on_enter, self.set_new_pin)
        self.on(UIManagerFSMState.session_first_start.on_enter, self.save_booking)
        self.on(UIManagerFSMState.session_first_start.on_enter, self.trigger_remote_start)
        self.on(UIManagerFSMState.normal_session.on_exit, self.clear_pin)
        self.on(UIManagerFSMState.normal_session.on_exit, self.trigger_remote_stop)

        self.tx_fsm.on(TxFSMState.transaction.on_enter, self.on_start_transaction)

    async def on_start_transaction(self):
        self.handle(UIManagerFSMEvent.on_ready_status)

    @property
    def tx_fsm(self) -> TxManagerFSMType:
        return self.context.tx_fsm

    @property
    def charge_point(self) -> OCPPServerHandler:
        cp : OCPPServerHandler | CallableInterface = self.context.charge_point
        if isinstance(cp, OCPPServerHandler):
            return cp
        raise f"Failed to check type of charge point interface. Expected OCPPServerHandler got {type(cp)}"


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
        await self.tx_fsm.handle(TxManagerFSMEvent.on_deauthorized)

    async def trigger_remote_start(self, *vargs, **kwargs):
        from server.ocpp_server_handler import OCPPServerHandler
        ctxt : UIManagerContext = self.context
        #self.charge_point.do_remote_start(evse_id=ctxt.evse.evse_id)
        if self.tx_fsm.current_state in [TxManagerFSMState.ready, TxManagerFSMState.charging, TxManagerFSMState.discharging]:
            self.handle_as_deferred(UIManagerFSMEvent.on_ready_status)
        else:
            await self.tx_fsm.handle(TxManagerFSMEvent.on_authorized)
            self.context.timeout_time = datetime.now() + timedelta(seconds=15)
        #ctxt.session_pin = random.randint(100000,999999)
        #ctxt.session_pins[ctxt.cp_evse_id] = ctxt.session_pin
        #ctxt.session_pins.redis.expire(ctxt.session_pins._format_key(ctxt.cp_evse_id), 100)

    
    async def set_new_pin(self, *vargs, **kwargs):
        ctxt : UIManagerContext = self.context
        ctxt.session_pin = random.randint(100000,999999)
        ctxt.session_pins[ctxt.cp_evse_id] = ctxt.session_pin
        server.ocpp_server_handler.redis.expire(ctxt.session_pins._format_key(ctxt.cp_evse_id), self.get_session_remaining_duration())

    async def save_booking(self, *vargs, **kwargs):
        ctxt : UIManagerContext = self.context
        self.tx_fsm.context.session_info.update(ctxt.session_info)
        
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
    def if_booking_not_supported(*vargs):
        return True
    
    @staticmethod
    def if_has_locking(*vargs):
        return False

    def if_has_no_locking(self, *vargs):
        return not self.if_has_locking(*vargs)

    def if_timeout(self, *vargs):
        return self.context.timeout_time < datetime.now()

    def if_session_ready(self, *vargs):
        return self.tx_fsm.current_state in [TxManagerFSMState.ready, TxManagerFSMState.charging, TxManagerFSMState.discharging, TxManagerFSMState.transition_triggered]

    def if_session_fault(self, *vargs):
        return self.tx_fsm.current_state not in [TxManagerFSMState.ready, TxManagerFSMState.charging, TxManagerFSMState.discharging, TxManagerFSMState.transition_triggered]

