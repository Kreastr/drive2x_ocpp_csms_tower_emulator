from _pydatetime import datetime

from lorem_text import lorem
from nicegui import ui
from snoop import snoop

from server.ocpp_server_handler import OCPPServerHandler
from server.ui_manager import UIManagerFSMType
from uimanager_fsm_enums import UIManagerFSMEvent
from util import async_l, if_valid
from util.dispatch import dispatch
from util.types import ChargePointId, EVSEId


def gdpraccepted_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    with ui.card():
        ui.label("Do you have a pre-booked session?")
        with ui.row():
            ui.button("Yes, I have a booking", on_click=async_l(lambda : fsm.handle(UIManagerFSMEvent.on_have_booking))).disable()
            ui.button("No, I'll fill the session info now", on_click=async_l(lambda : fsm.handle(UIManagerFSMEvent.on_continue_without_booking)))


def new_session_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    with ui.card():
        ui.label("Welcome to the Drive2X Project demo. ")
        ui.label("Here is how we process your data. ")
        with ui.scroll_area().classes('w-800 h-400 border'):
            ui.label(lorem.paragraphs(5).split("\n"))
        with ui.row():
            ui.button("Yes, I have read the policies and consent to handling of my data",
                      on_click=dispatch(fsm, UIManagerFSMEvent.on_gdpr_accept))
            ui.button("No, do not consent and cannot use this service.",
                      on_click=dispatch(fsm, UIManagerFSMEvent.on_exit))


def edit_booking_screen(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    with ui.card():
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
    with ui.card():
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
    with ui.card():
        ui.label("Waiting for car to be connected to charging port. If you have done so already please wait.").classes("w-60")


def car_connected_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    with ui.card():
        ui.label("Car connection detected.").classes(
            "w-60")
        ui.button("AUTHORISE CHARGING/DISCHARGING", on_click=dispatch(fsm, UIManagerFSMEvent.on_start)).classes("w-60")


def normal_session_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    ui.label("Thank you. Charging/dischargning of your EV will now occur according to the command from the Smart Charging Algorithm.")
    ui.label().bind_text_from(fsm.context, "session_pin", lambda x: f"Your session PIN is {x}")
    ui.label(f"Please record your PIN and use it to unlock charging progress information.")
    ui.button(f"Stop session early", on_click=dispatch(fsm, UIManagerFSMEvent.on_early_stop))


def session_unlock_screen(cp_id: ChargePointId, evse_id: EVSEId, fsm: UIManagerFSMType, cp: OCPPServerHandler):
    pin_code_test = snoop(lambda x: int(x if len(x) else "0") == fsm.context.session_pin)

    pininp = ui.input(label="Session PIN", validation={"PIN is incorrect": pin_code_test}).classes("w-40")

    @snoop
    def pin_code_test_call(*vargs,pininp=pininp):
        val = pininp.value
        lvl = len(pininp.value)
        return int(val if lvl else "0") == fsm.context.session_pin

    ui.button(f"Unlock session", on_click=dispatch(fsm, UIManagerFSMEvent.on_session_pin_correct,
                                                   condition=if_valid([pininp])))
