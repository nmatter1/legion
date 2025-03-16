import asyncio
from mcproto.buffer import Buffer
from mcproto.connection import TCPAsyncConnection
from mcproto.protocol.base_io import StructFormat
import logging
import math
from constants import *
from dataclasses import dataclass
 
def convert_vel(original):
    previous = (original / VERTICAL_DRAG) + GRAVITY
    return previous

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

class Entities():
    def __init__(self) -> None:
        self.entities = []

    def remove(self, e_id):
        self.entities = [entity for entity in self.entities if entity.e_id != e_id]
    
    def add(self, e_id, x, y, z):
        for entity in self.entities:
            if entity.e_id == e_id:
                print("entity already added")
                return
        self.entities.append(VisibleEntity(e_id, Position(x, y, z))) 
    
    def update(self, e_id, x, y, z):
        for entity in self.entities:
            if entity.e_id == e_id:
                entity.x = x
                entity.y = y
                return
        # add the entity if not found
        self.add(e_id, x, y, z)
        print(self.entities)
        #0x42 remove entity

class CraftPlayer():
    def __init__(self, name="Bot") -> None:
        self.name = name
        self.position = Position(0, 0, 0)
        self.velocity = Velocity(0, 0, 0)
        self.connection = None
        self.lock = asyncio.Lock()
        self.state = "login"
        self.motion_blocking = [] 
        self.entity_id = 0
        self.health = 20    
        self.entities = Entities() 
        self.play_ready = asyncio.Event()
    
    def get_height(self, x, z):
        for (x,y,z) in self.motion_blocking:
            if x == round(x) and z == round(z):
                return y 
        return 0
    
    def on_ground(self):
        on_ground = self.position.y <= self.get_height(self.position.x, self.position.z) 
        return on_ground
    
    def read_chunk_packet(self, buff: Buffer):
        """
        Reads the chunk data packet (16x16x16)
        Includes world blocks, heightmap, and other chunk information 
        """
        # read the height map
        print("reading chunk")
        start_x = 16 * buff.read_value(StructFormat.INT)
        start_z = 16 * buff.read_value(StructFormat.INT)
        buff.read(1) # should be \n which is hex=0xa, the start of the tag compound 
        motion_blocking = read_heightmap(buff, start_x, start_z)
        world_surface = read_heightmap(buff, start_x, start_z) # world surface heightmap
        self.motion_blocking.extend(motion_blocking) #adds the motion heightmaps to list of heightmaps in view              
        full = buff.read_value(StructFormat.BYTE) # is this the "full" value?
         
        size = buff.read_varint()
        print(f"size={size}") 
        block_count = buff.read_value(StructFormat.SHORT)
       # paletted container
        bits_per_entry = buff.read_value(StructFormat.UBYTE)
        
        print(f"bpe {bits_per_entry}")
        
        if bits_per_entry <= 8 and bits_per_entry >= 4:
            p_len = buff.read_varint()
            palette = []
            for _ in range(p_len):
                palette.append(buff.read_varint())
            print("palette")
            print(palette)
        else:
            raise ValueError("bpe type not supported")
        
        arr_len = buff.read_varint()
        # there could be errors here
        blocks = []
        for _ in range(arr_len):
            long = buff.read_value(StructFormat.LONG)
            blocks.append(long)
        print(f"bpe={bits_per_entry} block_count={block_count} size={size}")
    
    async def attack(self, e_id):
        """TODO: Not finished yet"""
        assert self.connection is not None
        # check if visible entities contains e_id
        buff = Buffer()
        buff.write_varint(int(0x16)) # packet id
        buff.write_varint(e_id)
        buff.write_varint(1) # 1 == attack, 2 == interact at, 0 == interact
        buff.write_value(StructFormat.BOOL, False) # is the player sneaking
        await send(self.connection, buff)

    async def walk(self):
        """Walks the player forwards"""
        # https://www.mcpk.wiki/wiki/Horizontal_Movement_Formulas
        # add the acceleration here, velocity is handled every tick in another function
        while True:
            await asyncio.sleep(0.05) # must run in its own spawn task
            async with self.lock:
                # APPLIED ACCELERATION IS 0.1 PER TICK FOR WALKING SPEED
                # BUT ONLY FOR DEFAULT EFFECT, DEFAULT FRICTION, AND DEFAULT DIRECTION
                
                facing = 0 # IMPORTANT: Direction and facing are in degrees. Facing only matters for sprint jump
                friction = 0.6
                e = 1.0 # effect multiplier
                mt = 0.98 # default = 0.98, 45 strafe = 1.0, 45 sneak = 0.98 * math.pow(2, .5)
                m = 1.0*mt# movement multiplier (1 * .98 default)
                acceleration = lambda direction: 0.1 * m * e * math.pow(0.6/friction, 3) * math.sin(direction)
                
                # apply the sprint jump multiplier?
                if not self.on_ground():
                    #acceleration+= 0.2 * math.sin(facing)# TODO: sprint jump multiplier 
                    pass
                
                self.velocity.dx += acceleration(0)
                self.velocity.dy = self.velocity.dy
                self.velocity.dz += acceleration(0)

    async def update_living(self):
        """
        Updates the entity velocity every tick, if needed.
        This method will be called automatically, there's no need to manually call it
        """
        assert self.connection is not None
        
        while True:
            await asyncio.sleep(.05)
            # delay for a single tick (20 / second) to avoid sending too many movement packets at once
                 
            async with self.lock:
                if self.velocity.dy == 0 and not self.on_ground(): # prevent floating issues
                    self.velocity.dy -= 0.01
                
                if self.velocity != Velocity(0, 0, 0) or not self.on_ground(): 
                    buffer = Buffer()
                    dy = max(self.velocity.dy, TERMINAL_VELOCITY) #prevent falling too fast
                    
                    if abs(dy) <= VELOCITY_THRESHOLD:
                        dy = 0
                    elif dy != TERMINAL_VELOCITY:
                        dy -= GRAVITY 
                        dy *= VERTICAL_DRAG 

                    if (dy + self.position.y) < self.get_height(self.position.x, self.position.z) and dy <= 0:
                        # if the player would move through ground block moving down
                        # snap the players position to ground level 
                        self.position.y = self.get_height(self.position.x, self.position.z) 
                        dy = 0
                    else:
                        self.position.y += dy 
                         
                    # 1.3 sprinting, 1 walking, 0.3 sneaking, 0 stopping
                    #TODO: slipperniess multiplier (use block map to check block below player) 0.6 default, 0.8 slime, 0.98 ice, 1.0 airborne
                    # TODO: 0.98 multiplier friction, 1.0 45 degree strafe, 0.98squareroot 2 45degree sneak
                    # dx is the offset applied to the player, assumes ground is flat
                    # TODO: RIGHT NOW JUST THE GROUND SPEED. AIR SPEED AND JUMP SPEED NOT ACCURATE
                    # Vh,t = Vh,t-1 x St-1 x 0.91 + 0.1 x Mt x Et x (0.6/St)
                    dx = self.velocity.dx * 0.91 * FRICTION
                    dz = self.velocity.dz * 0.91 * FRICTION
                    
                    # update the x and zs but check bounding box before and snap if hitting a wall
                    if self.get_height(self.position.x + dx, self.position.z + dz) > self.position.y:
                        # get the distance to the next block
                        pass
                    else:
                        self.position.x += dx
                        self.position.z += dz
                    
                    buffer.write_varint(int(0x1a)) 
                    buffer.write_value(StructFormat.DOUBLE, self.position.x)
                    buffer.write_value(StructFormat.DOUBLE, self.position.y)
                    buffer.write_value(StructFormat.DOUBLE, self.position.z)
                    buffer.write_value(StructFormat.BOOL, self.on_ground())

                    if abs(dy) <= VELOCITY_THRESHOLD:
                        dy = 0
                    if abs(dx) <= VELOCITY_THRESHOLD:
                        dx = 0
                    if abs(dz) <= VELOCITY_THRESHOLD:
                        dz = 0
                    
                    self.velocity = Velocity(dx, dy, dz)
                    
                    await send(self.connection, buffer)
    
    async def command(self, command: str):
        assert self.connection is not None
        packet = Buffer()
        packet.write_varint(0x4)
        packet.write_utf(command)
        await send(self.connection, packet)
    
    async def chat(self, message: str):
        """
        Send a chat message to the console
        TODO: check if this can also send commands
        """
        assert self.connection is not None
        packet = Buffer()
        packet.write_varint(6)
        packet.write_utf(message) # message
        packet.write_value(StructFormat.LONGLONG, 0) #timestamp
        packet.write_value(StructFormat.LONGLONG, 0) #salt
        packet.write_value(StructFormat.BOOL, False) #whether signature is present
        packet.write_varint(0)  # message count (VarInt)
       
        # Write the acknowledged messages (Fixed BitSet of 20 bits, here all zeros to mean no messages acknowledged)
        acknowledged = 0  # 20-bit field (bit set), using 0 for simplicity (no acknowledgments)
        packet.write(acknowledged.to_bytes(3, 'big'))  # 3 bytes for 20 bits (the last byte will only use 4 bits)
        
        await send(self.connection, packet)

    async def respawn(self):
        """
        Force player respawn. Only works when the player is currently dead. 
        """
        assert self.connection is not None
        self.health = 20
        buffer = Buffer()
        buffer.write_varint(9)
        buffer.write_varint(0)
        await send(self.connection, buffer)

    async def swing(self):
        """
        Swings the left arm of the player. Does not deal damage to entities
        """
        assert self.connection is not None
        buffer = Buffer()
        buffer.write_varint(int(0x36))
        buffer.write_varint(0)
        await send(self.connection, buffer)
    
    async def jump(self):
        """
        Applies a small vertical velocity if the player is grounded
        """
        assert self.connection is not None
        async with self.lock:
            if self.on_ground():
                jump_vel = convert_vel(0.42)
                self.velocity.dy = jump_vel
    
    async def handle_play_state(self, connection, buff: Buffer, p_id):
        """
        Play state packets. The player is already logged in and loaded into the world
        """
        #await apply_velocity(connection, 0, -20, 0) 
        if p_id == 0x64: # ========= (GAME TICK EVENT) ============
            # Notchian clients send move packet even if stationary every 20 ticks 
            # need to send move packet for stationary players so send this once every second 
            async with self.lock:
                buffer = Buffer()
                buffer.write_varint(int(0x1a)) 
                buffer.write_value(StructFormat.DOUBLE, self.position.x)
                buffer.write_value(StructFormat.DOUBLE, self.position.y)
                buffer.write_value(StructFormat.DOUBLE, self.position.z)
                buffer.write_value(StructFormat.BOOL, True)
        
        elif p_id == 0x27:
            self.read_chunk_packet(buff)
        elif p_id == 0x0c: # acknowledge chunk data
            buffer = Buffer()
            buffer.write_varint(int(0x08));
            buffer.write_value(StructFormat.FLOAT, 2)
            await send(connection, buffer)
        elif p_id == 0x5d:
            # Player took damage
            health = buff.read_value(StructFormat.FLOAT)
            print(f"player damaged health={health}")
            self.health =- health
            if health <= 0:
                logging.info("player died")
                await self.respawn()
        elif p_id == 0x26:
            # Keep-alive packet. Need to send these to avoid being kicked after a few seconds
            key = buff.read_value(StructFormat.LONGLONG)
            res = Buffer()
            res.write_varint(0x18)
            res.write_value(StructFormat.LONGLONG, key)
            await send(connection, res)
        elif p_id == 0x2a:
            pass
        elif p_id == 0x5a:
            print(buff)
            entity_id = buff.read_varint()
            dx = buff.read_value(StructFormat.SHORT) / 8000 # divided by 8000 just how the server sends it
            dy = buff.read_value(StructFormat.SHORT) / 8000
            dz = buff.read_value(StructFormat.SHORT) / 8000
            if entity_id == self.entity_id:
                self.velocity = Velocity(dx, dy, dz) 
            
            print(f"{entity_id}: {dx}, {dy} || {self.entity_id}")
        elif p_id == 0x40:
            # Synchronize player position
            async with self.lock:
                self.velocity = Velocity(0, 0, 0) 
                self.position.x = buff.read_value(StructFormat.DOUBLE)
                self.position.y = buff.read_value(StructFormat.DOUBLE)
                self.position.z = buff.read_value(StructFormat.DOUBLE)
                yaw = buff.read_value(StructFormat.FLOAT)
                pitch = buff.read_value(StructFormat.FLOAT)
                flags = buff.read_value(StructFormat.BYTE)
                print("synced position") 
            teleport_id = buff.read_varint()
            
            # Acknowledge teleportation
            res = Buffer()
            res.write_varint(0)
            res.write_varint(teleport_id)
            await send(connection, res)
        
        elif p_id == 0x2e: #
            # Player movement packet
            e_id = buff.read_varint()
            delta_x = buff.read_value(StructFormat.SHORT) / 8000
            delta_y = buff.read_value(StructFormat.SHORT)
            delta_z = buff.read_value(StructFormat.SHORT)
            angle = buff.read_value(StructFormat.BYTE)
            print(f"{e_id}: {delta_x} {delta_y}")
        elif p_id == 0x2b: # entity log in event
            self.entity_id = buff.read_value(StructFormat.INT)
            buff.read_value(StructFormat.BOOL) # is hardcore
            dim_count = buff.read_varint() # dimension count
            for i in range(dim_count):
                buff.read_utf()

            buff.read_varint() # max players
            view_dist = buff.read_varint() # view distance
            print(view_dist) 
        elif p_id == 0x70: # teleport more than 8 blocks
            e_id = buff.read_varint()
            if e_id != self.entity_id:
                x = buff.read_value(StructFormat.DOUBLE)
                y = buff.read_value(StructFormat.DOUBLE)
                z = buff.read_value(StructFormat.DOUBLE)
                self.entities.update(e_id, x, y, z)
    
    async def handle_configuration_state(self, connection, buff: Buffer, p_id):
        if p_id == 0x0e:
            res = Buffer()
            res.write_varint(7)
            res.write_varint(0)
            await send(connection, res)
        elif p_id == 0x07:
            identifier = buff.read_utf()
            print(identifier)
            count = buff.read_varint()
        elif p_id == 0x0D:
            print("0x0d packet no")
        elif p_id == 0x03:
            res = Buffer()
            res.write_varint(3)
            print("OKOKOK")
            await send(connection, res)
            await self.respawn()
            self.state = "play"
            self.play_ready.set()
            print("ready to go")
    async def start(self, ip: str, port: int = 25565):
        """
        Connects the player to a server.
        TODO: Not sure if the player can connect to multiple servers at the same time
        """
        async with (await TCPAsyncConnection.make_client((ip, port), 2)) as connection:
            self.connection = connection
            self.state = "login"
            await login(connection, self.name, ip, port)
            self.state = "configuration"
            asyncio.create_task(self.update_living()) 
            
            while True:
                data = await read(connection)
                if not data:
                    continue
                
                buff = Buffer(data)
                p_id = buff.read_varint() # this is the packet id (depends on client / server bound and state)
                
                if p_id == 0x1d:
                    reason = buff.read_utf()
                    print(reason)
                    print("client disconnect")
                    return
                if self.state == "configuration":
                    await self.handle_configuration_state(connection, buff, p_id)
                elif self.state == "play":
                    await self.handle_play_state(connection, buff, p_id)
                else:
                    raise ValueError("invalid state")
                if DEBUG:
                    print(f"{hex(p_id)}: {PLAY_PACKETS.get(p_id, 'Unknown')}")
        

def read_heightmap(buff, chunk_x, chunk_z):
    """Returns a map of the heightest blocks in the chunk for a 16x16 grid"""
    import math
    heightmap = []
    world_height = 256 
    bits_per_entry = math.ceil(math.log2(world_height + 1))
    buff.read(1) # LONG_ARRAY tag (0xc)
    buff.read(1) #pretag (0x00)
    buff.read_utf() # example: MOTION_BLOCKING or WORLD_SURFACE name
    entries = int.from_bytes(buff.read(4))
    rel_z = 0 # relative to start of chunk coordinate (0-15)
    rel_x = 0 
    long = int.from_bytes(buff.read(8)) # heightmap starts at -64 so at y=0 the heightmap is 64
    count = 0 
    packed_entries = 64//bits_per_entry
     
    while rel_z < 16:
        #can read maximum of 7 bits because there is padding between longs.
        if count == packed_entries:
            count=0
            long = int.from_bytes(buff.read(8)) 
        
        y = (long & 0b111111111) - 64
        long >>= 9
        heightmap.append((chunk_x+rel_x, y, chunk_z + rel_z))
        rel_x+=1
        if rel_x >= 16:
            rel_x = 0
            rel_z += 1

        count+=1
    return heightmap 

async def send(conn: TCPAsyncConnection, packet: Buffer):
    """Prefixes a packet with the length then sends to the server"""
    await conn.write_varint(len(packet))
    await conn.write(packet)

async def read(conn: TCPAsyncConnection):
    response_len = await conn.read_varint()
    response = await conn.read(response_len)
    return response

async def login(conn: TCPAsyncConnection, name: str, ip: str, port: int = 25565):
    packet = Buffer()
    packet.write_varint(0) # packet id 
    packet.write_varint(767) # protocol version
    packet.write_utf(ip)
    packet.write_value(StructFormat.USHORT, port)
    packet.write_varint(2) # 2 will put the client in login state 
    await send(conn, packet)
    packet = Buffer()
    packet.write_varint(0) #packet id
    packet.write_utf(name)
    p_id = bytes.fromhex("de6078a856ec4cf9b8832a46025ae261")
    packet.write(p_id)
    await send(conn, packet)
    await read(conn)
    packet = Buffer()
    packet.write_varint(0x03) #login acknowledgement packet
    await send(conn, packet)
    await read(conn)
    # Offline server sends the compression 0x03 to enable compression 
    #Server sends the login success packet.

