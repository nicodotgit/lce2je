import os
import sys
import struct
import zlib
import time
import io
import multiprocessing
import queue as qlib
from concurrent.futures import ProcessPoolExecutor
from nbt import nbt

# LCE constants
COMPRESSED_SECTION_HEIGHT = 128
BLOCKS_PER_SECTION = COMPRESSED_SECTION_HEIGHT * 16 * 16 # 32768
NIBBLES_PER_SECTION = BLOCKS_PER_SECTION // 2 # 16384
FULL_CHUNK_BLOCKS = 256 * 16 * 16 # 65536
FULL_CHUNK_NIBBLES = FULL_CHUNK_BLOCKS // 2 # 32768

def rle_decode(data: bytes, expected_size: int) -> bytearray:
    output = bytearray(expected_size)
    in_pos = 0
    out_pos = 0
    while in_pos < len(data) and out_pos < expected_size:
        current = data[in_pos]
        in_pos += 1
        if current == 255:
            if in_pos >= len(data):
                break
            count = data[in_pos]
            in_pos += 1
            if count < 3:
                count += 1
                for _ in range(count):
                    if out_pos < expected_size:
                        output[out_pos] = 255
                        out_pos += 1
            else:
                count += 1
                if in_pos >= len(data):
                    break
                value = data[in_pos]
                in_pos += 1
                for _ in range(count):
                    if out_pos < expected_size:
                        output[out_pos] = value
                        out_pos += 1
        else:
            output[out_pos] = current
            out_pos += 1
    return output

def get_compressed_tile_index(block: int, tile: int) -> int:
    index = ((block & 0x180) << 6) | ((block & 0x060) << 4) | ((block & 0x01F) << 2)
    index |= ((tile & 0x30) << 7) | ((tile & 0x0C) << 5) | (tile & 0x03)
    return index

def read_compressed_tile_storage(payload: bytes, offset: int) -> tuple[bytearray, int]:
    allocated_size = struct.unpack_from(">i", payload, offset)[0]
    offset += 4
    
    blob = payload[offset : offset + allocated_size]
    offset += allocated_size
    
    data_region = blob[1024:]
    blocks = bytearray(BLOCKS_PER_SECTION)
    
    for block in range(512):
        block_index = struct.unpack_from("<H", blob, block * 2)[0]
        index_type = block_index & 3
        
        if index_type == 3:
            if (block_index & 4) != 0:
                value = (block_index >> 8) & 0xFF
                for tile in range(64):
                    blocks[get_compressed_tile_index(block, tile)] = value
            else:
                data_offset = (block_index >> 1) & 0x7FFE
                for tile in range(64):
                    blocks[get_compressed_tile_index(block, tile)] = data_region[data_offset + tile]
            continue
            
        bits_per_tile = [1, 2, 4][index_type]
        tile_type_count = 1 << bits_per_tile
        tile_type_mask = tile_type_count - 1
        index_shift = 3 - index_type
        index_mask_bits = 7 >> index_type
        index_mask_bytes = 62 >> index_shift
        packed_data_size = 8 << index_type
        
        data_offset = (block_index >> 1) & 0x7FFE
        tile_types = data_region[data_offset : data_offset + tile_type_count]
        packed = data_region[data_offset + tile_type_count : data_offset + tile_type_count + packed_data_size]
        
        for tile in range(64):
            idx = (tile >> index_shift) & index_mask_bytes
            bit = (tile & index_mask_bits) * bits_per_tile
            palette_index = (packed[idx] >> bit) & tile_type_mask
            blocks[get_compressed_tile_index(block, tile)] = tile_types[palette_index]
            
    return blocks, offset

def set_nibble_value(nibble_data: bytearray, xz: int, y: int, value: int):
    pos = (xz << 7) | y
    slot = pos >> 1
    part = pos & 1
    value &= 0x0F
    if part == 0:
        nibble_data[slot] = (nibble_data[slot] & 0xF0) | value
    else:
        nibble_data[slot] = (nibble_data[slot] & 0x0F) | (value << 4)

def get_nibble_value(nibble_data: bytes, xz: int, y: int) -> int:
    pos = (xz << 8) | y
    slot = pos >> 1
    part = pos & 1
    value = nibble_data[slot]
    return (value & 0x0F) if part == 0 else ((value >> 4) & 0x0F)

def read_sparse_nibble_storage(payload: bytes, offset: int, supports_all_fifteen_plane: bool) -> tuple[bytearray, int]:
    count = struct.unpack_from(">i", payload, offset)[0]
    offset += 4
    
    storage_bytes = 128 + (count * 128)
    blob = payload[offset : offset + storage_bytes]
    offset += storage_bytes
    
    plane_indices = blob[0:128]
    plane_data = blob[128:]
    nibble_data = bytearray(NIBBLES_PER_SECTION)
    
    for y in range(128):
        plane_index = plane_indices[y]
        if plane_index == 128:
            continue
        if supports_all_fifteen_plane and plane_index == 129:
            for xz in range(256):
                set_nibble_value(nibble_data, xz, y, 15)
            continue
            
        plane_offset = plane_index * 128
        plane = plane_data[plane_offset : plane_offset + 128]
        for xz in range(128):
            packed = plane[xz]
            set_nibble_value(nibble_data, xz << 1, y, packed & 0x0F)
            set_nibble_value(nibble_data, (xz << 1) + 1, y, (packed >> 4) & 0x0F)
            
    return nibble_data, offset

def combine_block_sections(lower: bytearray, upper: bytearray) -> bytearray:
    combined = bytearray(FULL_CHUNK_BLOCKS)
    for xz in range(256):
        combined[xz*256 : xz*256 + 128] = lower[xz*128 : xz*128 + 128]
        combined[xz*256 + 128 : xz*256 + 256] = upper[xz*128 : xz*128 + 128]
    return combined

def combine_nibble_sections(lower: bytearray, upper: bytearray) -> bytearray:
    combined = bytearray(FULL_CHUNK_NIBBLES)
    for xz in range(256):
        combined[xz*128 : xz*128 + 64] = lower[xz*64 : xz*64 + 64]
        combined[xz*128 + 64 : xz*128 + 128] = upper[xz*64 : xz*64 + 64]
    return combined

def set_nibble_in_sec(arr: bytearray, index: int, value: int):
    byte_idx = index >> 1
    value &= 0x0F
    if (index & 1) == 0:
        arr[byte_idx] = (arr[byte_idx] & 0xF0) | value
    else:
        arr[byte_idx] = (arr[byte_idx] & 0x0F) | (value << 4)


def fix_uuid_strings(tag):
    if hasattr(tag, "tags") and isinstance(tag.tags, list):
        if tag.__class__.__name__ == "TAG_Compound":
            if "UUID" in tag:
                uuid_tag = tag["UUID"]
                if uuid_tag.__class__.__name__ == "TAG_String":
                    uuid_str = uuid_tag.value
                    del tag["UUID"]
                    hex_str = uuid_str
                    if hex_str.startswith("ent") or hex_str.startswith("ply") or hex_str.startswith("evt"):
                        hex_str = hex_str[3:]
                    hex_str = hex_str.replace("-", "")
                    
                    if len(hex_str) == 32:
                        try:
                            most = int(hex_str[:16], 16)
                            if most >= 2**63: most -= 2**64
                            least = int(hex_str[16:], 16)
                            if least >= 2**63: least -= 2**64
                            
                            if "UUIDMost" not in tag:
                                from nbt import nbt
                                tag.tags.append(nbt.TAG_Long(name="UUIDMost", value=most))
                            if "UUIDLeast" not in tag:
                                from nbt import nbt
                                tag.tags.append(nbt.TAG_Long(name="UUIDLeast", value=least))
                        except ValueError:
                            pass
        for subtag in tag.tags:
            fix_uuid_strings(subtag)

def decode_lce_chunk_payload(payload: bytes) -> nbt.NBTFile:
    offset = 0
    version = struct.unpack_from(">h", payload, offset)[0]
    offset += 2
    
    if version != 8 and version != 9:
        raise ValueError(f"Unsupported LCE chunk version: {version}")
        
    chunk_x = struct.unpack_from(">i", payload, offset)[0]
    offset += 4
    chunk_z = struct.unpack_from(">i", payload, offset)[0]
    offset += 4
    last_update = struct.unpack_from(">q", payload, offset)[0]
    offset += 8
    
    if version >= 9:
        inhabited_time = struct.unpack_from(">q", payload, offset)[0]
        offset += 8
    else:
        inhabited_time = 0
        
    lower_blocks, offset = read_compressed_tile_storage(payload, offset)
    upper_blocks, offset = read_compressed_tile_storage(payload, offset)
    
    lower_data, offset = read_sparse_nibble_storage(payload, offset, supports_all_fifteen_plane=False)
    upper_data, offset = read_sparse_nibble_storage(payload, offset, supports_all_fifteen_plane=False)
    
    lower_sky_light, offset = read_sparse_nibble_storage(payload, offset, supports_all_fifteen_plane=True)
    upper_sky_light, offset = read_sparse_nibble_storage(payload, offset, supports_all_fifteen_plane=True)
    
    lower_block_light, offset = read_sparse_nibble_storage(payload, offset, supports_all_fifteen_plane=True)
    upper_block_light, offset = read_sparse_nibble_storage(payload, offset, supports_all_fifteen_plane=True)
    
    height_map = payload[offset : offset + 256]
    offset += 256
    terrain_populated_flags = struct.unpack_from(">h", payload, offset)[0]
    offset += 2
    biomes = payload[offset : offset + 256]
    offset += 256
    
    dynamic_root = None
    if offset < len(payload):
        try:
            dynamic_root = nbt.NBTFile(buffer=io.BytesIO(payload[offset:]))
        except Exception as e:
            pass
            
    old_blocks = combine_block_sections(lower_blocks, upper_blocks)
    old_data = combine_nibble_sections(lower_data, upper_data)
    old_sky = combine_nibble_sections(lower_sky_light, upper_sky_light)
    old_block_light = combine_nibble_sections(lower_block_light, upper_block_light)
    
    root = nbt.NBTFile()
    root.name = ""
    
    level = nbt.TAG_Compound()
    level.name = "Level"
    
    level.tags.append(nbt.TAG_Int(name="xPos", value=chunk_x))
    level.tags.append(nbt.TAG_Int(name="zPos", value=chunk_z))
    level.tags.append(nbt.TAG_Long(name="LastUpdate", value=last_update))
    level.tags.append(nbt.TAG_Long(name="InhabitedTime", value=inhabited_time))
    level.tags.append(nbt.TAG_Byte(name="TerrainPopulated", value=1))
    level.tags.append(nbt.TAG_Byte(name="LightPopulated", value=1))
    
    hm_tag = nbt.TAG_Int_Array(name="HeightMap")
    hm_tag.value = [int(b & 0xFF) for b in height_map]
    level.tags.append(hm_tag)
    
    biomes_tag = nbt.TAG_Byte_Array(name="Biomes")
    biomes_tag.value = bytearray(biomes)
    level.tags.append(biomes_tag)
    
    sections = nbt.TAG_List(name="Sections", type=nbt.TAG_Compound)
    
    for section_y in range(16):
        base_y = section_y * 16
        
        has_any_block = False
        for y_in_sec in range(16):
            y = base_y + y_in_sec
            for z in range(16):
                for x in range(16):
                    old_idx = (x * 16 + z) * 256 + y
                    if old_blocks[old_idx] != 0:
                        has_any_block = True
                        break
                if has_any_block: break
            if has_any_block: break
                
        if not has_any_block:
            continue
            
        sec_blocks = bytearray(4096)
        sec_data = bytearray(2048)
        sec_sky = bytearray(2048)
        sec_block_light = bytearray(2048)
        
        for i in range(2048):
            sec_sky[i] = 0xFF
            
        for y_in_sec in range(16):
            y = base_y + y_in_sec
            for z in range(16):
                for x in range(16):
                    old_idx = (x * 16 + z) * 256 + y
                    sec_idx = x + z * 16 + y_in_sec * 256
                    
                    sec_blocks[sec_idx] = old_blocks[old_idx]
                    
                    val_data = get_nibble_value(old_data, x * 16 + z, y)
                    set_nibble_in_sec(sec_data, sec_idx, val_data)
                    
                    val_sky = get_nibble_value(old_sky, x * 16 + z, y)
                    set_nibble_in_sec(sec_sky, sec_idx, val_sky)
                    
                    val_block = get_nibble_value(old_block_light, x * 16 + z, y)
                    set_nibble_in_sec(sec_block_light, sec_idx, val_block)
                    
        sec_tag = nbt.TAG_Compound()
        sec_tag.tags.append(nbt.TAG_Byte(name="Y", value=section_y))
        
        b_array = nbt.TAG_Byte_Array(name="Blocks")
        b_array.value = sec_blocks
        sec_tag.tags.append(b_array)
        
        d_array = nbt.TAG_Byte_Array(name="Data")
        d_array.value = sec_data
        sec_tag.tags.append(d_array)
        
        s_array = nbt.TAG_Byte_Array(name="SkyLight")
        s_array.value = sec_sky
        sec_tag.tags.append(s_array)
        
        bl_array = nbt.TAG_Byte_Array(name="BlockLight")
        bl_array.value = sec_block_light
        sec_tag.tags.append(bl_array)
        
        sections.tags.append(sec_tag)
        
    level.tags.append(sections)
    
    entities = nbt.TAG_List(name="Entities", type=nbt.TAG_Compound)
    tile_entities = nbt.TAG_List(name="TileEntities", type=nbt.TAG_Compound)
    
    if dynamic_root is not None:
        try:
            if "Entities" in dynamic_root and isinstance(dynamic_root["Entities"], nbt.TAG_List):
                entities = dynamic_root["Entities"]
                entities.name = "Entities"
                fix_uuid_strings(entities)
        except Exception: pass
            
        try:
            if "TileEntities" in dynamic_root and isinstance(dynamic_root["TileEntities"], nbt.TAG_List):
                tile_entities = dynamic_root["TileEntities"]
                tile_entities.name = "TileEntities"
                fix_uuid_strings(tile_entities)
        except Exception: pass
            
        try:
            if "TileTicks" in dynamic_root:
                level.tags.append(dynamic_root["TileTicks"])
        except Exception: pass
            
    level.tags.append(entities)
    level.tags.append(tile_entities)
    
    root.tags.append(level)
    return root

class JavaRegionFileWriter:
    def __init__(self, filepath):
        self.filepath = filepath
        self.buffer = bytearray(8192)
        self.offsets = [0] * 1024
        self.timestamps = [0] * 1024
        self.next_sector = 2
        
    def write_chunk(self, local_x: int, local_z: int, uncompressed_nbt_bytes: bytes):
        if not (0 <= local_x < 32) or not (0 <= local_z < 32):
            return
            
        compressed = zlib.compress(uncompressed_nbt_bytes, 6)
        payload_len = 1 + len(compressed)
        total_len = 4 + payload_len
        sectors_needed = (total_len + 4095) // 4096
        if sectors_needed >= 256:
            return
            
        sector_start = self.next_sector
        self.next_sector += sectors_needed
        
        offset_pos = sector_start * 4096
        if offset_pos + sectors_needed * 4096 > len(self.buffer):
            self.buffer.extend(b'\x00' * (offset_pos + sectors_needed * 4096 - len(self.buffer)))
            
        struct.pack_into(">I", self.buffer, offset_pos, payload_len)
        self.buffer[offset_pos + 4] = 2
        self.buffer[offset_pos + 5 : offset_pos + 5 + len(compressed)] = compressed
        
        offset_val = (sector_start << 8) | sectors_needed
        idx = local_x + local_z * 32
        self.offsets[idx] = offset_val
        self.timestamps[idx] = int(time.time())
        
    def save(self):
        for i in range(1024):
            struct.pack_into(">I", self.buffer, i * 4, self.offsets[i])
        for i in range(1024):
            struct.pack_into(">I", self.buffer, 4096 + i * 4, self.timestamps[i])
            
        os.makedirs(os.path.dirname(self.filepath) or '.', exist_ok=True)
        temp_filepath = self.filepath + ".tmp"
        with open(temp_filepath, 'wb') as f:
            f.write(self.buffer)
        os.rename(temp_filepath, self.filepath)

def convert_lce_region_file(src_path: str, dest_path: str, queue=None, task_id=None):
    try:
        if queue:
            queue.put((task_id, 'start', os.path.basename(src_path)))
            
        with open(src_path, 'rb') as f:
            region_bytes = f.read()
            
        if len(region_bytes) < 8192:
            return
            
        writer = JavaRegionFileWriter(dest_path)
        converted_count = 0
        
        for index in range(1024):
            if queue and index % 16 == 0:
                queue.put((task_id, 'progress', index))
                
            offset_entry = struct.unpack_from("<I", region_bytes, index * 4)[0]
            if offset_entry == 0: continue
                
            size_sectors = offset_entry & 0xFF
            sector_offset = (offset_entry >> 8) & 0xFFFFFF
            
            if sector_offset <= 0: continue
                
            chunk_pos = sector_offset * 4096
            if chunk_pos + 8 > len(region_bytes): continue
                
            compressed_len_raw = struct.unpack_from("<I", region_bytes, chunk_pos)[0]
            uses_rle = (compressed_len_raw & 0x80000000) != 0
            compressed_len = compressed_len_raw & 0x7FFFFFFF
            decompressed_len = struct.unpack_from("<I", region_bytes, chunk_pos + 4)[0]
            
            if compressed_len <= 0 or chunk_pos + 8 + compressed_len > len(region_bytes):
                continue
                
            compressed_data = region_bytes[chunk_pos + 8 : chunk_pos + 8 + compressed_len]
            
            try:
                rle_data = zlib.decompress(compressed_data)
                if uses_rle:
                    uncompressed_payload = rle_decode(rle_data, decompressed_len)
                else:
                    uncompressed_payload = rle_data
                    
                local_x = index & 31
                local_z = index >> 5
                
                java_nbt_file = decode_lce_chunk_payload(uncompressed_payload)
                out_buf = io.BytesIO()
                java_nbt_file.write_file(buffer=out_buf)
                java_nbt_bytes = out_buf.getvalue()
                
                writer.write_chunk(local_x, local_z, java_nbt_bytes)
                converted_count += 1
            except Exception:
                pass
                
        if converted_count > 0:
            writer.save()
            
    except Exception as e:
        print(f"Error converting {src_path}: {e}")
    finally:
        if queue:
            queue.put((task_id, 'done', 1024))

def parse_region_filename(rel_path: str) -> tuple[str, str] | None:
    norm = rel_path.replace('\\', '/')
    base = os.path.basename(norm)
    
    if not base.endswith('.mcr'): return None
    stem = base[:-4]
    
    if norm.startswith('DIM-1r.'):
        parts = stem[len('DIM-1r.'):].split('.')
        dim = "DIM-1"
    elif norm.startswith('DIM1/r.'):
        parts = stem[len('r.'):].split('.')
        dim = "DIM1"
    elif base.startswith('r.'):
        parts = stem[2:].split('.')
        dim = ""
    else:
        return None
        
    if len(parts) < 2: return None
    rx, rz = parts[0], parts[1]
    
    dest_rel = f"{dim}/region/r.{rx}.{rz}.mca" if dim else f"region/r.{rx}.{rz}.mca"
    return rel_path, dest_rel

def convert_all_regions(input_dir: str, output_dir: str, progress_mgr=None):
    tasks = []
    for root_dir, _, files in os.walk(input_dir):
        for file in files:
            if not file.endswith(".mcr"): continue
            src_file_path = os.path.join(root_dir, file)
            rel_path = os.path.relpath(src_file_path, input_dir)
            mapping = parse_region_filename(rel_path)
            if mapping:
                dest_path = os.path.join(output_dir, mapping[1])
                if progress_mgr and progress_mgr.is_file_created(dest_path) and os.path.exists(dest_path):
                    continue
                tasks.append((src_file_path, dest_path))

    if not tasks:
        print("No .mcr files found to convert.")
        return

    max_workers = os.cpu_count() or 1
    num_slots = min(max_workers, len(tasks))
    print(f"Converting {len(tasks)} regions using up to {max_workers} threads...\n")
    
    try:
        manager = multiprocessing.Manager()
        queue = manager.Queue()
        executor_cls = ProcessPoolExecutor
        # Test executor creation to quickly catch SemLock issues
        _test_exec = executor_cls(max_workers=max_workers)
        _test_exec.shutdown()
    except OSError:
        queue = qlib.Queue()
        from concurrent.futures import ThreadPoolExecutor
        executor_cls = ThreadPoolExecutor
        max_workers = 1
        num_slots = min(max_workers, len(tasks))
        print("Warning: Failed to initialize Multiprocessing. Falling back to safe single-thread processing.")
        
    tasks_args = [(src, dest, queue, i) for i, (src, dest) in enumerate(tasks, 1)]
    
    with executor_cls(max_workers=max_workers) as executor:
        for arg in tasks_args:
            executor.submit(convert_lce_region_file, *arg)
            
        active_slots = [None] * num_slots
        task_to_slot = {}
        
        dynamic_height = num_slots + 1
        
        print("\n" * dynamic_height, end="")
        sys.stdout.flush()
        
        finished_tasks = 0
        total_tasks = len(tasks)
        pad = len(str(total_tasks))
        
        from scripts import progress
        def redraw():
            print("\n" * dynamic_height, end="")
            sys.stdout.flush()
        progress.g_on_resume = redraw
        
        while finished_tasks < total_tasks:
            newly_finished = []
            try:
                while True:
                    t_id, status, val = queue.get_nowait()
                    if status == 'start':
                        task_to_slot[t_id] = {'slot': None, 'name': val, 'prog': 0, 'idx': t_id}
                    elif status == 'progress':
                        if t_id in task_to_slot:
                            task_to_slot[t_id]['prog'] = val
                    elif status == 'done':
                        if t_id in task_to_slot:
                            task_to_slot[t_id]['prog'] = 1024
                            dest_path = tasks[t_id - 1][1]
                            if progress_mgr and os.path.exists(dest_path):
                                progress_mgr.mark_file_created(dest_path)
                        newly_finished.append(t_id)
                        finished_tasks += 1
            except qlib.Empty:
                pass
                
            for i in range(num_slots):
                t_id = active_slots[i]
                if t_id is not None and task_to_slot[t_id]['prog'] >= 1024:
                    active_slots[i] = None
                    
            for t_id, info in task_to_slot.items():
                if info['slot'] is None and info['prog'] < 1024:
                    if None in active_slots:
                        slot = active_slots.index(None)
                        active_slots[slot] = t_id
                        info['slot'] = slot
    
            sys.stdout.write(f"\033[{dynamic_height}A")
            
            for t_id in newly_finished:
                name = task_to_slot[t_id]['name']
                idx = task_to_slot[t_id]['idx']
                bar = '#' * 25
                line = f"({idx:>{pad}}/{total_tasks}) {name:<18} 100% [{bar}]"
                sys.stdout.write(f"\033[K{line}\n")
                
            sys.stdout.write("\033[K" + "-" * 66 + "\n")
                
            active_tasks = [t_id for t_id in active_slots if t_id is not None]
            active_tasks.sort(key=lambda t_id: task_to_slot[t_id]['idx'])
            
            for i in range(num_slots):
                if i < len(active_tasks):
                    t_id = active_tasks[i]
                    name = task_to_slot[t_id]['name']
                    prog = task_to_slot[t_id]['prog']
                    idx = task_to_slot[t_id]['idx']
                    
                    pct = int((prog / 1024) * 100)
                    bar_len = 25
                    filled = int((prog / 1024) * bar_len)
                    empty = bar_len - filled
                    bar = '#' * filled + '-' * empty
                    
                    line = f"({idx:>{pad}}/{total_tasks}) {name:<18} {pct:>3}% [{bar}]"
                else:
                    line = ""
                    
                sys.stdout.write(f"\033[K{line}\n")
            
            sys.stdout.flush()
            time.sleep(0.05)
            
        sys.stdout.write(f"\033[{dynamic_height}A\033[J")
        sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python convert_chunks.py <input_region_dir> <output_region_dir>")
        sys.exit(1)
        
    import os
    # Add parent directory to sys.path to allow running as a script directly
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from scripts.progress import ProgressManager, setup_signal_handler
    
    pm = ProgressManager(sys.argv[2])
    setup_signal_handler(pm, sys.argv[1], sys.argv[2])
    convert_all_regions(sys.argv[1], sys.argv[2], progress_mgr=pm)
