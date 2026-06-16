import os
import sys
import struct
import zlib

def pack_ms(input_dir, output_ms_path, progress_mgr=None):
    print(f"Packing {input_dir} into {output_ms_path}...")
    
    file_records = []
    file_data_blocks = []
    
    current_offset = 12 # 4 bytes table offset + 8 bytes header
    
    for root, dirs, files in os.walk(input_dir):
        for f in sorted(files):
            if f.endswith('.tmp'): continue
            
            file_path = os.path.join(root, f)
            rel_path = os.path.relpath(file_path, input_dir)
            lce_name = rel_path.replace('\\', '/')
            
            with open(file_path, 'rb') as f_in:
                data = f_in.read()
                
            size = len(data)
            file_records.append((lce_name, size, current_offset))
            file_data_blocks.append(data)
            
            current_offset += size
            
    table_offset = current_offset
    
    fat_blocks = []
    import time
    timestamp = int(time.time())
    
    for name, size, offset in file_records:
        record = bytearray(144)
        name_bytes = name.encode('utf-16le')
        if len(name_bytes) > 126:
            name_bytes = name_bytes[:126]
        record[0:len(name_bytes)] = name_bytes
        
        struct.pack_into('<I', record, 128, size)
        struct.pack_into('<I', record, 132, offset)
        struct.pack_into('<I', record, 136, timestamp)
        struct.pack_into('<I', record, 140, 0)
        fat_blocks.append(record)
        
    uncompressed = bytearray()
    uncompressed.extend(struct.pack('<I', table_offset))
    uncompressed.extend(struct.pack('<I', len(file_records)))
    uncompressed.extend(b'\x09\x00\x09\x00')
    
    for data in file_data_blocks:
        uncompressed.extend(data)
    for record in fat_blocks:
        uncompressed.extend(record)
        
    print("Compressing data...")
    compressed = zlib.compress(uncompressed, 6)
    
    decompressed_size = len(uncompressed)
    
    final_data = bytearray()
    final_data.extend(struct.pack('<I', 0)) # Padding
    final_data.extend(struct.pack('<I', decompressed_size))
    final_data.extend(compressed)
    
    os.makedirs(os.path.dirname(output_ms_path) or '.', exist_ok=True)
    temp_out = output_ms_path + ".tmp"
    with open(temp_out, 'wb') as f_out:
        f_out.write(final_data)
        
    if os.path.exists(output_ms_path):
        os.remove(output_ms_path)
    os.rename(temp_out, output_ms_path)
    
    if progress_mgr:
        progress_mgr.mark_file_created(output_ms_path)
        progress_mgr.mark_step_completed("pack")
        
    print(f"Packing complete! Size: {len(final_data)} bytes")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python pack_ms.py <input_dir> <output_ms_path>")
        sys.exit(1)
        
    pack_ms(sys.argv[1], sys.argv[2])
