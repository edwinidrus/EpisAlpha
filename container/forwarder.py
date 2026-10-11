#!/usr/bin/env python3
"""Fixed-target TCP forwarder for the worker network (M3-T04). Stdlib only.

    python forwarder.py 8080=172.17.0.1:41234 8081=172.17.0.1:41235

The Hermes worker sits on an internal Docker network with no route anywhere. This forwarder is
the only other member of that network. It accepts on the listed ports and forwards each one to
exactly one fixed host endpoint (the relay, the MCP tool server). It reads no request content
and can be told no new destination, so the worker gains no general egress through it.
"""

import asyncio
import sys
from collections.abc import Awaitable, Callable

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        writer.close()


def handler(host: str, port: int) -> Handler:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
        except OSError:
            writer.close()
            return
        await asyncio.gather(pipe(reader, upstream_writer), pipe(upstream_reader, writer))

    return handle


async def main(routes: list[str]) -> None:
    servers = []
    for route in routes:
        listen, target = route.split("=", 1)
        host, port = target.rsplit(":", 1)
        server = await asyncio.start_server(handler(host, int(port)), "0.0.0.0", int(listen))
        servers.append(server)
    print("forwarding", routes, flush=True)
    await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
