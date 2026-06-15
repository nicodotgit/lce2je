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

def rle_encode(data: bytes) -> bytearray:
    output = bytearray()
    in_pos = 0
    length = len(data)
    
    while in_pos < length:
        current = data[in_pos]
        run_length = 1
        while in_pos + run_length < length and data[in_pos + run_length] == current and run_length < 256:
            run_length += 1
            
        if current == 255:
            if run_length <= 3:
                output.append(255)
                output.append(run_length - 1)
            else:
                output.append(255)
                output.append(run_length - 1)
                output.append(255)
        else:
            if run_length >= 4:
                output.append(255)
                output.append(run_length - 1)
                output.append(current)
            else:
                for _ in range(run_length):
                    output.append(current)
                    
        in_pos += run_length
        
    return output

def get_compressed_tile_index(block: int, tile: int) -> int:
    index = ((block & 0x180) << 6) | ((block & 0x060) << 4) | ((block & 0x01F) << 2)
    index |= ((tile & 0x30) << 7) | ((tile & 0x0C) << 5) | (tile & 0x03)
    return index

def write_compressed_tile_storage(blocks: bytearray) -> bytes:
    block_indices = bytearray(1024)
    data_region = bytearray()
    
    for block in range(512):
        tile_bytes = bytearray(64)
        is_homogenous = True
        first_val = blocks[get_compressed_tile_index(block, 0)]
        
        for tile in range(64):
            val = blocks[get_compressed_tile_index(block, tile)]
            tile_bytes[tile] = val
            if val != first_val:
                is_homogenous = False
                
        if is_homogenous:
            block_index = (first_val << 8) | 7
        else:
            data_offset = len(data_region)
            block_index = (data_offset << 1) | 3
            data_region.extend(tile_bytes)
            
        struct.pack_into("<H", block_indices, block * 2, block_index)
        
    blob = bytearray()
    blob.extend(block_indices)
    blob.extend(data_region)
    
    allocated_size = len(blob)
    res = bytearray()
    res.extend(struct.pack(">i", allocated_size))
    res.extend(blob)
    return res

def get_nibble_value(nibble_data: bytearray, xz: int, y: int) -> int:
    pos = (xz << 7) | y
    slot = pos >> 1
    part = pos & 1
    value = nibble_data[slot]
    return (value & 0x0F) if part == 0 else ((value >> 4) & 0x0F)

def write_sparse_nibble_storage(nibble_data: bytearray) -> bytes:
    plane_indices = bytearray(128)
    plane_data = bytearray()
    
    current_plane_index = 0
    for y in range(128):
        plane_bytes = bytearray(128)
        is_empty = True
        is_all_15 = True
        
        for xz in range(128):
            val1 = get_nibble_value(nibble_data, xz << 1, y)
            val2 = get_nibble_value(nibble_data, (xz << 1) + 1, y)
            packed = val1 | (val2 << 4)
            plane_bytes[xz] = packed
            
            if packed != 0:
                is_empty = False
            if packed != 0xFF:
                is_all_15 = False
                
        if is_empty:
            plane_indices[y] = 128
        elif is_all_15:
            plane_indices[y] = 129
        else:
            plane_indices[y] = current_plane_index
            plane_data.extend(plane_bytes)
            current_plane_index += 1
            
    blob = bytearray()
    blob.extend(plane_indices)
    blob.extend(plane_data)
    
    res = bytearray()
    res.extend(struct.pack(">i", current_plane_index))
    res.extend(blob)
    return res

def split_block_sections(combined: bytearray) -> tuple[bytearray, bytearray]:
    lower = bytearray(32768)
    upper = bytearray(32768)
    for xz in range(256):
        lower[xz*128 : xz*128 + 128] = combined[xz*256 : xz*256 + 128]
        upper[xz*128 : xz*128 + 128] = combined[xz*256 + 128 : xz*256 + 256]
    return lower, upper

def split_nibble_sections(combined: bytearray) -> tuple[bytearray, bytearray]:
    lower = bytearray(16384)
    upper = bytearray(16384)
    for xz in range(256):
        lower[xz*64 : xz*64 + 64] = combined[xz*128 : xz*128 + 64]
        upper[xz*64 : xz*64 + 64] = combined[xz*128 + 64 : xz*128 + 128]
    return lower, upper

def get_nibble_in_sec(arr: bytearray, index: int) -> int:
    byte_idx = index >> 1
    if (index & 1) == 0:
        return arr[byte_idx] & 0x0F
    else:
        return (arr[byte_idx] >> 4) & 0x0F

def set_nibble_value(nibble_data: bytearray, xz: int, y: int, value: int):
    pos = (xz << 8) | y
    slot = pos >> 1
    part = pos & 1
    value &= 0x0F
    if part == 0:
        nibble_data[slot] = (nibble_data[slot] & 0xF0) | value
    else:
        nibble_data[slot] = (nibble_data[slot] & 0x0F) | (value << 4)

def encode_lce_chunk_payload(java_nbt_file: nbt.NBTFile) -> bytes:
    level = java_nbt_file.get("Level")
    if not level:
        raise ValueError("Invalid Java NBT: missing Level")
        
    chunk_x = level["xPos"].value
    chunk_z = level["zPos"].value
    last_update = level["LastUpdate"].value if "LastUpdate" in level else 0
    inhabited_time = level["InhabitedTime"].value if "InhabitedTime" in level else 0
    
    old_blocks = bytearray(FULL_CHUNK_BLOCKS)
    old_data = bytearray(FULL_CHUNK_NIBBLES)
    old_sky = bytearray(FULL_CHUNK_NIBBLES)
    old_block_light = bytearray(FULL_CHUNK_NIBBLES)
    
    for i in range(FULL_CHUNK_NIBBLES):
        old_sky[i] = 0xFF
        
    if "Sections" in level:
        for sec in level["Sections"].tags:
            sec_y = sec["Y"].value
            if sec_y < 0 or sec_y > 15: continue
            
            base_y = sec_y * 16
            blocks = sec["Blocks"].value
            data = sec["Data"].value
            sky = sec["SkyLight"].value if "SkyLight" in sec else None
            block_light = sec["BlockLight"].value if "BlockLight" in sec else None
            
            for y_in_sec in range(16):
                y = base_y + y_in_sec
                for z in range(16):
                    for x in range(16):
                        sec_idx = x + z * 16 + y_in_sec * 256
                        old_idx = (x * 16 + z) * 256 + y
                        
                        old_blocks[old_idx] = blocks[sec_idx]
                        set_nibble_value(old_data, x * 16 + z, y, get_nibble_in_sec(data, sec_idx))
                        if sky:
                            set_nibble_value(old_sky, x * 16 + z, y, get_nibble_in_sec(sky, sec_idx))
                        if block_light:
                            set_nibble_value(old_block_light, x * 16 + z, y, get_nibble_in_sec(block_light, sec_idx))

    lower_blocks, upper_blocks = split_block_sections(old_blocks)
    lower_data, upper_data = split_nibble_sections(old_data)
    lower_sky_light, upper_sky_light = split_nibble_sections(old_sky)
    lower_block_light, upper_block_light = split_nibble_sections(old_block_light)
    
    height_map = level["HeightMap"].value if "HeightMap" in level else [0] * 256
    biomes = level["Biomes"].value if "Biomes" in level else [0] * 256
    
    terrain_populated = level["TerrainPopulated"].value if "TerrainPopulated" in level else 1
    
    # Pack dynamic tags
    dynamic_root = nbt.NBTFile()
    dynamic_root.name = ""
    if "Entities" in level:
        dynamic_root.tags.append(level["Entities"])
    if "TileEntities" in level:
        dynamic_root.tags.append(level["TileEntities"])
    if "TileTicks" in level:
        dynamic_root.tags.append(level["TileTicks"])
        
    dynamic_buf = io.BytesIO()
    dynamic_root.write_file(buffer=dynamic_buf)
    dynamic_bytes = dynamic_buf.getvalue()
    
    payload = bytearray()
    payload.extend(struct.pack(">h", 9)) # Version 9
    payload.extend(struct.pack(">i", chunk_x))
    payload.extend(struct.pack(">i", chunk_z))
    payload.extend(struct.pack(">q", last_update))
    payload.extend(struct.pack(">q", inhabited_time))
    
    payload.extend(write_compressed_tile_storage(lower_blocks))
    payload.extend(write_compressed_tile_storage(upper_blocks))
    
    payload.extend(write_sparse_nibble_storage(lower_data))
    payload.extend(write_sparse_nibble_storage(upper_data))
    
    payload.extend(write_sparse_nibble_storage(lower_sky_light))
    payload.extend(write_sparse_nibble_storage(upper_sky_light))
    
    payload.extend(write_sparse_nibble_storage(lower_block_light))
    payload.extend(write_sparse_nibble_storage(upper_block_light))
    
    hm_bytes = bytes([b & 0xFF for b in height_map])
    payload.extend(hm_bytes)
    payload.extend(struct.pack(">h", terrain_populated))
    biomes_bytes = bytes([b & 0xFF for b in biomes])
    payload.extend(biomes_bytes)
    
    payload.extend(dynamic_bytes)
    return bytes(payload)

class LCERegionFileWriter:
    def __init__(self, filepath):
        self.filepath = filepath
        self.buffer = bytearray(8192)
        self.next_sector = 2
        
    def write_chunk(self, local_x: int, local_z: int, uncompressed_payload: bytes):
        if not (0 <= local_x < 32) or not (0 <= local_z < 32):
            return
            
        rle_data = rle_encode(uncompressed_payload)
        compressed = zlib.compress(rle_data, 6)
        
        compressed_len = len(compressed)
        compressed_len_raw = compressed_len | 0x80000000 # Set MSB to indicate RLE
        decompressed_len = len(uncompressed_payload)
        
        payload_len = 8 + compressed_len
        sectors_needed = (payload_len + 4095) // 4096
        if sectors_needed >= 256:
            return
            
        sector_start = self.next_sector
        self.next_sector += sectors_needed
        
        offset_pos = sector_start * 4096
        if offset_pos + sectors_needed * 4096 > len(self.buffer):
            self.buffer.extend(b'\x00' * (offset_pos + sectors_needed * 4096 - len(self.buffer)))
            
        struct.pack_into("<I", self.buffer, offset_pos, compressed_len_raw)
        struct.pack_into("<I", self.buffer, offset_pos + 4, decompressed_len)
        self.buffer[offset_pos + 8 : offset_pos + 8 + compressed_len] = compressed
        
        offset_val = sectors_needed | (sector_start << 8)
        idx = local_x + local_z * 32
        struct.pack_into("<I", self.buffer, idx * 4, offset_val)
        
    def save(self):
        os.makedirs(os.path.dirname(self.filepath) or '.', exist_ok=True)
        temp_filepath = self.filepath + ".tmp"
        with open(temp_filepath, 'wb') as f:
            f.write(self.buffer)
        os.rename(temp_filepath, self.filepath)

def read_mca_chunks(filepath: str):
    chunks = []
    try:
        with open(filepath, 'rb') as f:
            region_bytes = f.read()
    except OSError:
        return chunks
        
    if len(region_bytes) < 8192:
        return chunks
        
    for index in range(1024):
        offset_val = struct.unpack_from(">I", region_bytes, index * 4)[0]
        if offset_val == 0: continue
        
        sector_offset = offset_val >> 8
        size_sectors = offset_val & 0xFF
        
        if sector_offset <= 0: continue
        chunk_pos = sector_offset * 4096
        if chunk_pos + 5 > len(region_bytes): continue
        
        payload_len = struct.unpack_from(">I", region_bytes, chunk_pos)[0]
        compression_type = region_bytes[chunk_pos + 4]
        
        if payload_len <= 1 or chunk_pos + 4 + payload_len > len(region_bytes):
            continue
            
        compressed_data = region_bytes[chunk_pos + 5 : chunk_pos + 4 + payload_len]
        
        try:
            if compression_type == 1:
                import gzip
                uncompressed = gzip.decompress(compressed_data)
            elif compression_type == 2:
                uncompressed = zlib.decompress(compressed_data)
            else:
                continue
                
            java_nbt_file = nbt.NBTFile(buffer=io.BytesIO(uncompressed))
            local_x = index & 31
            local_z = index >> 5
            chunks.append((local_x, local_z, java_nbt_file))
        except Exception:
            pass
            
    return chunks

def convert_java_region_file(src_path: str, dest_path: str, queue=None, task_id=None):
    try:
        if queue:
            queue.put((task_id, 'start', os.path.basename(src_path)))
            
        chunks = read_mca_chunks(src_path)
        if not chunks:
            if queue: queue.put((task_id, 'done', 1024))
            return
            
        writer = LCERegionFileWriter(dest_path)
        converted_count = 0
        total_chunks = len(chunks)
        
        for i, (lx, lz, chunk_nbt) in enumerate(chunks):
            if queue and i % max(1, total_chunks // 16) == 0:
                queue.put((task_id, 'progress', int((i / total_chunks) * 1024)))
                
            try:
                lce_payload = encode_lce_chunk_payload(chunk_nbt)
                writer.write_chunk(lx, lz, lce_payload)
                converted_count += 1
            except Exception as e:
                pass
                
        if converted_count > 0:
            writer.save()
            
    except Exception as e:
        print(f"Error converting {src_path}: {e}")
    finally:
        if queue:
            queue.put((task_id, 'done', 1024))

def parse_region_filename_reverse(rel_path: str) -> tuple[str, str] | None:
    norm = rel_path.replace('\\', '/')
    base = os.path.basename(norm)
    
    if not base.endswith('.mca'): return None
    stem = base[:-4]
    
    if norm.startswith('DIM-1/region/r.'):
        parts = stem[2:].split('.')
        dim = "DIM-1"
    elif norm.startswith('DIM1/region/r.'):
        parts = stem[2:].split('.')
        dim = "DIM1"
    elif norm.startswith('region/r.'):
        parts = stem[2:].split('.')
        dim = ""
    else:
        return None
        
    if len(parts) < 2: return None
    rx, rz = parts[0], parts[1]
    
    dest_rel = f"{dim}r.{rx}.{rz}.mcr" if dim else f"r.{rx}.{rz}.mcr"
    return rel_path, dest_rel

def convert_all_regions_reverse(input_dir: str, output_dir: str, progress_mgr=None):
    tasks = []
    for root_dir, _, files in os.walk(input_dir):
        for file in files:
            if not file.endswith(".mca"): continue
            src_file_path = os.path.join(root_dir, file)
            rel_path = os.path.relpath(src_file_path, input_dir)
            mapping = parse_region_filename_reverse(rel_path)
            if mapping:
                dest_path = os.path.join(output_dir, mapping[1])
                if progress_mgr and progress_mgr.is_file_created(dest_path) and os.path.exists(dest_path):
                    continue
                tasks.append((src_file_path, dest_path))

    if not tasks:
        print("No .mca files found to convert.")
        return

    max_workers = os.cpu_count() or 1
    num_slots = min(max_workers, len(tasks))
    print(f"Converting {len(tasks)} regions using up to {max_workers} threads...\n")
    
    try:
        manager = multiprocessing.Manager()
        queue = manager.Queue()
        executor_cls = ProcessPoolExecutor
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
            executor.submit(convert_java_region_file, *arg)
            
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
        print("Usage: python convert_chunks_reverse.py <input_java_region_dir> <output_lce_region_dir>")
        sys.exit(1)
        
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from scripts.progress import ProgressManager, setup_signal_handler
    
    pm = ProgressManager(sys.argv[2])
    setup_signal_handler(pm, sys.argv[1], sys.argv[2])
    convert_all_regions_reverse(sys.argv[1], sys.argv[2], progress_mgr=pm)
