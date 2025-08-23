import asyncio
import logging
from abc import ABCMeta, abstractmethod
from datetime import datetime, timedelta
from typing import cast, Self
from uuid import uuid4

import websockets
from nicegui.binding import BindableProperty, bind_from
from nicegui.element import Element
from ocpp.routing import on
from ocpp.v16.enums import RegistrationStatus
from ocpp.v201 import ChargePoint, call
from ocpp.v201 import call_result
from ocpp.v201.call import GetVariables
from ocpp.v201.datatypes import GetVariableDataType, ComponentType, IdTokenInfoType, IdTokenType, VariableType, \
    SetVariableDataType, EVSEType
from ocpp.v201.enums import Action, RegistrationStatusEnumType, AuthorizationStatusEnumType, ReportBaseEnumType, \
    ResetEnumType, IdTokenEnumType, GetVariableStatusEnumType
from logging import getLogger

from nicegui import ui, app, background_tasks, ElementFilter, binding
from typing import Any

@binding.bindable_dataclass
class ConnectorStatus:
    connector_id : int = -1
    connector_status : str = "Unknown"


formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

cp_card_container : ui.grid | None = None
charge_points : dict[str, Any] = dict()
charge_point_cards : dict[str, Any] = dict()


ui.add_css('''
    .online {
        background: green;
    }
    .offline {
        background: red;
    }
''')

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.lastResort.setFormatter(formatter)
def get_time_str():
    return datetime.now().isoformat()




class OCPPServerHandler(ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.booted_ok = False
        self.events = []
        self.transactions = set()
        self.current_tx = None
        self.boot_notifications = []
        self.remote_ip = None
        self.online = False
        self.connectors = dict()
        self.shutdown = False
        self.tx_status = ""
        self.timeout = datetime.now()
        self.onl_task = asyncio.create_task(self.online_status_task())

    async def online_status_task(self):
        while not self.shutdown:
            await asyncio.sleep(1)
            if self.timeout < datetime.now():
                self.online = False


    @on(Action.boot_notification)
    async def on_boot_notification(self,  charging_station, reason, *vargs, **kwargs):
        self.booted_ok = True
        self.log_event(("boot_notification", (charging_station, reason, vargs, kwargs)))
        self.boot_notifications.append( (charging_station, reason, vargs, kwargs) )
        logger.warning(f"id={self.id} boot_notification {charging_station=} {reason=} {vargs=} {kwargs=}")
        #asyncio.create_task(self.call(GetVariables([GetVariableDataType(ComponentType.)])))
        return call_result.BootNotification(
            current_time=get_time_str(),
            interval=10,
            status=RegistrationStatusEnumType.accepted
        )

    @on(Action.status_notification)
    async def on_status_notification(self, **data):
        self.log_event(("status_notification", (data)))
        logger.warning(f"id={self.id} on_status_notification {data=}")
        conn_status = ConnectorStatus(**data)

        if conn_status.connector_id not in self.connectors:
            self.connectors[conn_status.connector_id] = conn_status
        else:
            self.connectors[conn_status.connector_id].connector_status = conn_status.connector_status
        return call_result.StatusNotification(
        )

    @on(Action.heartbeat)
    async def on_heartbeat(self, **data):
        self.log_event(("heartbeat", (data)))
        logger.warning(f"id={self.id} on_heartbeat {data=}")
        self.timeout = datetime.now() + timedelta(seconds=30)
        self.online = True
        return call_result.Heartbeat(
            current_time=get_time_str()
        )

    @on(Action.meter_values)
    async def on_meter_values(self, **data):
        self.log_event(("meter_values", (data)))
        logger.warning(f"id={self.id} on_meter_values {data=}")
        return call_result.MeterValues(
        )

    @on(Action.authorize)
    async def on_authorize(self, **data):
        self.log_event(("authorize", (data)))
        logger.warning(f"id={self.id} on_authorize {data=}")
        return call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted))

    @on(Action.transaction_event)
    async def on_transaction_event(self, **data):
        self.log_event(("transaction_event", (data)))
        logger.warning(f"id={self.id} on_transaction_event {data=}")
        response = dict()
        if "id_token_info" in data:
            response.update(dict(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted)))
        if "transaction_info" in data:
            if "transaction_id" in data["transaction_info"]:
                self.transactions |= {data["transaction_info"]["transaction_id"]}
                self.current_tx = data["transaction_info"]["transaction_id"]
        #self.tx_status 
        return call_result.TransactionEvent(**response)

    @on(Action.notify_report)
    async def on_notify_report(self, **data):
        self.log_event(("notify_report", (data)))
        logger.warning(f"id={self.id} on_notify_report {data=}")
        return call_result.NotifyReport()

    def log_event(self, event_data):
        self.events.append(event_data)

    async def close_connection(self):
        self.shutdown = True
        self.online = False 
        await self._connection.close()
        await self.onl_task




async def on_connect(websocket):
    logger.warning(f"on client connect {websocket=}")
    cp = OCPPServerHandler("provisional", websocket)
    #await cp.start()
    start = cp.start()
    start_task = asyncio.create_task(start)

    result : call_result.GetVariables = await cp.call(call.GetVariables([GetVariableDataType(component=ComponentType(name="ChargingStation"),
                                                                  variable=VariableType(name="SerialNumber"))]))
    logger.warning(f"Charger S/N variable {result=}")
    if result.get_variable_result[0]["attribute_status"] != GetVariableStatusEnumType.accepted:
        cp.log_event("Failed to read CP serial number. Refusing to operate.")
        await cp.close_connection()
        return


    cp.id = result.get_variable_result[0]["attribute_value"]
    charge_points[cp.id] = cp
    if "X-Real-IP" in websocket.request.headers:
        real_ip = websocket.request.headers["X-Real-IP"]
    else:
        real_ip = websocket.remote_address[0]
    cp.remote_ip = real_ip
    for client in app.clients('/'):
        with client:
            for old in ElementFilter(kind=CPCard, marker=cp.id):
                old.delete()
            for grid in ElementFilter(kind=ui.grid,marker="cp_card_container"):
                with grid:
                    CPCard(cp).mark(cp.id)

    await set_measurement_variables(cp)
    while not start_task.done():
        await asyncio.sleep(1)
    await cp.close_connection()
    print("start_task.result",start_task.result())


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


def time_based_id():
    return int((datetime.now() - datetime(2025, 1, 1)).total_seconds() * 10)


async def main():
    logging.warning("main start")
    server = await websockets.serve(on_connect, '0.0.0.0', 9000, subprotocols=['ocpp2.0.1'])
    logging.warning("main server ready")
    await server.serve_forever()
    logging.warning("main exit")

@app.get("/cp")
async def index():
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
        return {"result": await charge_points[cp_id].call(call.Reset(type=ResetEnumType.immediate))}

@app.get("/cp/{cp_id}/transactions")
async def transactions(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"events": charge_points[cp_id].transactions}

async def do_remote_start(cp_id, evse_id):
    await charge_points[cp_id].call(
            call.RequestStartTransaction(evse_id=evse_id,
                                         remote_start_id=time_based_id(),
                                         id_token=IdTokenType(id_token=str(uuid4()), type=IdTokenEnumType.central)))

@app.get("/cp/{cp_id}/remote_start")
async def remote_start(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await do_remote_start(cp_id, 1)}


@app.get("/cp/{cp_id}/remote_stop/{transaction_id}")
async def remote_stop(cp_id : str, transaction_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].call(
            call.RequestStopTransaction(transaction_id=transaction_id))}

@app.get("/cp/{cp_id}/report_full")
async def report_full(cp_id : str):
    if cp_id not in charge_points:
        return {"status": "error"}
    else:
        return {"result": await charge_points[cp_id].call(
            call.GetBaseReport(request_id=time_based_id(),
                               report_base=ReportBaseEnumType.full_inventory))}


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




class CPCard(Element):
    online = BindableProperty(
        on_change=lambda sender, value: cast(Self, sender)._handle_online_change(value))

    def __init__(self, cp, **kwargs):
        super().__init__(tag="div")
        self.cp = cp
        self.state = dict(id="provisional")
        self.state.update(kwargs)
        self.card = ui.card()
        self.bind_online_from(self.cp, "online")
        self._handle_online_change(self.cp.online)
        with self.card:
            ui.label("ID")
            ui.label().bind_text(self.cp, "id")
            ui.label("Remote IP")
            ui.label().bind_text(self.cp, "remote_ip")
            ui.button("Remote Start", on_click=lambda : do_remote_start(self.cp.id, 1))

    def bind_online_from(self, var, name):
        bind_from(self_obj=self, self_name="online",
                  other_obj=var, other_name=name)

    def _handle_online_change(self, card_online_status):
        logger.warning(f"online changes {card_online_status}")
        self.card.classes(remove="bg-green bg-red")
        self.card.classes(add="bg-green" if card_online_status else "bg-red")
        self.card.update()


@ui.page("/")
async def index():
    background_tasks.create_lazy(main(),name="main")
    ui.label(text="Charge Point status")
    with ui.grid().mark("cp_card_container"):
        for cpid in charge_points:
            CPCard(charge_points[cpid]).mark("")
ui.run(host="0.0.0.0", port=8000)
