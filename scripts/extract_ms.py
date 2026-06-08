import struct
import os
import sys
import zlib

def extract_ms(filepath, out_dir):
    print(f"Opening {filepath}...")
    with open(filepath, 'rb') as f:
        # Check ZLIB magic (with prepended 8 bytes)
        magic = f.read(8)

        data = f.read()
        print("Decompressing...")
        try:
            uncompressed = zlib.decompress(data)
        except Exception as e:
            print(f"Decompression error: {e}")
            return
            
    print(f"Decompressed size: {len(uncompressed)} bytes")
    
    # Read the file table offset from the start of the uncompressed data
    table_offset = struct.unpack('<I', uncompressed[0:4])[0]
    print(f"File table offset: {table_offset}")
    
    os.makedirs(out_dir, exist_ok=True)
    
    # Read file records
    # Each record is 144 bytes long
    pos = table_offset
    count = 0
    while pos + 144 <= len(uncompressed):
        record = uncompressed[pos:pos+144]
        name_bytes = record[:128]
        name = name_bytes.decode('utf-16le', errors='ignore').split('\x00')[0]
        
        if not name:
            break
            
        size, offset = struct.unpack('<II', record[128:136])
        print(f"Extracting {name} (size: {size} bytes, offset: {offset})...")
        
        file_data = uncompressed[offset : offset+size]

        out_name = name.replace('\\', '/')
        out_path = os.path.join(out_dir, out_name)
        os.makedirs(os.path.dirname(out_path) or out_dir, exist_ok=True)
        
        with open(out_path, 'wb') as out_f:
            out_f.write(file_data)
            
        count += 1
        pos += 144
        
    print(f"Extraction complete! {count} files extracted.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python extract.py <LCE .ms file> <out_dir>")
    else:
        extract_ms(sys.argv[1], sys.argv[2])
