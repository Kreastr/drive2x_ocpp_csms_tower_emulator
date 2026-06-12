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
import datetime

from beartype import beartype


from proxy_connection_fsm_enums import ProxyConnectionFSMEvent, ProxyConnectionFSMCondition

from .proxy_connection_context import ProxyConnectionContext
from .proxy_connection_fsm_type import ProxyConnectionFSMType, proxy_connection_uml, ProxyConnectionFSMState

HEARTBEAT_TIMEOUT = 120

class ProxyConnectionFSM(ProxyConnectionFSMType):
    
    @beartype
    def __init__(self, context : ProxyConnectionContext, *vargs, **kwargs):
        super().__init__(proxy_connection_uml,
                         *vargs,
                         se_factory=ProxyConnectionFSMState,
                         context=context,
                         **kwargs)

        self.apply_to_all_conditions(ProxyConnectionFSMCondition.if_heartbeat_timeout, callback=self.if_heartbeat_timeout)
        self.on(ProxyConnectionFSMState.connected.on_enter, self.start_new_heartbeat_timer)
        self.on(ProxyConnectionFSMState.connected.on_enter, self.handle_delayed_boot_notifications)
        self.on(ProxyConnectionFSMState.autonomous_loop.on_enter, self.start_new_heartbeat_timer)
        self.on(ProxyConnectionFSMState.autonomous_loop.on_loop, self.try_connect_to_upstream)
        

    async def start_new_timeout_timer(self):
        ctxt : ProxyConnectionContext = self.context
        ctxt.timeout_timer_start = datetime.datetime.now()

    async def handle_delayed_boot_notifications(self):
        ctxt : ProxyConnectionContext = self.context
        ctxt.charge_point_interface.try_forward_data_to_upstream()
        
    async def try_connect_to_upstream(self):
        ctxt : ProxyConnectionContext = self.context
        ctxt.charge_point_interface.try_connect_to_upstream()
        
    async def start_new_heartbeat_timer(self):
        ctxt : ProxyConnectionContext = self.context
        ctxt.timeout_timer_start = datetime.datetime.now()

    async def if_heartbeat_timeout(self, *vargs, **kwargs):
        ctxt: ProxyConnectionContext = self.context
        if (datetime.datetime.now() - ctxt.timeout_timer_start).total_seconds() > HEARTBEAT_TIMEOUT:
            return True
        return False
        
