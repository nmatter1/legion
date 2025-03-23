import asyncio
import enum
from mcproto.buffer import Buffer
from mcproto.connection import TCPAsyncConnection
from mcproto.protocol.base_io import StructFormat
import logging
import math
from dataclasses import dataclass
import json

logging.getLogger().setLevel(logging.DEBUG)
cache_pool = {}

def serialize_packet(p_id: int) -> str:
    packets = cache_pool.get("packets", None) 
    
    if packets is None:
        try:
            with open("./packets.json", "r") as file:
                packets = json.load(file)
                cache_pool["packets"] = packets
        except Exception as e:
            logging.error("could not read packets information")
    
    pool = packets["play"]["clientbound"]
    for packet in pool:
        if pool[packet]["protocol_id"] == p_id:
            return f"{packet} id={hex(p_id)}"

    return f"{hex(p_id)}" 

@dataclass
class Position():
    x: float 
    y: float 
    z: float 

@dataclass
class Velocity():
    dx: float 
    dy: float 
    dz: float 

@dataclass
class VisibleEntity():
    """
    A Visibile Entity is any entity that is within the players view distance
    An entity could exist in the world that the player has not loaded
    """
    e_id: int
    position: Position

class CraftPlayer():
    def __init__(self, name="Bot") -> None:
        self.name = name
        self.position = Position(0, 0, 0)
        self.velocity = Velocity(0, 0, 0)
        self.connection = None
        self.lock = asyncio.Lock()
        self.entity_id = 0
        self.health = 20    
    
    async def chat(self, message: str):
        """
        Send a chat message to the console
        TODO: check if this can also send commands
        """
        assert self.connection is not None
        packet = Buffer()
        packet.write_varint(0x07)
        packet.write_utf(message) # message
        packet.write_value(StructFormat.LONGLONG, 0) #timestamp
        packet.write_value(StructFormat.LONGLONG, 0) #salt
        packet.write_value(StructFormat.BOOL, False) #whether signature is present
        packet.write_varint(0)  # message count (VarInt)
       
        # Write the acknowledged messages (Fixed BitSet of 20 bits, here all zeros to mean no messages acknowledged)
        acknowledged = 0  # 20-bit field (bit set), using 0 for simplicity (no acknowledgments)
        packet.write(acknowledged.to_bytes(3, 'big'))  # 3 bytes for 20 bits (the last byte will only use 4 bits)
        
        await send(self.connection, packet)

    async def _status(self, status: int):
        """
        Sets the player status
        
        Args:
            status (int): 0 performs respawn and is sent when the client is 
                ready to respawn after death while 1 is sent when the client
                opens the Statistics menu.
        """
        assert self.connection is not None, "Not connected"
        buffer = Buffer()
        buffer.write_varint(status) 
        await send(self.connection, buffer)
        logging.debug("C->S (Play): Client Action respawn state ready")
    
    async def swing(self):
        """
        Swings the left arm of the player. Does not deal damage to entities
        """
        assert self.connection is not None
        buffer = Buffer()
        buffer.write_varint(int(0x36))
        buffer.write_varint(0)
        await send(self.connection, buffer)
    
    async def _handle(self, connection, buff: Buffer, p_id):
        """ Play state packets. The player is logged in, loaded, and configured """ 
        if p_id == 0x5b:
            # set spawn position
            logging.debug("S->C (Play): Set spawn position")
            position = int.from_bytes(buff.read(11), byteorder="big")
            
            x = position >> 38
            y = position << 52 >> 52
            z = position << 26 >> 38
            # ok here
        elif p_id == 0x42:
            # Synchronize player position
            logging.debug("S->C (Play): Sync position")
            async with self.lock:
                self.velocity = Velocity(0, 0, 0) 
                self.position.x = buff.read_value(StructFormat.DOUBLE)
                self.position.y = buff.read_value(StructFormat.DOUBLE)
                self.position.z = buff.read_value(StructFormat.DOUBLE)
                self.velocity.dx = buff.read_value(StructFormat.DOUBLE)
                self.velocity.dy = buff.read_value(StructFormat.DOUBLE)
                self.velocity.dz = buff.read_value(StructFormat.DOUBLE)
                yaw = buff.read_value(StructFormat.FLOAT)
                pitch = buff.read_value(StructFormat.FLOAT)
                flags = buff.read_value(StructFormat.INT)

            logging.debug("     Position updated, confirming teleportation...")
            teleport_id = buff.read_varint()
            res = Buffer()
            res.write_varint(0x00)
            res.write_varint(teleport_id)
            await send(connection, res)
            logging.debug("C->S (Play): Teleport confirmed")
            # ok 
        elif p_id == 0x20:
            entity_id = buff.read_varint()
            x = buff.read_value(StructFormat.DOUBLE)
            y = buff.read_value(StructFormat.DOUBLE)
            z = buff.read_value(StructFormat.DOUBLE)
            dx = buff.read_value(StructFormat.DOUBLE)
            dy = buff.read_value(StructFormat.DOUBLE)
            dz = buff.read_value(StructFormat.DOUBLE)
            
            yaw = buff.read_value(StructFormat.FLOAT)
            pitch = buff.read_value(StructFormat.FLOAT)
            on_ground = buff.read_value(StructFormat.BOOL)
        elif p_id == 0x2c: # entity log in event
            logging.debug("S->C (Play): Entity Log In")
            self.entity_id = buff.read_value(StructFormat.INT)
            buff.read_value(StructFormat.BOOL) # is hardcore
            dim_count = buff.read_varint() # dimension count
            for i in range(dim_count):
                buff.read_utf()

            buff.read_varint() # max pS->C s
            view_dist = buff.read_varint() # view distance
        elif p_id == 0x00:
            #bundle delimitter
            pass
        elif p_id == 0x09:
            val = buff.read_value(StructFormat.LONGLONG)
            x = val >> 38;
            y = val << 52 >> 52;
            z = val << 26 >> 38;
            logging.debug(f"S->C (Play): Block Update ({x}, {y}, {z})")
        elif p_id == 0x27:
            logging.debug("S->C (Play): Keep Alive")
            keep_alive_id = buff.read_value(StructFormat.LONGLONG)
            logging.debug(f"keep_alive_id={keep_alive_id}")
            buff = Buffer()
            buff.write_varint(0x1a)
            buff.write_value(StructFormat.LONGLONG, keep_alive_id) 
            await send(connection, buff)
            logging.debug("C->S (Play): Keep Alive")

    async def connect(self, ip: str, port: int = 25565):
        """
        Connects the player to a server.
        """
        async with (await TCPAsyncConnection.make_client((ip, port), 2)) as connection:
            self.connection = connection
            await login(connection, self.name, ip, port)
            await configure(connection)
            
            #asyncio.create_task(self.update_living()) 
            logging.debug("(Play): Now in play state")
            await self.chat("hello!")
            #await self.respawn()
            
            while True:
                p_id, buff = await read(connection)
                if p_id not in [0x6b]:
                    logging.debug(
                    f"S->C (Play): Received {serialize_packet(p_id)}")
                if p_id == 0x1d:
                    handle_disconnect(buff, nbt=True) 
                else:
                    await self._handle(connection, buff, p_id)
        
async def send(conn: TCPAsyncConnection, packet: Buffer):
    """Prefixes a packet with the length then sends to the server"""
    await conn.write_varint(len(packet))
    await conn.write(bytes(packet))

async def read(conn: TCPAsyncConnection):
    response_len = await conn.read_varint()
    response = await conn.read(response_len)
    buff = Buffer(response)
    p_id = buff.read_varint() # packet id
    return p_id, buff 

def handle_disconnect(packet: Buffer, nbt=False):
    if nbt:
        logging.error(packet.flush())
        raise ConnectionResetError("(Play) Kicked") 
    
    packet.read(1) # removes the prefix from the json 
    reason = {"translate": "unknown reason"}
    try:
        reason = json.loads(packet.flush().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logging.error(f"Error parsing JSON: {e}")
    finally:
        logging.error(f"Player disconnected {reason['translate']}")
        raise ConnectionResetError(reason['translate'])

async def login(conn: TCPAsyncConnection, name: str, ip: str, port: int = 25565):
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
    packet.write_varint(769) # protocol version (769 for v1.21.4)
    packet.write_utf(ip) # ip address
    packet.write_value(StructFormat.USHORT, port) # port
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

async def configure(connection: TCPAsyncConnection):
    configured = False

    while not configured:
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
            identifier = buff.read_utf()
            print(identifier)
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

