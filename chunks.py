from typing import List, Tuple 
from connection import Buffer
from nbt import read_nbt
import logging
from dataclasses import dataclass
import numpy as np

logging.getLogger().setLevel(logging.DEBUG)
np.set_printoptions(threshold=10000)

@dataclass
class ChunkSection:
    """Contains a list of block ids for a 16x16x16 area"""
    blocks: np.ndarray 

@dataclass
class Chunk:
    """Stores a list of ChunkSections"""
    #TODO: Read heightmaps from NBT data
    heightmap: List[int]
    sections: List[ChunkSection]
    chunk_height: int = 24

    def block_at(self, x: int, y: int, z: int):
        index = y // 16
        assert index < len(self.sections) and y % self.chunk_height < len(self.sections[index].blocks)
        
        return self.sections[index].blocks[y][z][x]

    def destroy_block(self, x: int, y: int, z: int):
        index = y // 16 # every section is 16 blocks tall, sections stored by increasing y
        assert index < len(self.sections), "chunk section does not exist"

def read_chunk(block_registry_func, buff: Buffer) -> Chunk:
    """
    Every chunk should consume <0.40MB of memory 
    Entire render distance should only take 4MB at most.
    
    """
    chunk_x = buff.read_int()
    chunk_y = buff.read_int()
    
    logging.info("reading chunk data")
    read_nbt(buff) # Heightmaps | NBT | See Chunk Format#Heightmaps structure 
    _ = buff.read_varint() # Data | Prefixed Array of Byte | See Chunk Format#Data structure
    sections = [] 
    
    for _ in range(24): # XXX: 24 chunk sections on vanilla servers. Overworld only!
        sections.append(_read_chunk_section(block_registry_func, buff))
    
    logging.info(f"chunk coordinates loaded ({chunk_x},{chunk_y})")
    
    return Chunk(sections=sections, heightmap=[])

def _read_chunk_section(block_registry_func, buff: Buffer) -> ChunkSection:
    # Block count   |   Short   |   Number of non-air blocks present in the chunk section. 
    block_count = buff.read_short() # can be more than 4096
    
    blocks, block_palette = _read_paletted_container(buff)
    _, biome_palette = _read_paletted_container(buff)
    
    palette_block_names = [block_registry_func(block_id) for block_id in block_palette]
    if len(block_palette) > 2:
        logging.debug(blocks)
    logging.debug(f"blocks={palette_block_names}")
    
    # TODO: convert to global ids, currently dependent on local indirect palettes
    return ChunkSection(blocks=blocks)

def _read_paletted_container(buff: Buffer) -> Tuple[np.ndarray, List[int]]:
    # Bits Per Entry    |   Unsigned Byte	|   Determines how many bits are used to encode entries. 
    bits_per_entry = buff.read_ubyte()
    palette = _read_palette(bits_per_entry, buff)
    data_array_length = buff.read_varint() # number of encoded longs for a single chunk section
    blocks = []

    if bits_per_entry != 0:
        for _ in range(data_array_length):
            encoded = buff.read_long() # contains multiple entries
            blocks.extend(_decode_long(bits_per_entry, encoded))
        
        #assert len(blocks) == 4096, f"read more than 4096 blocks in read data array"
    
    #TODO: Can optimize storage if supporting adding many players at a time
    return np.resize(np.array(blocks), (16,16,16)), palette

def _read_palette(bits_per_entry: int, buff: Buffer) -> List[int]:
    palette = []
    
    match bits_per_entry:
        case 0:
            block_id = buff.read_varint()
            palette = [block_id]
        case 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8:
            # Palette Length    |   VarInt      |   Number of elements in the following array.
            palette_length = buff.read_varint()
            # Palette   |   Array of VarInt     |    Mapping of IDs in the registry to indices of this array.
            palette = [buff.read_varint() for _ in range(palette_length)]
        case _:
            # Direct palettes aren't supported
            raise ValueError("Invalid palette type or bits per entry."+
                             f"Cannot use {palette} with {bits_per_entry}")
    
    return palette

def _decode_long(bits_per_entry: int, number: int) -> List[int]:
    """Decodes a single encoded long into a list of block ids"""
    bits_remaining = 64 # size of long

    mask = (0b1 << bits_per_entry) - 1
    block_ids = [] 
    
    while bits_remaining >= bits_per_entry:
        block_ids.append(number & mask) 
        number >>= bits_per_entry
        bits_remaining -= bits_per_entry
    
    return block_ids

