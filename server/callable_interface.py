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


from abc import abstractmethod, ABC

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ocpp.v201.datatypes import ChargingProfileType
    from util.types import EVSEId


class SupportsBootNotificationForwarding(ABC):

    @abstractmethod
    async def try_forward_data_to_upstream(self):
        pass

class SupportsUpstreamReconnect(ABC):

    @abstractmethod
    async def try_connect_to_upstream(self):
        pass

class SupportsClosingUpstreamDownstream(ABC):

    @abstractmethod
    async def close_upstream_connection(self, *vargs):
        pass
    
    @abstractmethod
    async def close_downstream_connection(self, *vargs):
        pass
    
class CallableInterface(ABC):
    
    @abstractmethod
    async def call_downstream_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):
        pass

    @abstractmethod
    def get_charge_point_id(self) -> str:
        pass

    @abstractmethod
    def is_connected_to_ocpp_upstream(self) -> bool:
        pass


    @abstractmethod
    def is_connected_to_ocpp_downstream(self) -> bool:
        pass
    
    @abstractmethod
    def do_set_charging_profile(self, evse_id: EVSEId, charging_profile : ChargingProfileType) :
        pass