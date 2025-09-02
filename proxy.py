import asyncio
import logging

import certifi
from redis.connection import ssl
from websockets.asyncio.server import serve, ServerConnection
from websockets.asyncio.client import connect, ClientConnection

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)




async def proxify(ss):
    ctx = ssl.create_default_context(cafile=certifi.where())

    async def _revtask(_ss : ServerConnection, _cs : ClientConnection):
        while True:
            _message = await _cs.recv()
            logger.warning(f"C->S {_message}")
            await _ss.send(_message)
            await asyncio.sleep(1)

    async with connect("wss://drive2x.lut.fi/ocpp/proxy/test/0001", ssl=ctx, subprotocols=["ocpp2.0.1"]) as cs:
        revtask = asyncio.create_task(_revtask(ss, cs))
        await asyncio.sleep(1)
        while True:
            try:
                message = await ss.recv()
                logger.warning(f"S->C {message}")
                await cs.send(message)
                await asyncio.sleep(1)
            except:
                break
        while revtask is None or not revtask.done():
            await asyncio.sleep(1)
        revtask.result()

async def main():
    async with serve(proxify, "0.0.0.0", 9500) as server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
