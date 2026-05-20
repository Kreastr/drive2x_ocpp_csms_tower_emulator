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
import logging
import random
from typing import TYPE_CHECKING


import server.ocpp_server_handler
from afsm import AFSM
from server.data import UIManagerContext, BookingDetails

import sys

if "--trace" in sys.argv:
    from snoop import snoop
else:
    snoop = lambda x: x

from dateutil.parser import parse as dtparse
from datetime import datetime, timedelta
import math

from server.callable_interface import CallableInterface
from tx_manager_fsm_enums import TxManagerFSMEvent, TxManagerFSMState
from util.db import get_default_redis

if TYPE_CHECKING:
    from server.ocpp_server_handler import OCPPServerHandler
else:
    OCPPServerHandler = object
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from tx_fsm_enums import TxFSMState

ui_manager_uml="""@startuml
[*] --> EVSEPage
EVSEPage --> EnterBookingPIN : if session is ready
EVSEPage --> NewSession : if session is not ready

NewSession --> EVSESelectPage : on exit
NewSession --> EnterBookingPIN : on gdpr accept
EnterBookingPIN --> EVSESelectPage : on exit
EnterBookingPIN --> BookingPINCorrect : on correct pin
BookingPINCorrect --> BookingDetails : if session is not ready
BookingPINCorrect --> NormalSession : if session is ready
EnterBookingPIN --> BookingPINIncorrect : on incorrect pin
BookingPINIncorrect --> EnterBookingPIN : on back

BookingDetails --> CarNotConnected : on confirm session 
BookingDetails --> EVSESelectPage : on exit

CarNotConnected --> EVSESelectPage : on exit
CarNotConnected --> CarConnected : if car present
CarConnected --> CarNotConnected : if car not present
CarConnected --> EVSESelectPage : on exit

CarConnected --> NormalSession : if session is ready
NormalSession --> EVSESelectPage : on exit
NormalSession --> SessionEndSummary : if car not present
NormalSession --> SessionEndSummary : if session is not ready
NormalSession --> SessionEndSummary : on early stop
NormalSession --> SessionEndSummary : if session fault
SessionEndSummary --> EVSESelectPage : on exit

NewSession --> CarConnectedTooSoon : if car present but session is not running
EnterBookingPIN --> CarConnectedTooSoon : if car present but session is not running
BookingPINCorrect --> CarConnectedTooSoon : if car present but session is not running
BookingPINIncorrect --> CarConnectedTooSoon : if car present but session is not running
BookingDetails --> CarConnectedTooSoon : if car present but session is not running
BookingDetails --> CarConnectedTooSoon : if car present but session is not running

CarConnectedTooSoon --> EVSEPage : if car not present

@enduml
"""
_fsm = AFSM(uml=ui_manager_uml, context=UIManagerContext(), se_factory=lambda x: str(x))

_fsm.write_enum_module("UIManagerFSM")

from uimanager_fsm_enums import UIManagerFSMState, UIManagerFSMCondition, UIManagerFSMEvent



class UIManagerFSMType(AFSM[UIManagerFSMState, UIManagerFSMCondition, UIManagerFSMEvent, UIManagerContext]):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)

        self.apply_to_all_conditions(UIManagerFSMCondition.if_car_present, self.if_car_present)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_car_not_present, self.if_car_not_present)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_session_fault, self.if_session_fault)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_session_is_ready, self.if_session_is_ready)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_session_is_not_ready, self.if_session_is_not_ready)
        self.apply_to_all_conditions(UIManagerFSMCondition.if_car_present_but_session_is_not_running, 
                                     self.if_car_present_but_session_is_not_running)

        #self.on(UIManagerFSMState.session_first_start.on_enter, self.set_new_pin)
        #self.on(UIManagerFSMState.session_first_start.on_enter, self.save_booking)
        self.on(UIManagerFSMState.car_connected.on_enter, self.trigger_remote_start)
        #self.on(UIManagerFSMState.normal_session.on_exit, self.clear_pin)
        self.on(UIManagerFSMState.session_end_summary.on_enter, self.trigger_remote_stop)

        self.tx_fsm.on(TxFSMState.transaction.on_enter, self.on_start_transaction)
        
        self.on(UIManagerFSMState.car_not_connected.on_enter, self.update_booking_to_tx_fsm)

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
        if self.tx_fsm.current_state in [TxManagerFSMState.ready]:
            self.handle_as_deferred(UIManagerFSMEvent.on_ready_status)
        else:
            await self.tx_fsm.handle(TxManagerFSMEvent.on_authorized_by_app)
            self.context.timeout_time = datetime.now() + timedelta(seconds=15)
        #ctxt.session_pin = random.randint(100000,999999)
        #ctxt.session_pins[ctxt.cp_evse_id] = ctxt.session_pin
        #ctxt.session_pins.redis.expire(ctxt.session_pins._format_key(ctxt.cp_evse_id), 100)

    async def update_booking_to_tx_fsm(self, *vargs, **kwargs):
        ctxt: UIManagerContext = self.context
        ctxt.tx_fsm.context.session_info = ctxt.session_info
    
    async def set_new_pin(self, *vargs, **kwargs):
        ctxt : UIManagerContext = self.context
        ctxt.session_pin = str(random.randint(100000,999999))
        ctxt.session_pins[ctxt.cp_evse_id] = ctxt.session_pin
        redis = get_default_redis()
        redis.expire(ctxt.session_pins._format_key(ctxt.cp_evse_id), self.get_session_remaining_duration())

    async def save_booking(self, *vargs, **kwargs):
        ctxt : UIManagerContext = self.context
        self.tx_fsm.context.session_info = BookingDetails.model_validate(ctxt.session_info.model_dump())

    async def clear_pin(self, *vargs, **kwargs):
        ctxt : UIManagerContext = self.context
        redis = get_default_redis()
        redis.expire(ctxt.session_pins._format_key(ctxt.cp_evse_id), 1)
        ctxt.session_pin = -1

    def if_car_present(self, *vargs):
        ctxt : UIManagerContext = self.context
        return ctxt.evse.connector_status == "Occupied"

    def if_car_not_present(self, *vargs):
        return not self.if_car_present(*vargs)

    @staticmethod
    def if_booking_not_supported(*vargs):
        return True


    def if_timeout(self, *vargs):
        return self.context.timeout_time < datetime.now()

    def if_session_is_not_ready(self, *vargs):
        logging.debug(f"if_session_is_not_ready check {self.tx_fsm.current_state=} {self.tx_fsm=}")
        return self.tx_fsm.current_state not in [TxManagerFSMState.ready]

    def if_session_is_ready(self, *vargs):
        logging.debug(f"if_session_is_ready check {self.tx_fsm.current_state=} {self.tx_fsm=}")
        return self.tx_fsm.current_state in [TxManagerFSMState.ready]

    def if_session_fault(self, *vargs):
        logging.debug(f"if_session_fault check {self.tx_fsm.current_state=} {self.tx_fsm=}")
        return self.tx_fsm.current_state in [TxManagerFSMState.fault]

    def if_car_present_but_session_is_not_running(self, *vargs):
        logging.debug(f"if_car_present_but_session_is_not_running check {self.tx_fsm.current_state=} {self.tx_fsm=}")
        return self.if_car_present(*vargs) and self.if_session_is_not_ready(*vargs)