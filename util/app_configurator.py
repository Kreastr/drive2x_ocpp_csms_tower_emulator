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
from typing import Generic
from typing import TypeVar

T = TypeVar("T")

class ConfigNotReadyException(Exception):
    pass


class ConfigRedefinedException(Exception):
    pass


class Configurator(Generic[T]):
    _CONFIG: T | None = None

    @classmethod
    def get_global_config(cls) -> T:
        if cls._CONFIG is None:
            raise ConfigNotReadyException("App configuration has not been loaded yet.")
        return cls._CONFIG

    @classmethod
    def set_global_config(cls, new_config: T):
        if cls._CONFIG is not None:
            raise ConfigRedefinedException("Global config can should be set once. "
                                           "Modify config fields directly if you need to adjust configuration at runtime.")

        cls._CONFIG = new_config