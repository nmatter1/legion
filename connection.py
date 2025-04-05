"""Send and receive data from buffers and socket connections"""
from abc import ABC, abstractmethod
import socket
import struct
from typing import Tuple
from enum import Enum 
import logging

class T(Enum):
    LONGLONG = "h"
    UBYTE = "B"
    BYTE = "b"

class Stream(ABC):
    @abstractmethod
    def write(self, msg: bytes | bytearray):
        raise NotImplementedError() 
    
    @abstractmethod
    def read(self, num_bytes: int):
        raise NotImplementedError() 

    def read_varint(self):
        value: int = 0
        position: int = 0

        while True:
            current_byte = int(self.read_ubyte())
            value |= (current_byte & 0x7F) << position 
            
            if current_byte & 0x80 == 0:
                break
            position+=7

            if position >= 32: raise RuntimeError("VarInt is too big")
        
        if value & (1 << (32 - 1)) != 0:
            value -= 1 << 32 
        
        return value

    def write_varint(self, value: int):
        value = value + (1 << 32) if value < 0 else value # convert into twos complement 
        
        while True:
            if value & ~0x7F == 0:
                self.write_ubyte(value)
                return

            self.write_ubyte(value & 0x7F | 0x80)
            value >>= 7

    def read_byte(self) -> int:
        return self.read(1)[0]
    
    def read_int(self, num_bytes: int=4, signed=False) -> int:
        # XXX: Move these methods into an enum?
        num = int.from_bytes(self.read(num_bytes), byteorder='big')
        
        if num & (1 << (32 - 1)) != 0:
            num -= 1 << 32 
        
        return num
    
    def read_long(self) -> int:
        return self.read_int(8)
    
    def read_double(self) -> int:
        return self.read_int(8)

    def read_ubyte(self) -> int:
        return self.read_int(1, signed=False)
    
    def read_short(self) -> int:
        return self.read_int(2)
    
    def read_float(self) -> int:
        return self.read_int(4)
     
    def read_longlong(self) -> int:
        return self.read_int(8)

    def read_bool(self) -> bool:
        return bool.from_bytes(self.read(1), byteorder='big')
    
    def read_utf(self) -> int:
        length = self.read_varint()
        assert length <= 131068, f"Maximum length of utf strings is 131068 bytes but received {length}"

        result = self.read(length).decode("utf-8")
        assert len(result) <= 32767, (f"Maximum length of utf strings" +
                                      "is 32767 characters but received {result}")
        
        return result

    def write_utf(self, msg: str):
        # XXX: Change these assertions to exceptions?
        assert len(msg) <= 32767, (f"Maximum length of utf strings is 32767 characters")
        
        self.write_varint(len(msg))
        self.write(msg.encode("utf-8"))

    def write_ushort(self, msg: int):
        self.write(struct.pack(">H", msg))
    
    def write_longlong(self, msg: int):
        self.write(struct.pack(">q", msg))
    
    def write_float(self, msg: int):
        self.write(struct.pack(">f", msg))
    
    def write_byte(self, msg: int):
        self.write(struct.pack(">b", msg))
    
    def write_ubyte(self, msg: int):
        self.write(struct.pack(">B", msg))

    def write_short(self, msg: int):
        self.write(struct.pack(">h", msg))
    
    def write_int(self, msg: int):
        self.write(struct.pack(">i", msg))

    def write_bool(self, msg: int):
        self.write(struct.pack(">?", msg))

class Buffer(Stream, bytearray):
    def __init__(self, data: bytearray = bytearray()):
        self[:] = data
        self.pos = 0 
    
    def read(self, num_bytes: int) -> bytearray:
        if self.pos + num_bytes > len(self):
            raise ValueError(f"Cannot read past end of buffer {self.pos+num_bytes}/{len(self)}")
        start = self.pos 
        self.pos += num_bytes

        return self[start:start+num_bytes]

    def write(self, msg: bytearray | bytes):
        self.extend(msg) 
    
    @property
    def remaining(self):
        return len(self) - self.pos
    
    def flush(self):
        return self.read(len(self) - self.pos)

class Connection(Stream):
    def __init__(self, client: socket.socket):
        self.client = client 
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.client.shutdown(socket.SHUT_RDWR)
        self.client.close()

    def read(self, num_bytes: int)->bytearray:
        result = bytearray() 
        
        while len(result) < num_bytes:
            msg = self.client.recv(num_bytes - len(result))
            if len(msg) == 0: 
                raise IOError("Connection must be closed")
            
            result.extend(msg)

        return result 
    
    def write(self, msg: bytearray | bytes):
        sent = 0

        while sent < len(msg):
            sent += self.client.send(msg[sent:])
    
    @classmethod
    def create(cls, ip: str, port: int):
        """
            :raises OSError: If socket fails to be created
        """
        client = socket.create_connection((ip, port), timeout=5)
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return cls(client)

async def send(conn: Connection, packet: Buffer):
    """Prefixes a packet with the length then sends to the server"""
    conn.write_varint(len(packet))
    conn.write(bytes(packet))

async def read(conn: Connection) -> Tuple[int, Buffer]:
    """Reads an incoming packet from the connection and stores in a buffer"""
    response_len = conn.read_varint()
    response = conn.read(response_len)
    buff = Buffer(response)
    p_id = buff.read_varint() # packet id
    return p_id, buff


