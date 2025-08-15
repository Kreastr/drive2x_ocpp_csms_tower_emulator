import asyncio
import logging
from datetime import datetime

import websockets
from ocpp.routing import on
from ocpp.v16.enums import RegistrationStatus
from ocpp.v201 import ChargePoint, call
from ocpp.v201 import call_result
from ocpp.v201.call import GetVariables
from ocpp.v201.datatypes import GetVariableDataType, ComponentType, IdTokenInfoType
from ocpp.v201.enums import Action, RegistrationStatusEnumType, AuthorizationStatusEnumType, ReportBaseEnumType
from logging import getLogger

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_time_str():
    return datetime.now().isoformat()


class OCPPServerHandler(ChargePoint):

    @on(Action.boot_notification)
    async def on_boot_notification(self,  charging_station, reason, *vargs, **kwargs):
        logger.warning(f"id={self.id} boot_notification {charging_station=} {reason=} {vargs=} {kwargs=}")
        #asyncio.create_task(self.call(GetVariables([GetVariableDataType(ComponentType.)])))
        return call_result.BootNotification(
            current_time=get_time_str(),
            interval=10,
            status=RegistrationStatusEnumType.accepted
        )

    @on(Action.status_notification)
    async def on_status_notification(self, **data):
        logger.warning(f"id={self.id} on_status_notification {data=}")
        return call_result.StatusNotification(
        )

    @on(Action.heartbeat)
    async def on_heartbeat(self, **data):
        logger.warning(f"id={self.id} on_heartbeat {data=}")
        return call_result.Heartbeat(
            current_time=get_time_str()
        )

    @on(Action.meter_values)
    async def on_meter_values(self, **data):
        logger.warning(f"id={self.id} on_meter_values {data=}")
        return call_result.MeterValues(
        )

    @on(Action.authorize)
    async def on_authorize(self, **data):
        logger.warning(f"id={self.id} on_authorize {data=}")
        return call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted))

    @on(Action.transaction_event)
    async def on_transaction_event(self, **data):
        logger.warning(f"id={self.id} on_transaction_event {data=}")
        response = dict()
        if "id_token_info" in data:
            response.update(dict(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted)))
        return call_result.TransactionEvent(**response)

    @on(Action.notify_report)
    async def on_notify_report(self, **data):
        logger.warning(f"id={self.id} on_notify_report {data=}")
        return call_result.NotifyReport()


async def on_connect(websocket):
    logger.warning(f"on client connect {websocket=}")
    cp = OCPPServerHandler("same_id", websocket)
    asyncio.create_task(cp.start())
    await asyncio.sleep(30)
    await cp.call(call.GetBaseReport(request_id=int((datetime.now()-datetime(2025,1,1)).total_seconds()*10),
                                     report_base=ReportBaseEnumType.configuration_inventory))

async def main():
    logging.warning("main start")
    server = await websockets.serve(on_connect, '0.0.0.0', 9000, subprotocols=['ocpp2.0.1'])
    logging.warning("main server ready")
    await server.serve_forever()
    logging.warning("main exit")


if __name__ == '__main__':
    asyncio.run(main())
