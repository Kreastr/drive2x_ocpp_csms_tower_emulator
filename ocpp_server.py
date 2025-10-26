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


import asyncio
import datetime
import logging
import traceback
from argparse import ArgumentParser
from datetime import timezone

import dateutil.parser
import pytz
import websockets
from ocpp.v201 import call
from ocpp.v201 import call_result
from ocpp.v201.datatypes import ComponentType, VariableType, \
    SetVariableDataType, EVSEType

from nicegui import ui, app, background_tasks

from server.data.car_db import SessionInfo, CAR_DB, CarDetails
from server.data.tx_manager_context import TxManagerContext
from server.transaction_manager.tx_fsm import TxFSMServer
from server.transaction_manager.tx_manager_fsm_type import TxManagerFSMType
from server.ui.nicegui import gui_info
from tx_manager_fsm_enums import TxManagerFSMState

from drive2x_sca_interfaces import SCADataEVs, SCADatum, SetpointRequestResponse, ConnectedEVId, GenericErrorResponse

gui_info._app = app
gui_info._ui = ui
gui_info._background_tasks = background_tasks



from websockets import Subprotocol

from charge_point_fsm_enums import ChargePointFSMEvent, ChargePointFSMState
from server.ocpp_server_handler import redis, session_pins, OCPPServerHandler, charge_points
from server.ui import CPCard
from server.ui.ui_screens import gdpraccepted_screen, new_session_screen, edit_booking_screen, session_confirmed_screen, \
    car_not_connected_screen, car_connected_screen, normal_session_screen, session_unlock_screen, session_end_summary_screen, session_first_start_screen
from uimanager_fsm_enums import UIManagerFSMState, UIManagerFSMEvent
from util import setup_logging, get_slot_start, get_slot_duration, get_app_args
from util.fair_semaphore_redis import FairSemaphoreRedis
from util.types import *

from server.ui.ui_manager import UIManagerFSMType, UIManagerContext, ui_manager_uml
from server.callable_interface import CallableInterface

from pytz import timezone

from pydantic import BaseModel, Field

logger = setup_logging(__name__)
logger.setLevel(logging.DEBUG)

cp_card_container : ui.grid | None = None

#logging.getLogger("websockets.server").setLevel(logging.WARNING)
#logging.getLogger("ocpp").setLevel(logging.WARNING)
#logging.getLogger("websockets.client").setLevel(logging.WARNING)




async def on_connect(websocket):
    logger.warning(f"on client connect {websocket=}")
    cp = OCPPServerHandler("provisional", websocket)

    await get_remote_ip(cp, websocket)

    await cp.fsm.handle(ChargePointFSMEvent.on_start)

    if 0:
        await set_measurement_variables(cp)
    while cp.fsm.current_state != None:
        await asyncio.sleep(1)
    logger.warning("Charge point FSM is done. Closing connection.")
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


async def set_measurement_variables(cp : CallableInterface):
    result: call_result.SetVariables = await cp.call_payload(
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


@app.get("/cp/{cp_id}/set/{component}/{variable}/{value}")
async def events(cp_id : ChargePointId, component: str, variable: str, value: str):
    if cp_id not in charge_points:
        return {"status": "error"}

    cp : OCPPServerHandler = charge_points[cp_id]

    result: call_result.SetVariables = await cp.call_payload(
        call.SetVariables(set_variable_data=[SetVariableDataType(
            attribute_value=value,
            component=ComponentType(name=component),
            variable=VariableType(name=variable))
        ]))

    return {"result": result, "status": "ok"}

@app.get("/cp/{cp_id}/events/")
async def events(cp_id : ChargePointId):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"events": charge_points[cp_id].events}

@app.get("/cp/{cp_id}/reboot")
async def reboot(cp_id : ChargePointId):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].reboot_peer_and_close_connection()}

@app.get("/cp/{cp_id}/transactions")
async def transactions(cp_id : ChargePointId):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"events": charge_points[cp_id].fsm.context.transactions}


@app.get("/cp/{cp_id}/remote_start/{evse_id}")
async def remote_start(cp_id : ChargePointId, evse_id : EVSEId):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].do_remote_start(evse_id)}


@app.get("/cp/{cp_id}/remote_stop/{evse_id}")
async def remote_stop(cp_id : ChargePointId, evse_id : EVSEId):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].do_remote_stop(evse_id)}

@app.get("/cp/{cp_id}/report_full")
async def report_full(cp_id : ChargePointId):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].request_full_report()}

@app.get("/cp/{cp_id}/read_reported_variables")
async def read_report(cp_id : ChargePointId):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": charge_points[cp_id].fsm.context.components}

@app.get("/cp/{cp_id}/setpoint/{value}")
async def setpoint(cp_id : ChargePointId, value : int):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        if value > 8000:
            value = 8000
        if value < -8000:
            value = -8000
        return {"result": await charge_points[cp_id].call_payload(
            call.SetVariables(set_variable_data=[SetVariableDataType(attribute_value=str(value),
                                                                     component=ComponentType(name="V2XChargingCtrlr", instance="1", evse=EVSEType(id=1)),
                                                                     variable=VariableType(name="Setpoint"))]))}

EV_TAGS = {"IOW_LHH_": "iow_luccombe_hall_hotel",
           "D2X_DEMO_": "d2x_ga3_demo",
           "PORTO_APT_": "porto_apt"}

@app.post("/sca_data/setpoints")
async def ev_setpoints(setpoints: SetpointRequestResponse) -> SetpointRequestResponse | GenericErrorResponse:
    if get_slot_start(setpoints.expected_slot_start_time) != setpoints.expected_slot_start_time:
        return GenericErrorResponse(error_message="Expected slot start time is not aligned.")
    if setpoints.expected_slot_start_time < datetime.datetime.now(datetime.timezone.utc):
        return GenericErrorResponse(error_message="Expected slot start time has passed.")
    if get_slot_start(datetime.datetime.now(datetime.timezone.utc), offset=1) != setpoints.expected_slot_start_time:
        return GenericErrorResponse(error_message="Only accepts setpoints for the next time slot.")

    try:
        confirmed = SetpointRequestResponse(site_tag=setpoints.site_tag,
                                            expected_slot_start_time=setpoints.expected_slot_start_time)
        for iid, value in setpoints.values.items():
            cp_id_s, evse_id_s = iid.split(":")
            cp_id = ChargePointId(cp_id_s)
            evse_id = EVSEId(int(evse_id_s))
            if cp_id in charge_points:
                control_allowed = check_control(cp_id, setpoints.site_tag)
    
                if not control_allowed:
                    continue
    
                cp = charge_points[cp_id]
                if evse_id in cp.fsm.context.transaction_fsms:
                    evse = cp.fsm.context.transaction_fsms[evse_id].context.evse
                    evse.setpoint = value
                    cp.clamp_setpoint(evse)
                    confirmed.values[iid] = evse.setpoint
        return confirmed
    except Exception as e:
        return GenericErrorResponse(error_message=traceback.format_exc())


def check_control(cp_id : ChargePointId, site_tag : str):
    control_allowed = False
    for prefix, cp_tag in EV_TAGS.items():
        if site_tag == cp_tag:
            if cp_id.startswith(prefix):
                control_allowed = True
                break
    return control_allowed

SITE_TIMEZONES = {"d2x_ga3_demo": timezone("Europe/Helsinki")}

@app.get("/sca_data/evs/{tag}")
async def sca_data_evs(tag : str) -> SCADataEVs:
    response = SCADataEVs(soc_estimate_valid_at=datetime.datetime.now(datetime.timezone.utc))
    for cp_id, cp in charge_points.items():
        control_allowed = check_control(cp_id, tag)

        if not control_allowed:
            continue

        if cp.fsm.context.online:
            for evse_id, evse_fsm in cp.fsm.context.transaction_fsms.items():
                if evse_fsm.current_state not in [TxManagerFSMState.ready, TxManagerFSMState.charging, TxManagerFSMState.discharging]:
                    continue
                evse_fsm : TxManagerFSMType
                csoc = evse_fsm.context.evse.last_cycle_soc_percent
                rsoc = evse_fsm.context.evse.last_report_soc_percent
                rtime =  evse_fsm.context.evse.last_report_time
                if rsoc is None:
                    continue
                if rtime is None:
                    continue
                if csoc is None:
                    csoc = rsoc
                ctime = get_slot_start(rtime)
                pred_soc = csoc + (rsoc-csoc) / (rtime - ctime).total_seconds() * get_slot_duration()
                sinfo = SessionInfo.model_validate(evse_fsm.context.session_info)

                site_tz : pytz.timezone = SITE_TIMEZONES.get(tag, pytz.utc)

                dept = site_tz.localize(dateutil.parser.parse(sinfo.departure_date + " " + sinfo.departure_time)).astimezone(datetime.timezone.utc)
                car : CarDetails = CAR_DB[sinfo.car_make][sinfo.car_model]
                evid = ConnectedEVId.model_validate({"charge_point_id": cp_id, "evse_id": evse_id})
                response.values[evid] = SCADatum.model_validate({"soc": pred_soc,
                                                                 "tdep": get_slot_start(dept),
                                                                 "usable_battery_capacity_kwh": car.usable_battery_capacity_kwh})
    return response


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
    background_tasks.create_lazy(main(),name="main")
    ui.page_title(f'Drive2X UI - {cp_id}')

    await standard_header_footer(cp_id)
    await styling()

    with (ui.card().classes('fixed-center').style("min-width: 18rem;")):
        if cp_id not in charge_points:
            with ui.row(align_items="center"):
                ui.icon("warning", color='red').classes('text-5xl')
                ui.label(f"Charge Point with this ID is not active. Please try later.")
                ui.timer(30.0, lambda : ui.navigate.to(f"/d2x_ui/{cp_id}"), once=True)

        else:
            with ui.column(align_items="center"):
                evse_ids = list(charge_points[cp_id].fsm.context.transaction_fsms)

                ui.label("Please pick an EV charging outlet to proceed.")
                with ui.column(align_items="center"):
                    for evse_id in evse_ids:
                        with ui.link(target=f"/d2x_ui/{cp_id}/{evse_id}").style("text-decoration: none; color: primary;"):
                            with ui.card():
                                with ui.row(align_items="center"):
                                    ui.icon('outlet', color='primary').classes('text-5xl')
                                    ui.label(f"Outlet {evse_id}").classes('text-4xl text-primary')


async def standard_header_footer(cp_id):
    with ui.header(elevated=True).style('background-color: white').classes('items-center justify-between'):
        ui.image(source="static/d2x_logo_1.svg").classes("w-20")
        timenow()
        ui.timer(1, timenow.refresh)
    with (ui.footer(elevated=True).style('background-color: brand').classes('items-center justify-between text-body2')):
        ui.label(f"Charging station serial number: {cp_id}.")
        ui.label("Operator: Drive2X.")
        ui.label("Contact details: DriVe2X@lut.fi +358 XXX YYY ZZZ")


@ui.refreshable
def timenow():
    tnow = datetime.datetime.now()
    ui.label(f"Current time: {tnow.date()} {tnow.time().replace(microsecond=0)}").style("color: black;")


STATE_SCREEN_MAP = {UIManagerFSMState.new_session: new_session_screen,
                    UIManagerFSMState.gdpraccepted: gdpraccepted_screen,
                    UIManagerFSMState.edit_booking: edit_booking_screen,
                    UIManagerFSMState.evseselect_page: lambda cp_id, *vargs: ui.navigate.to(f"/d2x_ui/{cp_id}"),
                    UIManagerFSMState.session_confirmed: session_confirmed_screen,
                    UIManagerFSMState.car_not_connected: car_not_connected_screen,
                    UIManagerFSMState.car_connected: car_connected_screen,
                    UIManagerFSMState.normal_session: normal_session_screen,
                    UIManagerFSMState.session_unlock: session_unlock_screen,
                    UIManagerFSMState.session_end_summary: session_end_summary_screen,
                    UIManagerFSMState.session_first_start: session_first_start_screen
                    }

@ui.refreshable
def state_dependent_frame(cp_id : ChargePointId, evse_id : EVSEId, fsm : UIManagerFSMType, cp : OCPPServerHandler):
    #ui.label(fsm.current_state)
    #ui.label(cp_id)
    #ui.label(evse_id)
    if fsm.current_state in STATE_SCREEN_MAP:
        STATE_SCREEN_MAP[fsm.current_state](cp_id, evse_id, fsm, cp)



@ui.page("/d2x_ui/{cp_id}/{evse_id}")
async def d2x_ui_evse(cp_id : ChargePointId, evse_id : EVSEId):
    ui.add_head_html('''<script>
    function onResize() {
      emitEvent('body_size', 
      {w: window.innerWidth,
       h: window.innerHeight});
    }
    window.onload = onResize;
    window.onresize = onResize;
    </script>''')

    ui.on('body_size', refresh_on_resize)
    background_tasks.create_lazy(main(),name="main")
    ui.page_title(f'Drive2X UI - {cp_id}/{evse_id}')
    await standard_header_footer(cp_id)
    await styling()
    semaphore = FairSemaphoreRedis(name="page-access-" + cp_id + "-" + str(evse_id), n_users=1, redis=redis, session_timeout=5)
    semaphore.acquire()
    await screen_size_refreshable_block(cp_id, evse_id, semaphore)
    ui.timer(1, lambda : semaphore.acquire())

wheight = 0
wwidth = 0
@ui.refreshable
async def screen_size_refreshable_block(cp_id, evse_id, semaphore):

    if wheight > 700 and wwidth > 380:
        with ui.card(align_items="center").classes('fixed-center ').style(
                "min-width: 20rem; text-align: justify;").bind_visibility_from(semaphore, "acquired"):
            await main_screen_block(cp_id, evse_id)
        with ui.card().classes('fixed-center').bind_visibility_from(semaphore, "acquired", backward=lambda x: not x):
            await pend_semaphore_screen_block(semaphore, cp_id)
    else:
        with ui.row().classes("justify-center full-width"):
            with ui.column(align_items="center").style(
                    "text-align: justify; background: white;").classes("p-5").bind_visibility_from(semaphore, "acquired"):
                await main_screen_block(cp_id, evse_id)
            with ui.column(align_items="center").style(
                    "text-align: justify; background: white;").classes("p-5").bind_visibility_from(semaphore, "acquired", backward=lambda x: not x):
                await pend_semaphore_screen_block(semaphore, cp_id)

def refresh_on_resize(event):
    global wheight
    global wwidth
    logger.error(f"{event.args}")
    wheight = event.args["h"]
    wwidth =  event.args["w"]
    screen_size_refreshable_block.refresh()


async def pend_semaphore_screen_block(semaphore, cp_id):
    with ui.column(align_items="center"):
        with ui.row(align_items="center"):
            ui.icon("clock", color='warning').classes('text-5xl mr-3')
            ui.label(format_queue_position(semaphore.rank)).bind_text_from(semaphore,
                                                                           "rank",
                                                                           backward=format_queue_position)
        ui.separator()
        with ui.row().classes('items-center justify-around'):
            ui.button(text="Exit", on_click=lambda: ui.navigate.to(f"/d2x_ui/{cp_id}"))


async def main_screen_block(cp_id, evse_id):
    if cp_id not in charge_points:
        with ui.row(align_items="center"):
            ui.icon("warning", color='red').classes('text-5xl')
            ui.label(f"Charge Point with this ID is not active. Please try later.")
            ui.timer(30, lambda: ui.navigate.to(f"/d2x_ui/{cp_id}/{evse_id}"), once=True)
    elif evse_id not in charge_points[cp_id].fsm.context.transaction_fsms:
        with ui.row(align_items="center"):
            ui.icon("warning", color='red').classes('text-5xl mr-3')
            ui.label(f"EV charging equipment with this ID is not active. Please try later.")
            ui.timer(30, lambda: ui.navigate.to(f"/d2x_ui/{cp_id}/{evse_id}"), once=True)

    else:
        fsm = UIManagerFSMType(uml=ui_manager_uml,
                               context=UIManagerContext(charge_point=charge_points[cp_id],
                                                        tx_fsm=charge_points[cp_id].fsm.context.transaction_fsms[
                                                            evse_id],
                                                        evse=charge_points[cp_id].fsm.context.transaction_fsms[
                                                            evse_id].context.evse), se_factory=UIManagerFSMState)

        fsm.context.session_pins = session_pins
        fsm.context.cp_evse_id = f"{cp_id}-{evse_id}"
        fsm.load_from_redis()
        cp = charge_points[cp_id]
        with ui.column(align_items="center"):
            state_dependent_frame(cp_id, evse_id, fsm, cp)
            fsm.on(UIManagerFSMEvent.on_state_changed, lambda *vargs: state_dependent_frame.refresh())
            ui.timer(1, fsm.loop)
            ui.separator()
            with ui.row(align_items="center").classes('items-center justify-around'):
                ui.button(text="Exit", on_click=lambda: ui.navigate.to(f"/d2x_ui/{cp_id}"))


async def styling():
    ui.colors(brand="#2FAC66", primary="#2FAC66", dark="#3b4a3f", secondary="#00afc1", accent="#00afc1", info="#00798b", positive="#9eb0a2")
    ui.query("body").style("background-color: #d4fade;")


def format_queue_position(rank):
    return (f"This resource is busy. "
            f"You are in the queue to access the resource. "
            f"Your place in the queue is {rank+1}")

if __name__ in {"__main__", "__mp_main__"}:
    args = get_app_args()
    ui.run(host=args.ui_host, port=args.ui_port, favicon="static/cropped-Favicon-1-192x192.png", language="en-GB")
