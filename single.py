"""
Example of a single player connecting to an offline server
"""
from enum import Enum
from protocol import CraftPlayer
import asyncio

async def send_periodic_chat(agent):
    """Send a chat message every second"""
    while True:
        await asyncio.sleep(1)
        #await agent.chat("hello world")

class Commands(Enum):
    DIE = "kill @s"
    HEAL = "heal 20"

async def start(ip: str="127.0.0.1", port: int=25565):
    """

    """
    agent = CraftPlayer(name="operator")
    
    try:
        await agent.connect(ip, port)
    except ConnectionResetError as e:
        print("Disconnected ", e)

if __name__ == "__main__":
    asyncio.run(start())

