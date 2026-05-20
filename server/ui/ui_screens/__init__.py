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
from datetime import datetime as dt
from datetime import timedelta
import datetime
from typing import Optional

from beartype import beartype
from nicegui import ui
import sys

from numpy import ceil

from server.data import BookingDetails, UIManagerContext
from server.ui.models.figma_document_model import FigmaNode
from server.ui.renderer_singletone import figma_renderer

if "--trace" in sys.argv:
    pass
else:
    snoop = lambda x: x

from server.ocpp_server_handler import OCPPServerHandler
from server.ui.ui_manager import UIManagerFSMType
from uimanager_fsm_enums import UIManagerFSMEvent
from util import async_l, if_valid, setup_logging
from util.dispatch import dispatch
from util.types import ChargePointId, EVSEId

logger = setup_logging(__name__)
logger.setLevel(logging.DEBUG)

booking_details : dict[str, BookingDetails] = dict()

def gdpraccepted_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    ui.label("Do you have a pre-booked session?")
    with ui.row():
        ui.button("Yes, I have a booking",
                  on_click=async_l(lambda: fsm.handle(UIManagerFSMEvent.on_have_booking))).disable()
        ui.button("No, I'll fill the session info now",
                  on_click=async_l(lambda: fsm.handle(UIManagerFSMEvent.on_continue_without_booking)))


def new_session_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("data_message")
    user_agreement = figma_renderer.maybe_find_one_label_child_of(screen_data, "TEXT_AREA_LEGAL")
    if user_agreement is not None:
        user_agreement.style("overflow: scroll;")

    map_click_action("ACTION_SELF_ACCEPT", UIManagerFSMEvent.on_gdpr_accept, fsm, screen_data)
    map_click_action("ACTION_SELF_CANCEL", UIManagerFSMEvent.on_exit, fsm, screen_data)


async def add_to_code(state, new_value, callbacks=None):
    current = state["code"]
    new_code_l = list(current)
    if int(new_value) < 0 or int(new_value) > 9:
        return
    for i, x in enumerate(new_code_l):
        if x == "X":
            new_code_l[i] = str(new_value)[0]
            break
    state["code"] = "".join(new_code_l)
    if callbacks is not None:
        for callback in callbacks:
            await callback()


async def delete_last_in_code(state):
    current = state["code"]
    new_code_l = list(current)
    for i, x in list(enumerate(new_code_l))[::-1]:
        if x != "X":
            new_code_l[i] = "X"
            break
    state["code"] = "".join(new_code_l)

def format_datetime(x : datetime.datetime):
    return x.astimezone(datetime.timezone("Portugal")).strftime("%d %b %Y - %H:%M")

def format_session_duration(td: timedelta) -> str:
    total_hours = int(td.total_seconds() / 3600 + 0.5)

    days, hours = divmod(total_hours, 24)
    return f"{days}d" if days > 0 else "" + f"{hours}h"

def booking_details_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("session_details")
    map_click_action("ACTION_SELF_CONFIRM", UIManagerFSMEvent.on_confirm_session, fsm, screen_data)
    map_click_action("ACTION_SELF_CANCEL", UIManagerFSMEvent.on_exit, fsm, screen_data)

    update_generic_fields(screen_data, state=dict())

    anchor = "TIME SET"
    time_of_connection = _lookup_span_in_child_of_anchor(anchor, child_index=0, span_index=1, screen_data=screen_data)
    time_of_disconnection = _lookup_span_in_child_of_anchor(anchor, child_index=1, span_index=1, screen_data=screen_data)
    session_duration = _lookup_span_in_child_of_anchor(anchor, child_index=2, span_index=1, screen_data=screen_data)
    logger.debug(f"booking_details_screen {time_of_connection=}")
    if time_of_connection is not None:
        time_of_connection.content = ""
        time_of_connection.bind_content_from(fsm.context.session_info,
                                          "arrival_time",
                                          backward=format_datetime)
    if time_of_disconnection is not None:
        time_of_disconnection.content = ""
        time_of_disconnection.bind_content_from(fsm.context.session_info,
                                              "departure_time",
                                              backward=format_datetime)
    if session_duration is not None:
        session_duration.content = ""
        session_duration.bind_content_from(fsm.context.session_info,
                                           "session_duration",
                                            backward=format_session_duration)


def update_generic_fields(screen_data, state):
    date_time_now_element = figma_renderer.maybe_find_one_label_child_of(screen_data, "BOOKING_DATE_TIME")
    if date_time_now_element is None:
        date_time_now = figma_renderer.find_exactly_one(screen_data, "BOOKING_DATE_TIME")
        date_time_now_element = date_time_now.ui_element

    if date_time_now_element is not None:
        assert type(date_time_now_element) is ui.label
        date_time_now_element.bind_text_from(state, "current_time", backward=format_datetime)
        ui.timer(5, lambda: state.update(dict(current_time=dt.now(tz=datetime.UTC))))



def _lookup_span_in_child_of_anchor(anchor, child_index, span_index, screen_data) -> Optional[ui.html]:
    anchor_element = figma_renderer.find_exactly_one(screen_data, anchor)
    logger.debug(f"_lookup_span_in_child_of_anchor {anchor_element=}")
    if anchor_element is not None:
        if len(anchor_element.children) > child_index:
            groups: FigmaNode = anchor_element.children[child_index]
            logger.debug(f"_lookup_span_in_child_of_anchor {groups=}")
            if len(groups.get_spans) > span_index:
                node = groups.get_spans[span_index]
                logger.debug(f"_lookup_span_in_child_of_anchor {node=}")
                assert type(node) == ui.html
                return node
    return None


def porto_login_code_screen_correct(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType,
                                    cp: OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("login_code_correct")
    map_click_action("ACTION_SELF_CONFIRM", UIManagerFSMEvent.on_confirm_session, fsm, screen_data)
    map_click_action("ACTION_SELF_CANCEL", UIManagerFSMEvent.on_exit, fsm, screen_data)


def porto_login_code_screen_incorrect(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType,
                                      cp: OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("login_code_error")
    map_click_action("ACTION_SELF_BACK", UIManagerFSMEvent.on_back, fsm, screen_data)


def test_pin(pin, context : UIManagerContext):
    if "X" in pin:
        return "INCOMPLETE"
    if pin == "00000000":
        arrival = dt.now(tz=datetime.UTC).replace(minute=0,second=0,microsecond=0)
        departure = arrival + timedelta(days=30)
        booking_details[pin] = BookingDetails(arrival_time=arrival,
                                              departure_time=departure,
                                              original_departure_time=departure,
                                              session_duration=departure-arrival)

    if pin in booking_details:
        context.session_pin = pin
        context.session_info = booking_details[pin]
        return "CORRECT"

    return "INCORRECT"


@beartype
def porto_login_code_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("login_code")
    input_pad = figma_renderer.find_exactly_one(screen_data, "INPUT_KEYPAD")
    code_display_parent = figma_renderer.find_exactly_one(screen_data, "CHILD_INPUT_PARKING_CODE")

    state = {"code": "XXXXXXXX"}

    if code_display_parent is not None:
        if code_display_parent.children:
            code_text: ui.label = code_display_parent.children[0].ui_element
            code_text.text = f"ANA - {state['code']}"
            code_text.bind_text_from(state, "code", backward=lambda x: f"ANA - {x}")

    if input_pad is not None:
        pad_element: ui.element = input_pad.ui_element
        pad_element.clear()
        with pad_element:
            common_style = ("height: 140px; font-size: 72px; line-height: 85px; "
                            "color: black; background-color: #F2F2F2; "
                            "border: 5px solid #2FAC66;  display: flex; "
                            "justify-content: center; "
                            "align-items: center; ")
            button_style = "width: 140px; " + common_style
            arrow_style = "width: 316px; " + common_style
            code_dispatchers = [dispatch(fsm, UIManagerFSMEvent.on_correct_pin,
                                         condition=lambda s=state, fsm=fsm: test_pin(s["code"], fsm.context) == "CORRECT"),
                                dispatch(fsm, UIManagerFSMEvent.on_incorrect_pin,
                                         condition=lambda s=state, fsm=fsm: test_pin(s["code"], fsm.context) == "INCORRECT"),
                                ]
            with ui.column():
                with ui.row().style("gap: 36px; font-family: Raleway; font-weight: 300; font-variation: light; "):
                    for i in range(1, 7):
                        ui.label(f"{i}").style(button_style).on('click',
                                                                lambda val=i: add_to_code(state, val,
                                                                                          callbacks=code_dispatchers))
                with ui.row().style("gap: 36px; font-family: Raleway; font-weight: 300; font-variation: light; "):
                    for i in range(7, 11):
                        ui.label(f"{i % 10}").style(button_style).on('click',
                                                                     lambda val=i: add_to_code(state, val % 10,
                                                                                               callbacks=code_dispatchers))
                    ui.label().bind_visibility_from(state,
                                                    "code",
                                                    backward=lambda x: x == "XXXXXXXX").style(
                        arrow_style + " opacity: 20%; ")
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


def edit_booking_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    ui.label("Please enter all of the following details related to your charging session").classes("w-60")
    with ui.column():
        moment = datetime.now()
        fsm.context.session_info.update({"car_make": "D2X Cars",
                                         "car_model": "D2X Virtual EV (2025-)",
                                         "departure_date": moment.isoformat()[:10],
                                         "departure_time": "23:59"})
        checked_inputs = []
        checked_inputs.append(ui.select(["D2X Cars"], value="D2X Cars", label="Car make",
                                        on_change=lambda x: fsm.context.session_info.update(
                                            {"car_make": x.value})).classes("w-60"))
        checked_inputs.append(ui.select(["D2X Virtual EV (2025-)"], value="D2X Virtual EV (2025-)", label="Car model",
                                        on_change=lambda x: fsm.context.session_info.update(
                                            {"car_model": x.value})).classes("w-60"))
        with ui.input('Departure Date', value=moment.isoformat()[:10],
                      validation={"Departure date should not be empty": lambda x: len(x)}).classes("w-60") as date:
            checked_inputs.append(date)
            with ui.menu().props('no-parent-event') as menu:
                with ui.date(
                        on_change=lambda x: fsm.context.session_info.update({"departure_date": x.value})).bind_value(
                        date):
                    with ui.row().classes('justify-end'):
                        ui.button('Close', on_click=menu.close).props('flat')
            with date.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        with ui.input('Departure Time', value="23:59",
                      validation={"Departure time should not be empty": lambda x: len(x)}
                      ).classes("w-60") as time:
            checked_inputs.append(time)
            with ui.menu().props('no-parent-event') as menu:
                with ui.time(
                        on_change=lambda x: fsm.context.session_info.update({"departure_time": x.value})).bind_value(
                        time):
                    with ui.row().classes('justify-end'):
                        ui.button('Close', on_click=menu.close).props('flat')
            with time.add_slot('append'):
                ui.icon('access_time').on('click', menu.open).classes('cursor-pointer')

        ui.button("CONFIRM SESSION DETAILS", on_click=dispatch(fsm, UIManagerFSMEvent.on_confirm_session,
                                                               condition=lambda: if_valid(checked_inputs))).classes(
            "w-60")


def session_confirmed_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    ui.label("Here are your session details").classes("w-60")
    with ui.column():
        ui.select(["D2X Cars"], value=fsm.context.session_info["car_make"], label="Car make").classes("w-60").disable()
        ui.select(["D2X Virtual EV (2025-)"], value=fsm.context.session_info["car_model"], label="Car model").classes(
            "w-60").disable()
        ui.label('Departure Date').classes("w-60")
        ui.input(fsm.context.session_info["departure_date"]).classes("w-60").disable()
        ui.label('Departure Time').classes("w-60")
        ui.input(fsm.context.session_info["departure_time"]).classes("w-60").disable()

        ui.button("GO BACK", on_click=dispatch(fsm, UIManagerFSMEvent.on_back)).classes("w-60")
        ui.button("START SESSION", on_click=dispatch(fsm, UIManagerFSMEvent.on_start_session)).classes("w-60")


def car_not_connected_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("ready_mode_booked")
    update_generic_fields(screen_data, state=dict())



def car_connected_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("ready_mode_booked")
    update_generic_fields(screen_data, state=dict())

    input_pad = figma_renderer.find_exactly_one(screen_data, "INFO_CHARGING_STATUS")
    if input_pad is not None:
        nch = len(input_pad.ui_element.default_slot.children)
        if nch > 1:
            second_span : ui.html = input_pad.ui_element.default_slot.children[1]
            second_span.delete()
    #import code
    #code.interact(local=locals())
    #ui.button("AUTHORISE CHARGING/DISCHARGING", on_click=dispatch(fsm, UIManagerFSMEvent.on_start)).classes("w-60")


def normal_session_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):

    txfsm = cp.fsm.context.transaction_fsms[evse_id]
    evse = txfsm.context.evse
    state = {"countdown": 30}


    async def on_countdown():
        state.update({"countdown": state["countdown"] - 1})
        if state["countdown"] < 1:
            state["countdown"] = 1
            await fsm.handle(UIManagerFSMEvent.on_exit)


    ui.timer(1, on_countdown)

    root, screen_data = figma_renderer.render_screen("charging_mode")
    update_generic_fields(screen_data, state=state)

    map_click_action("ACTION_SELF_CANCEL", UIManagerFSMEvent.on_early_stop, fsm, screen_data)

    session_end_time = _lookup_span_in_child_of_anchor("SESSION_END_DATE_TIME", child_index=0, span_index=1, screen_data=screen_data)
    if session_end_time is not None:
        session_end_time.bind_content_from(fsm.context.tx_fsm.context.session_info, "departure_time",
                                           backward=lambda x: f"<br>until {format_datetime(x)}")

    live_power = figma_renderer.maybe_find_one_label_child_of(screen_data, "INFO_LIVE_CHARGING_POWER", index=1)

    if live_power is not None:
        live_power.bind_text_from(evse,
                                  "last_reported_power",
                                  backward= lambda x: f"{x:.1f} kW")
    timeout_notice = figma_renderer.maybe_find_one_label_child_of(screen_data, "INFO_TIMEOUT_NOTICE")
    if timeout_notice is not None:
        timeout_notice.bind_text_from(state, "countdown", backward=lambda x: f"You can now leave the car, this screen will automatically close in {x} second{'s' if x > 1 else ''}...")


    return

    with ui.column(align_items="center"):
        with ui.card():
            with ui.row(align_items="end"):
                with ui.column(align_items="center"):
                    ui.label("50%").classes('text-3xl').style("color: primary;").bind_text_from(evse,
                                                                                                "last_report_soc_percent",
                                                                                                backward=lambda
                                                                                                    x: "" if x is None else f"{int(x)}%")
                    ui.icon("electric_car", color='brand').classes('text-5xl')

                with ui.column(align_items="center").classes("lm-3 rm-3"):
                    ui.label("0 kW").classes('text-3xl').style("color: primary;").bind_text_from(evse,
                                                                                                 "last_reported_power",
                                                                                                 backward=lambda
                                                                                                     x: "" if x is None else f"{int(x)} kW")
                    ui.icon("keyboard_double_arrow_left", color='brand').classes('text-5xl').bind_visibility_from(evse,
                                                                                                                  "last_reported_power",
                                                                                                                  backward=lambda
                                                                                                                      x: x > 0)
                    ui.icon("pause", color='brand').classes('text-5xl').bind_visibility_from(evse,
                                                                                             "last_reported_power",
                                                                                             backward=lambda x: x == 0)
                    ui.icon("keyboard_double_arrow_right", color='brand').classes('text-5xl').bind_visibility_from(evse,
                                                                                                                   "last_reported_power",
                                                                                                                   backward=lambda
                                                                                                                       x: x < 0)

                ui.icon("ev_station", color='brand').classes('text-5xl')

        ui.label(
            "Thank you. Charging/dischargning of your EV will now occur according to the command from the Smart Charging Algorithm.")
        ui.label().bind_text_from(fsm.context, "session_pin", lambda x: f"Your session PIN is {x}")
        ui.label(f"Please record your PIN and use it to unlock charging progress information.")
        ui.button(f"Stop session early", on_click=dispatch(fsm, UIManagerFSMEvent.on_early_stop))



def session_end_summary_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    root, screen_data = figma_renderer.render_screen("final_thanks")
    state = {"countdown": 60}
    update_generic_fields(screen_data, state=state)

    async def on_countdown():
        state.update({"countdown": state["countdown"] - 1})
        if state["countdown"] < 1:
            state["countdown"] = 1
            await fsm.handle(UIManagerFSMEvent.on_exit)


    ui.timer(1, on_countdown)

    timeout_notice = figma_renderer.maybe_find_one_label_child_of(screen_data, "INFO_TIMEOUT_NOTICE")
    if timeout_notice is not None:
        timeout_notice.bind_text_from(state, "countdown", backward=lambda x: f"This window will automatically close in {x} second{'s' if x > 1 else ''}...")

def car_connected_too_soon_error_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    error_screen("ERROR",
                 "You have connected your EV too early.",
                 "Please disconnect the car and only reconnect it once instructed by the charger.",
                 cp_id,
                 hide_button=True)



def error_screen(heading, title, text, cp_id : ChargePointId, hide_button=False):
    root, screen_data = figma_renderer.render_screen("error_page")

    error_heading = figma_renderer.maybe_find_one_label_child_of(screen_data, "ERROR")
    if error_heading is not None:
        error_heading.text = heading

    error_title = figma_renderer.maybe_find_one_label_child_of(screen_data, "ERROR_TITLE")
    if error_title is not None:
        error_title.text = title

    error_message = figma_renderer.maybe_find_one_label_child_of(screen_data, "ERROR_MESSAGE")
    if error_message is not None:
        error_message.text = text

    button_exit = figma_renderer.find_exactly_one(screen_data, "ACTION_SELF_EXIT")
    if button_exit is not None:
        if hide_button:
            button_exit.ui_element.delete()
        else:
            button_exit : ui.element = button_exit.ui_element
            button_exit.classes('cursor-pointer')
            button_exit.on('click', lambda: ui.navigate.to(f"/d2x_ui/{cp_id}"))

    return error_heading, error_title, error_message
