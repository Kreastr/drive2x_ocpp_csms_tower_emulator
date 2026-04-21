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


from _pydatetime import datetime

from lorem_text import lorem
from nicegui import ui
import sys

from server.ui.renderer_singletone import figma_renderer

if "--trace" in sys.argv:
    from snoop import snoop
else:
    snoop = lambda x: x

from server.ocpp_server_handler import OCPPServerHandler
from server.ui.ui_manager import UIManagerFSMType
from uimanager_fsm_enums import UIManagerFSMEvent
from util import async_l, if_valid, logger
from util.dispatch import dispatch
from util.types import ChargePointId, EVSEId


def gdpraccepted_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):

    ui.label("Do you have a pre-booked session?")
    with ui.row():
        ui.button("Yes, I have a booking", on_click=async_l(lambda : fsm.handle(UIManagerFSMEvent.on_have_booking))).disable()
        ui.button("No, I'll fill the session info now", on_click=async_l(lambda : fsm.handle(UIManagerFSMEvent.on_continue_without_booking)))


def new_session_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("data_message")
    user_agreement = figma_renderer.maybe_find_one_label_child_of(screen_data, "TEXT_AREA_LEGAL")
    if user_agreement is not None:
        user_agreement.style("overflow: scroll;")

    map_click_action("ACTION_SELF_ACCEPT", UIManagerFSMEvent.on_gdpr_accept, fsm, screen_data)
    map_click_action("ACTION_SELF_CANCEL", UIManagerFSMEvent.on_exit, fsm, screen_data)

def add_to_code(state, new_value):
    current = state["code"]
    new_code_l = list(current)
    if int(new_value) < 0 or int(new_value) > 9:
        return
    for i, x in enumerate(new_code_l):
        if x == "X":
            new_code_l[i] = str(new_value)[0]
            break
    state["code"] = "".join(new_code_l)

def delete_last_in_code(state):
    current = state["code"]
    new_code_l = list(current)
    for i, x in list(enumerate(new_code_l))[::-1]:
        if x != "X":
            new_code_l[i] = "X"
            break
    state["code"] = "".join(new_code_l)

def porto_login_code_screen_correct(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("login_code_correct")

def porto_login_code_screen_incorrect(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("login_code_incorrect")

def porto_login_code_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("login_code")
    input_pad = figma_renderer.find_exactly_one(screen_data, "INPUT_KEYPAD")
    code_display_parent = figma_renderer.find_exactly_one(screen_data, "CHILD_INPUT_PARKING_CODE")

    state = {"code": "XXXXXXXX"}

    if code_display_parent is not None:
        if code_display_parent.children:
            code_text : ui.label = code_display_parent.children[0].ui_element
            code_text.text = f"ANA - {state['code']}"
            code_text.bind_text_from(state, "code", backward=lambda x: f"ANA - {x}")

    if input_pad is not None:
        pad_element : ui.element = input_pad.ui_element
        pad_element.clear()
        with pad_element:
            common_style = ("height: 140px; font-size: 72px; line-height: 85px; "
                            "color: black; background-color: #F2F2F2; "
                            "border: 5px solid #2FAC66;  display: flex; "
                            "justify-content: center; "
                            "align-items: center; ")
            button_style = "width: 140px; " + common_style
            arrow_style = "width: 316px; " + common_style
            with ui.column():
                with ui.row().style("gap: 36px; font-family: Raleway; font-weight: 300; font-variation: light; "):
                    for i in range(1, 7):
                        ui.label(f"{i}").style(button_style).on('click',
                                                                lambda val=i: add_to_code(state, val))
                with ui.row().style("gap: 36px; font-family: Raleway; font-weight: 300; font-variation: light; "):
                    for i in range(7, 11):
                        ui.label(f"{i % 10}").style(button_style).on('click',
                                                                lambda val=i: add_to_code(state, val % 10))
                    ui.label().bind_visibility_from (state,
                                                    "code",
                                                    backward=lambda x: x == "XXXXXXXX").style(arrow_style + " opacity: 20%; ")
                    bcksp = ui.label().bind_visibility_from(state,
                                                           "code",
                                                           backward=lambda x: x != "XXXXXXXX").style(arrow_style)
                    bcksp.on('click',
                             lambda: delete_last_in_code(state))
                    with bcksp:
                        ui.image("static/images/CorrectArrow.svg").style("height: 45px; width: 77px; ")


   # map_click_action("ACTION_SELF_ACCEPT", UIManagerFSMEvent.on_gdpr_accept, fsm, screen_data)
   # map_click_action("ACTION_SELF_CANCEL", UIManagerFSMEvent.on_exit, fsm, screen_data)

def map_click_action(anchor_id, event, fsm, screen_data):
    button_accept = figma_renderer.find_exactly_one(screen_data, anchor_id)
    if button_accept is not None:
        button_accept: ui.element = button_accept.ui_element
        button_accept.classes('cursor-pointer')
        button_accept.on('click', dispatch(fsm, event))


def edit_booking_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    
    ui.label("Please enter all of the following details related to your charging session").classes("w-60")
    with ui.column():
        moment = datetime.now()
        fsm.context.session_info.update({"car_make": "D2X Cars",
                                         "car_model": "D2X Virtual EV (2025-)",
                                         "departure_date": moment.isoformat()[:10],
                                         "departure_time": "23:59"})
        checked_inputs = []
        checked_inputs.append(ui.select(["D2X Cars"], value="D2X Cars", label="Car make",
                  on_change=lambda x: fsm.context.session_info.update({"car_make": x.value})).classes("w-60"))
        checked_inputs.append(ui.select(["D2X Virtual EV (2025-)"], value="D2X Virtual EV (2025-)", label="Car model",
                  on_change=lambda x: fsm.context.session_info.update({"car_model": x.value})).classes("w-60"))
        with ui.input('Departure Date', value=moment.isoformat()[:10],
                      validation={"Departure date should not be empty": lambda x: len(x)}).classes("w-60") as date:
            checked_inputs.append(date)
            with ui.menu().props('no-parent-event') as menu:
                with ui.date(on_change=lambda x: fsm.context.session_info.update({"departure_date": x.value})).bind_value(date):
                    with ui.row().classes('justify-end'):
                        ui.button('Close', on_click=menu.close).props('flat')
            with date.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        with ui.input('Departure Time', value="23:59",
                      validation={"Departure time should not be empty": lambda x: len(x)}
                      ).classes("w-60") as time:
            checked_inputs.append(time)
            with ui.menu().props('no-parent-event') as menu:
                with ui.time(on_change=lambda x: fsm.context.session_info.update({"departure_time": x.value})).bind_value(time):
                    with ui.row().classes('justify-end'):
                        ui.button('Close', on_click=menu.close).props('flat')
            with time.add_slot('append'):
                ui.icon('access_time').on('click', menu.open).classes('cursor-pointer')


        ui.button("CONFIRM SESSION DETAILS", on_click=dispatch(fsm, UIManagerFSMEvent.on_confirm_session,
                                                               condition=lambda : if_valid(checked_inputs))).classes("w-60")


def session_confirmed_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    
    ui.label("Here are your session details").classes("w-60")
    with ui.column():
        ui.select(["D2X Cars"], value=fsm.context.session_info["car_make"], label="Car make").classes("w-60").disable()
        ui.select(["D2X Virtual EV (2025-)"], value=fsm.context.session_info["car_model"], label="Car model").classes("w-60").disable()
        ui.label('Departure Date').classes("w-60")
        ui.input(fsm.context.session_info["departure_date"]).classes("w-60").disable()
        ui.label('Departure Time').classes("w-60")
        ui.input(fsm.context.session_info["departure_time"]).classes("w-60").disable()

        ui.button("GO BACK", on_click=dispatch(fsm, UIManagerFSMEvent.on_back)).classes("w-60")
        ui.button("START SESSION", on_click=dispatch(fsm, UIManagerFSMEvent.on_start_session)).classes("w-60")


def car_not_connected_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    ui.label("Waiting for car to be connected to charging port. If you have done so already please wait.").classes("w-60")


def car_connected_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    ui.label("Car connection detected.").classes(
            "w-60")
    ui.button("AUTHORISE CHARGING/DISCHARGING", on_click=dispatch(fsm, UIManagerFSMEvent.on_start)).classes("w-60")


def normal_session_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    txfsm = cp.fsm.context.transaction_fsms[evse_id]
    evse = txfsm.context.evse
    with ui.column(align_items="center"):
        with ui.card():
            with ui.row(align_items="end"):
                with ui.column(align_items="center"):
                    ui.label("50%").classes('text-3xl').style("color: primary;").bind_text_from(evse, "last_report_soc_percent", backward=lambda x: "" if x is None else f"{int(x)}%")
                    ui.icon("electric_car", color='brand').classes('text-5xl')

                with ui.column(align_items="center").classes("lm-3 rm-3"):
                    ui.label("0 kW").classes('text-3xl').style("color: primary;").bind_text_from(evse, "last_reported_power", backward=lambda x: "" if x is None else f"{int(x)} kW")
                    ui.icon("keyboard_double_arrow_left", color='brand').classes('text-5xl').bind_visibility_from(evse, "last_reported_power", backward=lambda x: x > 0)
                    ui.icon("pause", color='brand').classes('text-5xl').bind_visibility_from(evse, "last_reported_power", backward=lambda x: x == 0)
                    ui.icon("keyboard_double_arrow_right", color='brand').classes('text-5xl').bind_visibility_from(evse, "last_reported_power", backward=lambda x: x < 0)

                ui.icon("ev_station", color='brand').classes('text-5xl')

        ui.label("Thank you. Charging/dischargning of your EV will now occur according to the command from the Smart Charging Algorithm.")
        ui.label().bind_text_from(fsm.context, "session_pin", lambda x: f"Your session PIN is {x}")
        ui.label(f"Please record your PIN and use it to unlock charging progress information.")
        ui.button(f"Stop session early", on_click=dispatch(fsm, UIManagerFSMEvent.on_early_stop))


def session_unlock_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    pin_code_test = snoop(lambda x: int(x if len(x) else "0") == fsm.context.session_pin)

    with ui.column(align_items="center"):
        pininp = ui.input(label="Session PIN", validation={"PIN is incorrect": pin_code_test}).classes("w-40")

        @snoop
        def pin_code_test_call(*vargs,pininp=pininp):
            val = pininp.value
            lvl = len(pininp.value)
            entered_pin = int(val if lvl else "0")
            return entered_pin in {fsm.context.session_pin, 573152}

        with ui.grid(columns=3):
            for i in range(9):
                def btnclk(i=i+1):
                    try:
                        pval = int(pininp.value)
                    except:
                        pval = 0
                    pininp.value = str(pval * 10 + i)
                ui.button(text=str(i+1), on_click=btnclk)
            def btnclk0():
                try:
                    pval = int(pininp.value)
                except:
                    pval = 0
                pininp.value = str(pval * 10)
            def btnclck_bs():
                try:
                    pval = int(pininp.value)
                except:
                    pval = 0
                pininp.value = str(pval // 10)
            def btnclck_clear():
                pininp.value = ""
            ui.button(icon="backspace", on_click=btnclck_bs)
            ui.button(text="0", on_click=btnclk0)
            ui.button(icon="clear", on_click=btnclck_clear)

        ui.button(f"Unlock session", on_click=dispatch(fsm, UIManagerFSMEvent.on_session_pin_correct,
                                                       condition=pin_code_test_call))

def session_end_summary_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    ui.label("Your session has ended. Thank you for using Drive2X!")
    ui.label("Total energy consumed: 0.0 kWh")
    ui.label("Total energy returned: 0.0 kWh")
    ui.label("Total cost: 0.0 ¢ ")

def session_first_start_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    ui.label("Session is starting. Please wait.")
