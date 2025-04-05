import logging
from typing import List
from connection import Buffer

logging.getLogger().setLevel(logging.INFO)

def read_nbt(buff: Buffer):
    """Reads minimal uncompressed network NBT. Does not work with deeply nested data."""
    if buff.remaining == 0: 
        return
    
    tag = buff.read(1)[0] # 1 byte always sent for TAG_Compound
    assert tag == 0x0a, f"TAG_COMPOUND not found. Is {hex(tag)} valid network NBT?"
    
    return _read_nbt_helper(buff) #TODO: Return the NBT Tags and the data in a dictionary 

def _read_nbt_helper(buff: Buffer):
    if buff.remaining <= 2:
        return
    
    tag = buff.read(2)[0]
    
    match tag:
        case 0: # TAG_End
            return
        case 8: # TAG_String
            message = buff.read_utf()
            return message
        case 12: # TAG_Long_Array
            name = buff.read_utf()
            length = int.from_bytes(buff.read(4), 'big')
            for i in range(length):
                long = int.from_bytes(buff.read(8), 'big')
        case _: # default 
            #print(buff.read(40))
            logging.error("read unhandled nbt tag") 
    _read_nbt_helper(buff)

