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

>>> import json
>>> from camel_converter import dict_to_camel
>>> data='{"connector_id": 1, "transaction_id": 282683992, "meter_value": [{"timestamp": "2025-11-26T13:20:51.934Z", "sampled_value": [{"unit": "Wh", "value": 0, "location": "Outlet", "measurand": "Energy.Active.Import.Register"}, {"unit": "W", "value": 180000, "location": "Outlet", "measurand": "Power.Active.Import"}, {"unit": "W", "value": 180000, "location": "Outlet", "measurand": "Power.Offered"}, {"unit": "Percent", "value": 19.5444, "location": "EV", "measurand": "SoC"}]}]}'
>>> jdata = dict_to_camel(json.loads(data))
>>> jdata
{'connectorId': 1, 'transactionId': 282683992, 'meterValue': [{'timestamp': '2025-11-26T13:20:51.934Z', 'sampledValue': [{'unit': 'Wh', 'value': 0, 'location': 'Outlet', 'measurand': 'Energy.Active.Import.Register'}, {'unit': 'W', 'value': 180000, 'location': 'Outlet', 'measurand': 'Power.Active.Import'}, {'unit': 'W', 'value': 180000, 'location': 'Outlet', 'measurand': 'Power.Offered'}, {'unit': 'Percent', 'value': 19.5444, 'location': 'EV', 'measurand': 'SoC'}]}]}
>>> MeterValuesRequest.model_validate(jdata)
MeterValuesRequest(connectorId=1, transactionId=282683992, meterValue=[MeterValue(timestamp=datetime.datetime(2025, 11, 26, 13, 20, 51, 934000, tzinfo=TzInfo(UTC)), sampledValue=[SampledValue(value=0, context=None, format=None, measurand=<Measurand.energy_active_import_register: 'Energy.Active.Import.Register'>, phase=None, location=<Location.outlet: 'Outlet'>, unit=<UnitOfMeasure.wh: 'Wh'>), SampledValue(value=180000, context=None, format=None, measurand=<Measurand.power_active_import: 'Power.Active.Import'>, phase=None, location=<Location.outlet: 'Outlet'>, unit=<UnitOfMeasure.w: 'W'>), SampledValue(value=180000, context=None, format=None, measurand=<Measurand.power_offered: 'Power.Offered'>, phase=None, location=<Location.outlet: 'Outlet'>, unit=<UnitOfMeasure.w: 'W'>), SampledValue(value=19.5444, context=None, format=None, measurand=<Measurand.soc: 'SoC'>, phase=None, location=<Location.ev: 'EV'>, unit=<UnitOfMeasure.percent: 'Percent'>)])])

"""
import datetime
from typing import Annotated, Optional

from ocpp.v16.enums import ReadingContext, ValueFormat, Measurand, Phase, Location, UnitOfMeasure
from pydantic import BaseModel, StringConstraints

class SampledValue(BaseModel):
    value : str | int | float
    context : Optional[ReadingContext] = None
    format : Optional[ValueFormat] = None
    measurand : Optional[Measurand] = None
    phase : Optional[Phase] = None
    location : Optional[Location] = None
    unit : Optional[UnitOfMeasure] = None

class MeterValue(BaseModel):
    timestamp : datetime.datetime
    sampledValue : list[SampledValue]


class MeterValuesRequest(BaseModel):
    connectorId : int
    transactionId  : Optional[int] = None
    meterValue : list[MeterValue]
