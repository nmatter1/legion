import asyncio
from dataclasses import dataclass
import logging
import json
import datetime
from typing import Dict, Tuple

from player import AddEntity 
from chunks import Chunk, read_chunk 
from nbt import read_nbt
from packets import Clientbound 
from connection import Buffer, send, read, Connection

logging.getLogger().setLevel(logging.DEBUG)

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

cache_pool = {}
def block_from_id(block_id: int) -> str:
    blocks = cache_pool.get("blocks", None) 
    
    if blocks is None:
        with open("./blocks.json", "r") as file:
            blocks = json.load(file)
            cache_pool["blocks"] = blocks 
    
    assert blocks is not None, "blocks registry missing"

    for block_name in blocks:
        data = blocks[block_name]
        for state in data["states"]:
            if state["id"] == block_id:
                name_parts = block_name.split(":") # [minecraft:, block_name]
                assert len(name_parts) > 1, "Unsupported version, block names are too small"
                return name_parts[1] 
    
    return f"{block_id}" 

def serialize_packet(p_id: int) -> str:
    return Clientbound.for_id(p_id)

@dataclass
class Vec:
    x: float
    y: float
    z: float

class Player():
    def __init__(self, name="Bot") -> None:
        self.name = name
        self.connection = None
        self.entity_id = 0
        self.health = 20
        self.tps = 20 # ticks per second
        self.dx = 0
        self.is_flying = False
        self.chunks: Dict[Tuple[int, int], Chunk] = {}

    async def on_ground(self):
        return False
    
    async def getBlockBelow(self):
        return 0
    
    def calculate_movement(self, vec: Vec, friction: float) -> Vec:
        return vec 
    
    def get_effective_gravity(self):
        return 0 if self.is_flying else 0.4
    
    def travel(self, vec: Vec):
        block_below = self.getBlockBelow()
        friction: float = 1.0 if self.on_ground() else 1.0 # else block_below.friction()
        dampened: float = friction * 0.91
        #TODO: add potion effects to gravity such as levitation. Add swimming.

        new_vec: Vec = self.calculate_movement(vec, friction)
        y_copy: float = new_vec.y
        y_copy -= self.get_effective_gravity() 
        self.delta_movement = Vec(new_vec.x * dampened, y_copy * 0.98, new_vec.z * dampened)
    
    async def serverbound(self, connection):
        while True:
            logging.debug("walking forwards") 
            await asyncio.sleep(0.05)
    
    async def clientbound(self, connection):
        """ Play state packets. The player is logged in, loaded, and configured """ 
        important = [0x28, 0x0d, 0x4c, 0x4e, 0x58, 0x09, 0x0c, 0x0d, 0x0e] 

        while True:
            p_id, buff = await read(connection)
            if p_id in important:
                logging.debug(Colors.OKGREEN + f"S->C (Play): {serialize_packet(p_id)}" + Colors.ENDC)
            elif p_id not in [0x6b]:
                logging.debug(f"S->C (Play): {serialize_packet(p_id)}")
            
            if p_id == 0x1d:
                handle_disconnect(buff, nbt=True) 
            elif p_id == Clientbound.set_default_spawn_position:
                # set spawn position
                logging.debug("S->C (Play): Set spawn position")
                position = int.from_bytes(buff.read(11), byteorder="big")
                
                x = position >> 38
                y = position << 52 >> 52
                z = position << 26 >> 38
                # ok here
            elif p_id == 0x22: # minecraft:forget_level_chunk
                z = buff.read_int()
                x = buff.read_int() # coordinates divided by 16 rounded down
                if (x, z) in self.chunks:
                    del self.chunks[(x, z)]
            elif p_id == 0x0d: # minecraft:chunk_batch_start
                datetime.datetime.now()
            elif p_id == 0x28: # minecraft:level_chunk_with_light
                chunk: Chunk = read_chunk(block_from_id, buff) 
                self.chunks[(0, 0)] = chunk 
                logging.debug(chunk.block_at(0, 0, 0))
            elif p_id == 0x01: # minecraft:add_entity
                entity: AddEntity = AddEntity.read(buff)
                logging.debug(f"entity_id={entity.entity_id} entity_type={entity.entity_type}")
                logging.debug(f"position={entity.x},{entity.y},{entity.z}") 
            elif p_id == 0x0c: # minecraft:chunk_batch_finished
                batch_size = buff.read_varint()
                assert self.connection is not None
                buffer = Buffer()
                buffer.write_varint(0x09)
                buffer.write_float(9) # chunks per tick
                await send(connection, buffer)
                logging.debug(f"(Chunk): Chunk received and acknowledge batch_size={batch_size}") 
            elif p_id == 0x42: # minecraft:teleport_entity
                logging.debug("S->C (Play): Sync position")
                x = buff.read_double()
                y = buff.read_double()
                z = buff.read_double()
                dx = buff.read_double()
                dy = buff.read_double()
                dz = buff.read_double()
                yaw = buff.read_float()
                pitch = buff.read_float()
                flags = buff.read_int()

                logging.debug("Confirming teleportation...")
                teleport_id = buff.read_varint()
                res = Buffer()
                res.write_varint(0x00)
                res.write_varint(teleport_id)
                await send(connection, res)
                logging.debug("C->S (Play): Teleport confirmed")
                # ok 
            elif p_id == 0x20:
                entity_id = buff.read_varint()
                x = buff.read_double()
                y = buff.read_double()
                z = buff.read_double()
                dx = buff.read_double()
                dy = buff.read_double()
                dz = buff.read_double()
                
                yaw = buff.read_float()
                pitch = buff.read_float()
                on_ground = buff.read_bool()
            elif p_id == 0x2c: # entity log in event
                logging.debug("S->C (Play): Entity Log In")
                self.entity_id = buff.read_int()
                buff.read_bool()
                dim_count = buff.read_varint() # dimension count
                for i in range(dim_count):
                    buff.read_utf()

                buff.read_varint() # max pS->C s
                view_dist = buff.read_varint() # view distance
                logging.debug(f"View distance is set to {view_dist}")
            elif p_id == 0x00: # bundle delimiter
                pass
            elif p_id == 0x09:
                val = buff.read_longlong()
                x = val >> 38;
                y = val << 52 >> 52;
                z = val << 26 >> 38;
                logging.debug(f"S->C (Play): Block Update ({x}, {y}, {z})")
            elif p_id == 0x27:
                keep_alive_id = buff.read_longlong()
                logging.debug(f"keep_alive_id={keep_alive_id}")
                buff = Buffer()
                buff.write_varint(0x1a)
                buff.write_longlong(keep_alive_id) 
                await send(connection, buff)
            elif p_id == 0x62:
                health = buff.read_float()
                logging.debug(f"setting health to {health}")
                if health <= 0:
                    await self.respawn()
                else:
                    self.health = health

    async def connect(self, ip: str, port: int = 25565, timeout=2):
        """
        Connects the player to a server.
        """
        with Connection.create(ip, port) as connection:
            self.connection = connection
            await login(connection, self.name, ip, port)
            await configure(self.connection)
            await self.respawn() 
            #asyncio.create_task(self.update_living()) 
            logging.debug("(Play): Now in play state")
            await self.chat("hello!")
            
            clientbound = asyncio.create_task(self.clientbound(connection))
            serverbound = asyncio.create_task(self.serverbound(connection))
            await asyncio.gather(clientbound, serverbound)  # Run both tasks concurrently
        
    async def _send_status(self, status: int):
        assert self.connection is not None
        buffer = Buffer()
        buffer.write_varint(0x0a)
        buffer.write_varint(status) 
        await send(self.connection, buffer)
    
    async def respawn(self):
        assert self.connection is not None
        await self._send_status(0) # 0 is for respawn status
        self.health = 20
        logging.debug("C->S (Play): Client Action respawn state ready")
    
    async def chat(self, message: str):
        """
        Send a chat message to the console
        TODO: check if this can also send commands
        """
        assert self.connection is not None
        packet = Buffer()
        packet.write_varint(0x07) # minecraft:send_chat_message
        packet.write_utf(message) # message
        packet.write_longlong(0) # timestamp
        packet.write_longlong(0) # salt
        packet.write_bool(False) # true if signature is present
        packet.write_varint(0)  # message count (VarInt)
        acknowledged = 0 
        packet.write(acknowledged.to_bytes(3, 'big'))  # 3 bytes for 20 bits (the last byte will only use 4 bits)
        
        await send(self.connection, packet)
    
def handle_disconnect(packet: Buffer, nbt=False):
    if nbt:
        message = read_nbt(packet)
        logging.error(f"Player disconnected: {message}")
        raise ConnectionResetError(f"{message}") 
    
    packet.read(1) # removes the prefix from the json 
    reason = {"translate": "unknown reason"}

    try:
        reason = json.loads(packet.flush().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logging.error(f"Error parsing JSON: {e}")
    finally:
        logging.error(f"Player disconnected {reason['translate']}")
    
    raise ConnectionResetError(reason['translate'])

async def login(conn: Connection, name: str, ip: str, port: int = 25565):
    """
    C→S: Handshake with Next State set to 2 (login)
    C→S: Login Start
    S→C: Encryption Request
    C→S: Encryption Response
    S→C: Login Success
    C→S: Login Acknowledged
    """
    assert len(name) <= 16, "Username cannot be longer than 16 characters"
    logging.info(f"logging in {name} to {ip}:{port}") 
    
    logging.debug("C->S (Login): Handshake with Next State set to 2 (login)")
    packet = Buffer()
    packet.write_varint(0) # packet id
    logging.debug(" 2")
    packet.write_varint(769) # protocol version (769 for v1.21.4)
    logging.debug(" 3")
    packet.write_utf(ip) # ip address
    logging.debug(" 4")
    packet.write_ushort(port) # port
    logging.debug(" 5")
    packet.write_varint(2) # next state. login state is 2 
    await send(conn, packet)
    
    logging.debug("C->S (Login): Login Start")
    packet = Buffer()
    packet.write_varint(0) #packet id
    packet.write_utf(name) # player's username
    # This is just set to an arbitrary UUID for now because it is not used on vanilla servers
    packet.write(bytes.fromhex("de6078a856ec4cf9b8832a46025ae261")) # UUID of player's username (not used by offline servers)
    await send(conn, packet)
    
    p_id, packet = await read(conn)
    if p_id == 0x00:
        handle_disconnect(packet) 
    logging.debug("S->C (Login): Login Success")
    
    logging.debug("C->S (Login): Login Acknowledged") 
    packet = Buffer()
    packet.write_varint(0x03) # login acknowledgement packet
    await send(conn, packet)
    logging.debug("Logged in. Starting configuration.")

async def configure(connection: Connection):
    configured = False

    while not configured:
        logging.debug("reading")
        p_id, buff = await read(connection) # TODO: read might error and return null
        logging.debug(f"S->C (Configuration): {hex(p_id)}")
        if p_id == 0x01:
            logging.debug("S->C (Configuration): Plugin Message")
        elif p_id == 0x02: 
            logging.debug("S->C (Configuration): Disconnect")
            handle_disconnect(buff) 
        elif p_id == 0x0e:
            logging.debug("S->C (Configuration): Known Packs")
            res = Buffer()
            res.write_varint(int(0x07))
            res.write_varint(0)
            await send(connection, res)
            logging.debug("C->S (Configuration): Known Packs")
        elif p_id == 0x07:
            logging.debug("S->C (Configuration): Identifier Message")
            identifier = buff.read_utf()
            pack_id = buff.read_utf()
        elif p_id == 0x0D:
            logging.debug("S->C (Configuration): Update Tags")
        elif p_id == 0x03:
            logging.debug("S->C (Configuration): Finish Configuration")
            res = Buffer()
            res.write_varint(0x03)
            await send(connection, res)
            logging.debug("C->S (Configuration): Acknowledge Finish Configuration")
            configured = True
