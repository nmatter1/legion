from mcproto.buffer import Buffer as ProtoBuffer
from mcproto.protocol.base_io import StructFormat

class Buffer(ProtoBuffer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def read_ubyte(self) -> int:
        return self.read_value(StructFormat.UBYTE)

    def read_bool(self) -> bool:
        return self.read_value(StructFormat.BOOL)

    def read_double(self) -> float:
        return self.read_value(StructFormat.DOUBLE)
    
    def read_float(self) -> float:
        return self.read_value(StructFormat.FLOAT)

    def read_int(self) -> int:
        return self.read_value(StructFormat.INT)
    
    def read_short(self) -> int:
        return self.read_value(StructFormat.SHORT) 
    
    def read_long(self) -> int:
        return int.from_bytes(self.read(8), 'big')
