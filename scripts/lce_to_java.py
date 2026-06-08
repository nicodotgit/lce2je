import os
import shutil
import sys
import gzip

def convert_layout(extracted_dir, java_dir):
    print(f"Converting layout from {extracted_dir} to {java_dir}...")
    os.makedirs(java_dir, exist_ok=True)

    for root, dirs, files in os.walk(extracted_dir):
        for f in files:
            src = os.path.join(root, f)
            rel_path = os.path.relpath(src, extracted_dir)

            dest_rel = rel_path

            if rel_path.startswith('DIM-1r.'):
                dest_rel = 'DIM-1/region/' + rel_path[len('DIM-1'):]
            elif rel_path.startswith('DIM1/r.'):
                dest_rel = 'DIM1/region/' + rel_path[5:]
            elif rel_path.startswith('r.') and '/' not in rel_path:
                dest_rel = 'region/' + rel_path
                
            dest_path = os.path.join(java_dir, dest_rel)
            if f.endswith('.mcr'):
                continue
                
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            print(f"Processing {rel_path} -> {dest_rel}")
            
            # Java 1.6.4 expects level.dat and player data to be GZipped
            if f == 'level.dat' or f.endswith('.dat'):
                with open(src, 'rb') as f_in:
                    magic = f_in.read(2)
                    f_in.seek(0)
                    if magic != b'\x1f\x8b':
                        with gzip.open(dest_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    else:
                        shutil.copy2(src, dest_path)
            else:
                shutil.copy2(src, dest_path)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python 2_lce_to_java.py <extracted_lce_dir> <output_java_dir>")
    else:
        convert_layout(sys.argv[1], sys.argv[2])
