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


import json
from argparse import ArgumentParser

argp = ArgumentParser(description="Simple json list sorter for OCPP dumps")
argp.add_argument("input_filename")
argp.add_argument("output_filename")

args = argp.parse_args()

with open(args.input_filename) as f:
    datain = json.load(f)

def ocpp_key(record):
    cmpnt = record["component"]["name"]
    var = record["variable"]["name"]
    return f"{cmpnt}-{var}"

data_out = sorted(datain, key=ocpp_key)

with open(args.output_filename, "w") as f:
    json.dump(data_out, f)