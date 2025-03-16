"""
Example of creating multiple bots and joining a sever

IMPORTANT: Server must be in offline mode
"""
from protocol import CraftPlayer
import asyncio
from faker import Faker

async def start(ip: str="127.0.0.1", port: int=25565):
    """

    """
    username_gen = Faker()
    
    agents = [CraftPlayer(name=username_gen.user_name()) for _ in range(10)]
    
    await asyncio.gather(*(agent.connect(ip, port) for agent in agents))

if __name__ == "__main__":
    asyncio.run(start())

