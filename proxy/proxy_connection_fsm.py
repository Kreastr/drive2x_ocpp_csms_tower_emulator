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

from beartype import beartype


from proxy_connection_fsm_enums import ProxyConnectionFSMEvent, ProxyConnectionFSMCondition

from .proxy_connection_context import ProxyConnectionContext
from .proxy_connection_fsm_type import ProxyConnectionFSMType, proxy_connection_uml, ProxyConnectionFSMState


class ProxyConnectionFSM(ProxyConnectionFSMType):
    
    @beartype
    def __init__(self, context : ProxyConnectionContext ):
        super().__init__(proxy_connection_uml,
                         se_factory=ProxyConnectionFSMState,
                         context=context)
        
        self.apply_to_all_conditions(ProxyConnectionFSMCondition.if_new_state_timeout, callback=lambda *vargs, **kwargs: False)
        self.on(ProxyConnectionFSMState.new.on_enter, self.start_new_timeout_timer)
        

    @staticmethod
    def if_charge_setpoint(context : ProxyConnectionContext, other):
        return context.evse.setpoint > 0
    
    async def start_new_timeout_timer(self):
        self.context 