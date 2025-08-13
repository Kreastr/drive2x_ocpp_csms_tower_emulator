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


charge_point_uml = """@startuml
[*] --> Created
Created --> Unknown : on start
Unknown --> Identified : on serial number obtained
Unknown --> Rejected : on serial number not obtained
Unknown --> Booted : on boot notification 
Rejected --> [*]
Identified --> Booted : on boot notification
Identified --> Booted : on cached boot notification
Identified --> Failed : on boot timeout
Failed --> [*]
Booted --> RunningTransaction : on transaction_manager request
Booted --> Identified : on boot notification
RunningTransaction --> RunningTransaction
RunningTransaction --> Booted : if no active transactions
Booted --> Closing : on reboot confirmed
Closing --> [*]
@enduml
"""

"""
Booted --> Failed : if heartbeat timeout
Unknown --> Failed : if heartbeat timeout
Identified --> Failed : if heartbeat timeout
RunningTransaction --> Failed : if heartbeat timeout
"""