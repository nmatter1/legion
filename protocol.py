import enum
import math
import asyncio
import logging
import json
import datetime
from dataclasses import dataclass

from nbt import read_nbt
from buffer import Buffer

from mcproto.connection import TCPAsyncConnection
from mcproto.protocol.base_io import StructFormat

logging.getLogger().setLevel(logging.DEBUG)
cache_pool = {}

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

class PacketWrapper():
    async def send_chat_message(self, connection: TCPAsyncConnection, message: str):
        packet = Buffer()
        packet.write_varint(0x07) # minecraft:send_chat_message
        packet.write_utf(message) # message
        packet.write_value(StructFormat.LONGLONG, 0) # timestamp
        packet.write_value(StructFormat.LONGLONG, 0) # salt
        packet.write_value(StructFormat.BOOL, False) # true if signature is present
        packet.write_varint(0)  # message count (VarInt)
        acknowledged = 0 
        packet.write(acknowledged.to_bytes(3, 'big'))  # 3 bytes for 20 bits (the last byte will only use 4 bits)
        
        await send(connection, packet)
    
    async def send_status(self, connection: TCPAsyncConnection, status: int):
        """
        Sets the player status
        
        :param status: 0 performs respawn and is sent when the client is 
                       ready to respawn after death while 1 is sent 
                       when the clientbound opens the Statistics menu.
        """
        buffer = Buffer()
        buffer.write_varint(0x0a)
        buffer.write_varint(status) 
        await send(connection, buffer)
    
    async def send_chunk_received(self, connection: TCPAsyncConnection, chunks_per_tick: int):
        """
        Notifies the server that the chunk batch has been received by the client

        :param chunks_per_tick: Desired chunks per tick
        """
        buffer = Buffer()
        buffer.write_varint(0x09)
        buffer.write_value(StructFormat.FLOAT, chunks_per_tick)
        await send(connection, buffer)

class CraftPlayer():
    def __init__(self, name="Bot") -> None:
        self.name = name
        self.packet_wrapper = PacketWrapper()
        self.position = Position(0, 0, 0)
        self.velocity = Velocity(0, 0, 0)
        self.connection = None
        self.entity_id = 0
        self.health = 20

    async def respawn(self):
        assert self.connection is not None
        await self.packet_wrapper.send_status(self.connection, 0) # 0 is for respawn status
        logging.debug("C->S (Play): Client Action respawn state ready")
    
    async def chat(self, message: str):
        """
        Send a chat message to the console
        TODO: check if this can also send commands
        """
        assert self.connection is not None
        await self.packet_wrapper.send_chat_message(self.connection, message)
    
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
        elif p_id == 0x58: # minecraft:set_chunk_cache_center
            chunk_x = buff.read_varint()
            chunk_y = buff.read_varint()
        elif p_id == 0x0d: # minecraft:chunk_batch_start
            datetime.datetime.now()
        
        elif p_id == 0x28: # minecraft:level_chunk_with_light
            chunk_x = buff.read_int()
            chunk_z = buff.read_int()
            logging.debug(Colors.OKCYAN + f"(World): Loading chunk {chunk_x},{chunk_z}" + Colors.ENDC)
            heightmaps = read_nbt(buff)
            length = buff.read_varint()
            
            for i in range(24):
                block_count = buff.read_short()
                # reading paletted container
                bits_per_entry = buff.read_ubyte()
                assert bits_per_entry >= 0 and bits_per_entry <= 15, "Something went wrong with checking bits_per_entry"

                if bits_per_entry >= 4 and bits_per_entry <= 8:
                    palette_length = buff.read_varint()
                    palette = []

                    for _ in range(palette_length):
                        palette.append(buff.read_varint())
                    
                    logging.debug(f"registry {palette[0]}")
                    logging.debug(Colors.OKBLUE + f"(World): length={length} block_count={block_count}" + Colors.ENDC)
            
                    logging.debug(f"bits_per_entry={bits_per_entry}")
                    chunk_section_length = buff.read_varint()
                    logging.debug(f"chunk_length={chunk_section_length}")
                    
                    #for _ in range(chunk_section_length):
                    #    bits = int.from_bytes(buff.read(15), 'big')
                            
                    #buff.read_long()
            
            logging.debug(buff.read(40))
        
        elif p_id == 0x01: # minecraft:add_entity
            entity_id = buff.read_varint()
            entity_uuid = buff.read(16)
            entity_type = buff.read_varint() # TODO: get this from the reports
            x = buff.read_double()
            y = buff.read_double()
            z = buff.read_double()
            logging.debug(f"entity_id={entity_id} entity_type={entity_type}")
            logging.debug(f"position={x},{y},{z}") 
        elif p_id == 0x0c: # minecraft:chunk_batch_finished
            batch_size = buff.read_varint()
            assert self.connection is not None
            await self.packet_wrapper.send_chunk_received(self.connection, 9)
            logging.debug(f"(Chunk): Chunk received and acknowledge batch_size={batch_size}") 
        elif p_id == 0x42: # minecraft:teleport_entity
            logging.debug("S->C (Play): Sync position")
            self.velocity = Velocity(0, 0, 0) 
            self.position.x = buff.read_double()
            self.position.y = buff.read_double()
            self.position.z = buff.read_double()
            self.velocity.dx = buff.read_double()
            self.velocity.dy = buff.read_double()
            self.velocity.dz = buff.read_double()
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
            val = buff.read_value(StructFormat.LONGLONG)
            x = val >> 38;
            y = val << 52 >> 52;
            z = val << 26 >> 38;
            logging.debug(f"S->C (Play): Block Update ({x}, {y}, {z})")
        elif p_id == 0x27:
            keep_alive_id = buff.read_value(StructFormat.LONGLONG)
            logging.debug(f"keep_alive_id={keep_alive_id}")
            buff = Buffer()
            buff.write_varint(0x1a)
            buff.write_value(StructFormat.LONGLONG, keep_alive_id) 
            await send(connection, buff)
        elif p_id == 0x62:
            health = buff.read_float()
            logging.debug(f"setting health to {health}")
    
    async def connect(self, ip: str, port: int = 25565):
        """
        Connects the player to a server.
        """
        async with (await TCPAsyncConnection.make_client((ip, port), 2)) as connection:
            self.connection = connection
            await login(connection, self.name, ip, port)
            await configure(connection)
            await self.respawn() 
            #asyncio.create_task(self.update_living()) 
            logging.debug("(Play): Now in play state")
            await self.chat("hello!")
            
            important = [0x28, 0x0d, 0x4c, 0x4e, 0x58, 0x09, 0x0c, 0x0d, 0x0e] 
            while True:
                p_id, buff = await read(connection)
                if p_id in important:
                    logging.debug(Colors.OKGREEN + f"S->C (Play): {serialize_packet(p_id)}" + Colors.ENDC)
                elif p_id not in [0x6b]:
                    logging.debug(f"S->C (Play): {serialize_packet(p_id)}")
                
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

