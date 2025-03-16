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
    task = asyncio.create_task(agent.start(ip, port))
    await agent.play_ready.wait()
    
    asyncio.create_task(send_periodic_chat(agent))
    await agent.chat("hello world")
    await agent.chat("hello2")
    await agent.command("say asfasdfasdf")
    await agent.command(Commands.DIE.value)
    await task
     
if __name__ == "__main__":
    asyncio.run(start())

