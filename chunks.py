from typing import List, Literal, Tuple
from buffer import Buffer
from nbt import read_nbt
import logging

logging.getLogger().setLevel(logging.DEBUG)

#file = open("chunk.txt", "w")

def _decode_long(bits_per_entry: int, number: int):
    bits_remaining = 64 # size of long
    block_count = 0

    mask = (0b1 << bits_per_entry) - 1
    block_ids = [] 
    
    while bits_remaining >= bits_per_entry:
        palette_entry = number & mask
        block_ids.append(palette_entry) 
        number >>= bits_per_entry
        bits_remaining -= bits_per_entry
        block_count+=1
    
    return block_ids

def _read_paletted_container(buff: Buffer, palette_type: Literal["chunk", "biome"] ="chunk"):
    # Bits Per Entry    |   Unsigned Byte	|   Determines how many bits are used to encode entries. 
    bits_per_entry = buff.read_ubyte()
    palette = _read_palette(bits_per_entry, buff, palette_type)
    data_array_length = buff.read_varint() # number of encoded longs for a single chunk section
    
    if bits_per_entry != 0:
        total_decoded = 0 
        
        for _ in range(data_array_length):
            encoded = buff.read_long() # contains multiple entries
            total_decoded += len(_decode_long(bits_per_entry, encoded))
        
        assert total_decoded == 4096, f"read more than 4096 blocks in read data array"
    return palette

def _read_palette(bits_per_entry: int, buff: Buffer, palette_type: Literal["chunk", "biome"] = "chunk"):
    palette = []
    
    match bits_per_entry:
        case 0:
            block_id = buff.read_varint()
            palette = [block_id]
        case 4 | 5 | 6 | 7 | 8:
            assert palette_type == "chunk", "not a chunk type"
            # Palette Length    |   VarInt      |   Number of elements in the following array.
            palette_length = buff.read_varint()
            # Palette   |   Array of VarInt     |    Mapping of IDs in the registry to indices of this array.
            palette = [buff.read_varint() for _ in range(palette_length)]
        case 1 | 2 | 3:
            assert palette_type == "biome", "not a biome type"
            # Palette Length    |   VarInt      |   Number of elements in the following array.
            palette_length = buff.read_varint()
            # Palette   |   Array of VarInt     |    Mapping of IDs in the registry to indices of this array.
            palette = [buff.read_varint() for _ in range(palette_length)]
        case _:
            # Direct palettes aren't supported
            raise ValueError("Invalid palette type or bits per entry."+
                             f"Cannot use {palette_type} with {bits_per_entry}")
    
    return palette

def _read_chunk_section(block_registry_func, buff: Buffer):
    # Block count   |   Short   |   Number of non-air blocks present in the chunk section. 
    block_count = buff.read_short() # can be more than 4096
    
    block_palette = _read_paletted_container(buff, 'chunk')
    biome_palette = _read_paletted_container(buff, 'biome')

    palette_block_names = [block_registry_func(block_id).split("minecraft:")[1] for block_id in block_palette]
    logging.debug(f"blocks={palette_block_names}")

def read_chunk(block_registry_func, buff: Buffer):
    chunk_x = buff.read_int()
    chunk_y = buff.read_int()
    
    logging.info("reading chunk data")
    # Heightmaps    |   NBT     |   See Chunk Format#Heightmaps structure 
    read_nbt(buff)
    # Data          |   Prefixed Array of Byte  |   See Chunk Format#Data structure
    size = buff.read_varint() # size of buffer 
    
    for _ in range(24): # 24 chunk sections on vanilla servers
        _read_chunk_section(block_registry_func, buff) # read 1/24 chunk sections
    
    logging.info(f"chunk coordinates loaded ({chunk_x},{chunk_y})")

