import traceback
from typing import cast, Self

from beartype import beartype
from nicegui import ui
from nicegui.binding import BindableProperty, bind_from
from nicegui.element import Element

from server.ocpp_server_handler import charge_points
from server.charge_point_model import ChargePointFSMType
from server.data import ChargePointContext
from util.types import EVSEId

import logging
from logging import getLogger

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
