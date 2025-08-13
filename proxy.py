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


import logging
from threading import Thread

import certifi
from redis.connection import ssl
from websockets.sync.server import serve, ServerConnection
from websockets.sync.client import connect, ClientConnection

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def proxify(ss):
    ctx = ssl.create_default_context(cafile=certifi.where())

    def _revtask(_ss : ServerConnection, _cs : ClientConnection):
        while True:
            _message = _cs.recv()
            logger.warning(f"C->S {_message}")
            _ss.send(_message)

    with connect("wss://drive2x.lut.fi/ocpp/proxy/test/0001", ssl=ctx, subprotocols=["ocpp2.0.1"]) as cs:
        revtask = Thread(target=lambda: _revtask(ss, cs))
        revtask.start()
        while True:
            try:
                message = ss.recv()
                logger.warning(f"S->C {message}")
                cs.send(message)
            except:
                break
        revtask.join()

def main():
    with serve(proxify, "0.0.0.0", 9500) as server:
        server.serve_forever()

if __name__ == '__main__':
    main()
