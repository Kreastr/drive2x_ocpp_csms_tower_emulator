import asyncio
import logging
import traceback
from typing import cast, Self

import websockets
from beartype import beartype
from nicegui.binding import BindableProperty, bind_from
from nicegui.element import Element
from ocpp.v201 import call
from ocpp.v201 import call_result
from ocpp.v201.datatypes import ComponentType, VariableType, \
    SetVariableDataType, EVSEType

from nicegui import ui, app, background_tasks, ElementFilter
from typing import Any

from websockets import Subprotocol

import server.ocpp_server_handler
from charge_point_fsm_enums import ChargePointFSMEvent
from server.charge_point_model import ChargePointFSMType
from server.data import ChargePointContext
from server.ocpp_server_handler import redis, session_pins, OCPPServerHandler
from server.ui_screens import gdpraccepted_screen, new_session_screen, edit_booking_screen, session_confirmed_screen, \
    car_not_connected_screen, car_connected_screen, normal_session_screen, session_unlock_screen
from uimanager_fsm_enums import UIManagerFSMState, UIManagerFSMEvent
from util import setup_logging
from util.fair_semaphore_redis import FairSemaphoreRedis
from util.types import *

from server.ui_manager import UIManagerFSMType, UIManagerContext, ui_manager_uml


async def broadcast_to(op, page, **filters):
    for client in app.clients(page):
        with client:
            for old in ElementFilter(**filters):
                op(old)



logger = setup_logging(__name__)
logger.setLevel(logging.DEBUG)

cp_card_container : ui.grid | None = None
charge_points : dict[ChargePointId, OCPPServerHandler] = dict()
ui_pages : dict[ChargePointId, UIManagerFSMType] = dict()
charge_point_cards : dict[ChargePointId, Any] = dict()




async def on_connect(websocket):
    logger.warning(f"on client connect {websocket=}")
    cp = OCPPServerHandler("provisional", websocket)

    await get_remote_ip(cp, websocket)

    await cp.fsm.handle(ChargePointFSMEvent.on_start)

    if 0:
        await set_measurement_variables(cp)
    while cp.fsm.context.connection_task is None or not cp.fsm.context.connection_task.done():
        await asyncio.sleep(1)
    await cp.close_connection()
    try:
        result = cp.fsm.context.connection_task.result()
    except Exception as e:
        result = f"Exception {e}"
    cp.log_event(f"start_task.result {result}")


async def get_remote_ip(cp, websocket):
    if "X-Real-IP" in websocket.request.headers:
        real_ip = websocket.request.headers["X-Real-IP"]
    else:
        real_ip = websocket.remote_address[0]
    cp.fsm.context.remote_ip = real_ip


async def set_measurement_variables(cp):
    result: call_result.SetVariables = await cp.call(
        call.SetVariables(set_variable_data=[SetVariableDataType(
            attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
            component=ComponentType(name="AlignedDataCtrlr"),
            variable=VariableType(name="Measurands")),
            SetVariableDataType(
                attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                component=ComponentType(name="AlignedDataCtrlr"),
                variable=VariableType(name="TxEndedMeasurands")),
            SetVariableDataType(
                attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                component=ComponentType(name="SampledDataCtrlr"),
                variable=VariableType(name="TxStartedMeasurands")),
            SetVariableDataType(
                attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                component=ComponentType(name="SampledDataCtrlr"),
                variable=VariableType(name="TxUpdatedMeasurands")),
            SetVariableDataType(
                attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                component=ComponentType(name="SampledDataCtrlr"),
                variable=VariableType(name="TxEndedMeasurands"))
        ]))
    logger.warning(f"Charger measurands set {result=}")


async def main():
    logging.warning("main start")
    server = await websockets.serve(on_connect, '0.0.0.0', 9000, subprotocols=[Subprotocol('ocpp2.0.1')])
    logging.warning("main server ready")
    await server.serve_forever()
    logging.warning("main exit")

@app.get("/cp")
async def cp_list():
    return {"charge_points": list(charge_points)}

@app.get("/cp/{cp_id}/events/")
async def events(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"events": charge_points[cp_id].events}

@app.get("/cp/{cp_id}/reboot")
async def reboot(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].reboot_peer_and_close_connection()}

@app.get("/cp/{cp_id}/transactions")
async def transactions(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"events": charge_points[cp_id].fsm.context.transactions}


@app.get("/cp/{cp_id}/remote_start/{evse_id}")
async def remote_start(cp_id : str, evse_id : int):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].do_remote_start(evse_id)}


@app.get("/cp/{cp_id}/remote_stop/{evse_id}")
async def remote_stop(cp_id : str, evse_id : int):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].do_remote_stop(evse_id)}

@app.get("/cp/{cp_id}/report_full")
async def report_full(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].request_full_report()}


@app.get("/cp/{cp_id}/setpoint/{value}")
async def setpoint(cp_id : str, value : int):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        if value > 4000:
            value = 4000
        if value < -2000:
            value = -2000
        return {"result": await charge_points[cp_id].call(
            call.SetVariables(set_variable_data=[SetVariableDataType(attribute_value=str(value),
                                                                     component=ComponentType(name="V2XChargingCtrlr", instance="1", evse=EVSEType(id=1)),
                                                                     variable=VariableType(name="Setpoint"))]))}



@beartype
class CPCard(Element):
    online = BindableProperty(
        on_change=lambda sender, value: cast(Self, sender)._handle_online_change(value))

    def __init__(self, fsm : ChargePointFSMType, **kwargs):
        super().__init__(tag="div")
        self.fsm = fsm
        self.cp_context : ChargePointContext = fsm.context
        cp = charge_points[self.cp_context.id]
        self.card = ui.card()
        self.bind_online_from(self.cp_context, "online")
        self._handle_online_change(self.cp_context.online)
        with self.card:
            with ui.row():
                ui.label("ID")
                ui.label().bind_text(self.cp_context, "id")
            with ui.row():
                ui.label("Remote IP")
                ui.label().bind_text(self.cp_context, "remote_ip")
            with ui.row():
                ui.label("Status")
                ui.label().bind_text(self.fsm, "current_state")
            ui.button("REBOOT", on_click=cp.reboot_peer_and_close_connection)
            ui.separator()
            self.connector_container = ui.column()
            ui.separator()
            ui.button("UI", on_click=lambda: ui.navigate.to(f"/d2x_ui/{self.cp_context.id}"))
            ui.button("REPORT", on_click=cp.reboot_peer_and_close_connection)

        for connid in self.cp_context.transaction_fsms:
            self.on_new_evse(connid)


    def bind_online_from(self, var, name):
        bind_from(self_obj=self, self_name="online",
                  other_obj=var, other_name=name)

    def _handle_online_change(self, card_online_status):
        logger.warning(f"online changes {card_online_status}")
        self.card.classes(remove="bg-green bg-red")
        self.card.classes(add="bg-green" if card_online_status else "bg-red")
        self.card.update()

    def on_new_evse(self, evse_id : EVSEId):
        logger.warning(f"on new connector {evse_id}")
        with self.connector_container:
            with ui.row(align_items='center'):
                cp = charge_points[self.cp_context.id]
                evse = cp.get_evse(evse_id)
                new_label = ui.label(text=f"{evse_id}: {evse.connector_status}")
                new_label.bind_text_from(evse, "connector_status", backward=lambda x, cid=evse_id: f"{cid}: {x}")
                tx_fsm = self.cp_context.transaction_fsms[evse_id]
                tx_label = ui.label(text=f"{str(tx_fsm.current_state)}")
                tx_label.bind_text_from(tx_fsm, "current_state")
                def exec_async(_evse_id, operation):
                    async def executable():
                        try:
                            logger.warning(f"operation result {await operation(_evse_id)}")
                        except:
                            logger.error(traceback.format_exc())
                    return executable
                ui.button("Start", on_click=exec_async(evse_id, cp.do_remote_start))
                ui.button("Stop", on_click=exec_async(evse_id, cp.do_remote_stop))
                ui.button("Clear", on_click=exec_async(evse_id, cp.do_clear_fault))
                ui.button("+", on_click=exec_async(evse_id, cp.do_increase_setpoint))
                ui.label("0").bind_text_from(self.fsm.context.transaction_fsms[evse_id].context.evse, "setpoint", backward=str)
                ui.button("-", on_click=exec_async(evse_id, cp.do_decrease_setpoint))


@ui.page("/")
async def index():
    ui.page_title(f'Drive2X OCPP Server Control Panel')
    background_tasks.create_lazy(main(),name="main")
    ui.label(text="Charge Point status")
    with ui.row().mark("cp_card_container"):
        for cpid in charge_points:
            if cpid != "provisional":
                CPCard(charge_points[cpid].fsm).mark(cpid)


@ui.page("/d2x_ui/{cp_id}")
async def d2x_ui_landing(cp_id : ChargePointId):
    ui.page_title(f'Drive2X UI - {cp_id}')

    with ui.card().classes('fixed-center'):
        if cp_id not in charge_points:
            ui.label(f"Charge Point with this ID is not active. Please try later.")
            ui.timer(30, lambda : ui.navigate.to(f"/d2x_ui/{cp_id}"))

        else:
            evse_ids = list(charge_points[cp_id].fsm.context.transaction_fsms)

            ui.label(cp_id)
            with ui.grid():
                for evse_id in evse_ids:
                    with ui.link(target=f"/d2x_ui/{cp_id}/{evse_id}"):
                        with ui.card():
                            ui.label(evse_id)


STATE_SCREEN_MAP = {UIManagerFSMState.new_session: new_session_screen,
                    UIManagerFSMState.gdpraccepted: gdpraccepted_screen,
                    UIManagerFSMState.edit_booking: edit_booking_screen,
                    UIManagerFSMState.evseselect_page: lambda cp_id, *vargs: ui.navigate.to(f"/d2x_ui/{cp_id}"),
                    UIManagerFSMState.session_confirmed: session_confirmed_screen,
                    UIManagerFSMState.car_not_connected: car_not_connected_screen,
                    UIManagerFSMState.car_connected: car_connected_screen,
                    UIManagerFSMState.normal_session: normal_session_screen,
                    UIManagerFSMState.session_unlock: session_unlock_screen
                    }

@ui.refreshable
def state_dependent_frame(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    ui.label(fsm.current_state)
    ui.label(cp_id)
    ui.label(evse_id)
    if fsm.current_state in STATE_SCREEN_MAP:
        STATE_SCREEN_MAP[fsm.current_state](cp_id, evse_id, fsm, cp)


@ui.page("/d2x_ui/{cp_id}/{evse_id}")
async def d2x_ui_evse(cp_id : ChargePointId, evse_id : EVSEId):
    ui.page_title(f'Drive2X UI - {cp_id}/{evse_id}')
    semaphore = FairSemaphoreRedis(name="page-access-" + cp_id + "-" + str(evse_id), n_users=1, redis=redis, session_timeout=5)
    semaphore.acquire()

    with ui.card().classes('fixed-center').bind_visibility_from(semaphore, "acquired"):
        if cp_id not in charge_points:
            ui.label(f"Charge Point with this ID is not active. Please try later.")
            ui.timer(30, lambda : ui.navigate.to(f"/d2x_ui/{cp_id}/{evse_id}"))
        elif evse_id not in charge_points[cp_id].fsm.context.transaction_fsms:
            ui.label(f"EV charging equipment with this ID is not active. Please try later.")
            ui.timer(30, lambda : ui.navigate.to(f"/d2x_ui/{cp_id}/{evse_id}"))

        else:
            fsm = UIManagerFSMType(uml=ui_manager_uml, 
                                   context=UIManagerContext(charge_point=charge_points[cp_id],
                                                            tx_fsm=charge_points[cp_id].fsm.context.transaction_fsms[evse_id],
                                                            evse=charge_points[cp_id].fsm.context.transaction_fsms[evse_id].context.evse), se_factory=UIManagerFSMState)

            server.ocpp_server_handler.session_pins = session_pins
            fsm.context.cp_evse_id = f"{cp_id}-{evse_id}"
            fsm.load_from_redis()
            cp = charge_points[cp_id]
            state_dependent_frame(cp_id, evse_id, fsm, cp)
            fsm.on(UIManagerFSMEvent.on_state_changed, lambda *vargs: state_dependent_frame.refresh())
            ui.timer(1, fsm.loop)
            ui.button(text="Exit",on_click=lambda:ui.navigate.to(f"/d2x_ui/{cp_id}"))

    with ui.card().classes('fixed-center').bind_visibility_from(semaphore, "acquired", backward=lambda x: not x):
        (ui.label(format_queue_position(semaphore.rank)).bind_text_from(semaphore,
                                                                        "rank",
                                                                              backward=format_queue_position))
        ui.button(text="Exit",on_click=lambda:ui.navigate.to(f"/d2x_ui/{cp_id}"))
    ui.timer(1, lambda : semaphore.acquire())

def format_queue_position(rank):
    return (f"This resource is busy. "
            f"You are in the queue to access the resource. "
            f"Your place in the queue is {rank+1}")


ui.run(host="0.0.0.0", port=8000, favicon="🚘", language="en-GB")
