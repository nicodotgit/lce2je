import struct
import os
import sys
import zlib

def extract_ms(filepath, out_dir, progress_mgr=None):
    print(f"Opening {filepath}...")
    with open(filepath, 'rb') as f:
        # Check ZLIB magic (with prepended 8 bytes)
        magic = f.read(8)

        data = f.read()
        print("Decompressing...")
        try:
            uncompressed = zlib.decompress(data)
        except Exception as e:
            print(f"\nError: The provided world file '{filepath}' appears to be corrupted or invalid.", file=sys.stderr)
            print(f"Details: Decompression failed ({e})", file=sys.stderr)
            if progress_mgr and os.path.exists(progress_mgr.filepath):
                os.remove(progress_mgr.filepath)
            sys.exit(1)
            
    print(f"Decompressed size: {len(uncompressed)} bytes")
    
    try:
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
            
            if progress_mgr and progress_mgr.is_file_created(out_path) and os.path.exists(out_path):
                count += 1
                pos += 144
                continue
                
            os.makedirs(os.path.dirname(out_path) or out_dir, exist_ok=True)
            
            temp_out = out_path + ".tmp"
            with open(temp_out, 'wb') as out_f:
                out_f.write(file_data)
            os.rename(temp_out, out_path)
            
            if progress_mgr:
                progress_mgr.mark_file_created(out_path)
                
            count += 1
            pos += 144
            
        print(f"Extraction complete! {count} files extracted.")
    except Exception as e:
        print(f"\nError: Failed to parse '{filepath}'. The file structure is invalid or corrupt.", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        if progress_mgr and os.path.exists(progress_mgr.filepath):
            os.remove(progress_mgr.filepath)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python extract_ms.py <LCE .ms file> <out_dir>")
        sys.exit(1)
        
    # Add parent directory to sys.path to allow running as a script directly
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from scripts.progress import ProgressManager, setup_signal_handler
    
    pm = ProgressManager(sys.argv[2])
    setup_signal_handler(pm, sys.argv[2], sys.argv[2])
    extract_ms(sys.argv[1], sys.argv[2], progress_mgr=pm)
