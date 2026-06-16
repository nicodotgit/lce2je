import os
import shutil
import sys
import gzip

def convert_layout_to_lce(java_dir, lce_temp_dir, progress_mgr=None):
    print(f"Converting layout from {java_dir} to {lce_temp_dir}...")
    os.makedirs(lce_temp_dir, exist_ok=True)

    for root, dirs, files in os.walk(java_dir):
        for f in files:
            src = os.path.join(root, f)
            rel_path = os.path.relpath(src, java_dir)

            # Reverse the path transformations
            norm_path = rel_path.replace('\\', '/')
            if norm_path.startswith('DIM-1/region/'):
                dest_rel = 'DIM-1' + norm_path[len('DIM-1/region/'):]
            elif norm_path.startswith('DIM1/region/'):
                dest_rel = 'DIM1/' + norm_path[len('DIM1/region/'):]
            elif norm_path.startswith('region/'):
                dest_rel = norm_path[len('region/'):]
            else:
                dest_rel = norm_path

            # Replace .mca extension with .mcr
            if dest_rel.endswith('.mca'):
                dest_rel = dest_rel[:-4] + '.mcr'
                
            dest_path = os.path.join(lce_temp_dir, dest_rel)

            if dest_rel.endswith('.mcr'):
                continue
                
            # Filter out Java-specific metadata files that crash the LCE engine
            base_name = os.path.basename(dest_rel)
            if base_name in ['session.lock', 'level.dat_old', 'level.dat_mcr']:
                continue
            
            # Filter out
            if dest_rel.startswith('data/'):
                if not (base_name.startswith('map_') or base_name in ['villages.dat', 'largeMapDataMappings.dat']):
                    continue
                
            if progress_mgr and progress_mgr.is_file_created(dest_path) and os.path.exists(dest_path):
                continue
                
            os.makedirs(os.path.dirname(dest_path) or lce_temp_dir, exist_ok=True)
            print(f"Processing {rel_path} -> {dest_rel}")
            
            temp_dest = dest_path + ".tmp"

            if f == 'level.dat' or f.endswith('.dat'):
                try:
                    with gzip.open(src, 'rb') as f_in:
                        uncompressed_data = f_in.read()
                except OSError:
                    with open(src, 'rb') as f_in:
                        uncompressed_data = f_in.read()
                        
                if f == 'level.dat':
                    try:
                        from nbt import nbt
                        import io
                        level_nbt = nbt.NBTFile(buffer=io.BytesIO(uncompressed_data))
                        data_tag = level_nbt.get("Data")
                        if data_tag:
                            chosen_size = "Large"
                            if progress_mgr:
                                size_val = progress_mgr.get_player_mapping("world_size")
                                if size_val:
                                    chosen_size = size_val
                            
                            if chosen_size == "Classic":
                                xz_size = 54; hell_scale = 3
                            elif chosen_size == "Small":
                                xz_size = 64; hell_scale = 3
                            elif chosen_size == "Medium":
                                xz_size = 192; hell_scale = 6
                            else: # Large
                                xz_size = 320; hell_scale = 8
                                
                            lce_defaults = {
                                "XZSize": (nbt.TAG_Int, xz_size),
                                "StrongholdX": (nbt.TAG_Int, 48),
                                "StrongholdY": (nbt.TAG_Int, 0),
                                "StrongholdZ": (nbt.TAG_Int, 32),
                                "StrongholdEndPortalX": (nbt.TAG_Int, 782),
                                "StrongholdEndPortalZ": (nbt.TAG_Int, 534),
                                "hasStronghold": (nbt.TAG_Byte, 1),
                                "hasStrongholdEndPortal": (nbt.TAG_Byte, 1),
                                "newSeaLevel": (nbt.TAG_Byte, 1),
                                "hasBeenInCreative": (nbt.TAG_Byte, 0),
                                "spawnBonusChest": (nbt.TAG_Byte, 0),
                                "ClassicMoat": (nbt.TAG_Int, 0),
                                "SmallMoat": (nbt.TAG_Int, 0),
                                "MediumMoat": (nbt.TAG_Int, 0),
                                "HellScale": (nbt.TAG_Int, hell_scale)
                            }
                            for tag_name, (tag_class, default_val) in lce_defaults.items():
                                if tag_name not in data_tag:
                                    data_tag.tags.append(tag_class(name=tag_name, value=default_val))
                                elif tag_name in ["XZSize", "HellScale"]:
                                    data_tag[tag_name].value = default_val
                            
                            out_buf = io.BytesIO()
                            level_nbt.write_file(buffer=out_buf)
                            uncompressed_data = out_buf.getvalue()
                    except Exception as e:
                        print(f"Error patching level.dat tags: {e}")
                
                with open(temp_dest, 'wb') as f_out:
                    f_out.write(uncompressed_data)
            else:
                shutil.copy2(src, temp_dest)
                
            os.rename(temp_dest, dest_path)
            if progress_mgr:
                progress_mgr.mark_file_created(dest_path)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python java_to_lce.py <input_java_dir> <output_lce_dir>")
        sys.exit(1)
        
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from scripts.progress import ProgressManager, setup_signal_handler
    
    pm = ProgressManager(sys.argv[2])
    setup_signal_handler(pm, sys.argv[2], sys.argv[2])
    convert_layout_to_lce(sys.argv[1], sys.argv[2], progress_mgr=pm)
