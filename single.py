"""
Example of a single player connecting to an offline server
"""
import logging
from protocol import Player 
import asyncio
import threading
from panel import start_server

async def start(ip: str="127.0.0.1", port: int=25565):
    """

    """
    server = threading.Thread(target=start_server, daemon=True)
    server.start()

    agent = Player(name="operator")
    
    try:
        await agent.connect(ip, port)
    except Exception as e:
        logging.error(e) 

if __name__ == "__main__":
    asyncio.run(start())

