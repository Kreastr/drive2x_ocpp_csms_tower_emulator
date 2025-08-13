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


import dataclasses
import nicegui

@dataclasses.dataclass
class GUI:
    
    _ui : type(nicegui.ui) | None = None
    _app : type(nicegui.app) | None = None
    _background_tasks : type(nicegui.background_tasks) | None = None
    
    @property
    def ui(self) -> type(nicegui.ui):
        assert self._ui is not None
        return self._ui

    @property
    def app(self) -> type(nicegui.app):
        assert self._app is not None
        return self._app
    
    @property
    def background_tasks(self) -> type(nicegui.background_tasks):
        assert self._background_tasks is not None
        return self._background_tasks

gui_info = GUI()