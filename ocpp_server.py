import asyncio
import logging
from datetime import datetime
from uuid import uuid4

import websockets
from ocpp.routing import on
from ocpp.v16.enums import RegistrationStatus
from ocpp.v201 import ChargePoint, call
from ocpp.v201 import call_result
from ocpp.v201.call import GetVariables
from ocpp.v201.datatypes import GetVariableDataType, ComponentType, IdTokenInfoType, IdTokenType, VariableType, \
    SetVariableDataType, EVSEType
from ocpp.v201.enums import Action, RegistrationStatusEnumType, AuthorizationStatusEnumType, ReportBaseEnumType, \
    ResetEnumType, IdTokenEnumType
from logging import getLogger
from fastapi import FastAPI

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

def get_time_str():
    return datetime.now().isoformat()


class OCPPServerHandler(ChargePoint):

    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.booted_ok = False
        self.events = []
        self.transactions = set()

    @on(Action.boot_notification)
    async def on_boot_notification(self,  charging_station, reason, *vargs, **kwargs):
        self.booted_ok = True
        self.log_event(("boot_notification", (charging_station, reason, vargs, kwargs)))
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
        return call_result.StatusNotification(
        )

    @on(Action.heartbeat)
    async def on_heartbeat(self, **data):
        self.log_event(("heartbeat", (data)))
        logger.warning(f"id={self.id} on_heartbeat {data=}")
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
        if "transactionId" in data:
            self.transactions |= {data["transactionId"]}
        return call_result.TransactionEvent(**response)

    @on(Action.notify_report)
    async def on_notify_report(self, **data):
        self.log_event(("notify_report", (data)))
        logger.warning(f"id={self.id} on_notify_report {data=}")
        return call_result.NotifyReport()

    def log_event(self, event_data):
        self.events.append(event_data)


latest_cp : OCPPServerHandler | None = None


async def on_connect(websocket):
    global latest_cp
    logger.warning(f"on client connect {websocket=}")
    cp = OCPPServerHandler("same_id", websocket)
    latest_cp = cp
    #await cp.start()
    start = cp.start()
    start_task = asyncio.create_task(start)

    result = await cp.call(call.GetVariables([GetVariableDataType(component=ComponentType(name="ChargingStation"),
                                                                  variable=VariableType(name="SerialNumber"))]))
    logger.warning(f"Charger S/N variable {result=}")
    result = await latest_cp.call(
        call.SetVariables(set_variable_data=[SetVariableDataType(attribute_value="Energy.Active.Import.Register,Energy.Active.Export.Register,SoC",
                                                                 component=ComponentType(name="AlignedDataCtrlr"),
                                                                 variable=VariableType(name="Measurands"))]))
    logger.warning(f"Charger measurands set {result=}")
    while not start_task.done():
        await asyncio.sleep(1)
    print("start_task.result",start_task.result())


def time_based_id():
    return int((datetime.now() - datetime(2025, 1, 1)).total_seconds() * 10)


async def main():
    logging.warning("main start")
    server = await websockets.serve(on_connect, '0.0.0.0', 9000, subprotocols=['ocpp2.0.1'])
    logging.warning("main server ready")
    await server.serve_forever()
    logging.warning("main exit")

app = FastAPI()

@app.get("/")
async def index():
    if latest_cp is None:
        return {"status": "error"}
    else:
        return {"status": "ready"}

@app.get("/events")
async def index():
    if latest_cp is None:
        return {"status": "error"}
    else:
        return {"events": latest_cp.events}

@app.get("/reboot/{cp_id}")
async def reboot(cp_id : str):
    if latest_cp is None:
        return {"status": "error"}
    else:
        return {"result": await latest_cp.call(call.Reset(type=ResetEnumType.immediate))}

@app.get("/transactions")
async def transactions():
    if latest_cp is None:
        return {"status": "error"}
    else:
        return {"events": latest_cp.transactions}

@app.get("/remote_start")
async def remote_start():
    if latest_cp is None:
        return {"status": "error"}
    else:
        return {"result": await latest_cp.call(
            call.RequestStartTransaction(evse_id=1,
                                         remote_start_id=time_based_id(),
                                         id_token=IdTokenType(id_token=str(uuid4()), type=IdTokenEnumType.central)))}


@app.get("/remote_stop/{transaction_id}")
async def remote_stop(transaction_id : str):
    if latest_cp is None:
        return {"status": "error"}
    else:
        return {"result": await latest_cp.call(
            call.RequestStopTransaction(transaction_id=transaction_id))}

@app.get("/report_full")
async def report_full():
    if latest_cp is None:
        return {"status": "error"}
    else:
        return {"result": await latest_cp.call(
            call.GetBaseReport(request_id=time_based_id(),
                               report_base=ReportBaseEnumType.full_inventory))}


@app.get("/setpoint/{value}")
async def setpoint(value : int):
    if latest_cp is None:
        return {"status": "error"}
    else:
        if value > 4000:
            value = 4000
        if value < -2000:
            value = -2000
        return {"result": await latest_cp.call(
            call.SetVariables(set_variable_data=[SetVariableDataType(attribute_value=str(value),
                                                                     component=ComponentType(name="V2XChargingCtrlr", instance="1" , evse=EVSEType(id=1)),
                                                                     variable=VariableType(name="Setpoint"))]))}

asyncio.create_task(main())

