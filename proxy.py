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
