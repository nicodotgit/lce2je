import sys
import os
import hashlib
import io
from nbt import nbt

def get_numeric_id(username: str) -> int:
    # Generate a 64-bit unsigned int from the username
    md5 = hashlib.md5(username.encode('utf-8')).digest()
    return int.from_bytes(md5[:8], byteorder='little', signed=False)

def extract_all_players(level_dat_path: str, players_dir: str, mapping_dict: dict):
    if not os.path.exists(level_dat_path):
        print(f"Error: {level_dat_path} does not exist.")
        return
        
    os.makedirs(players_dir, exist_ok=True)
    
    # 1. Process level.dat
    if os.path.exists(level_dat_path):
        try:
            with open(level_dat_path, "rb") as f:
                level_nbt = nbt.NBTFile(buffer=f)
                
            data_tag = level_nbt.get("Data")
            if data_tag and "Player" in data_tag:
                # Find if any mapped player uses level.dat
                host_username = None
                host_data = None
                for uname, data in mapping_dict.items():
                    if data.get("source") == "level.dat":
                        host_username = uname
                        host_data = data
                        break
                        
                if host_username and host_data.get("action") != "ignore":
                    player_tag = data_tag["Player"]
                    
                    # Create the new player NBT file
                    player_nbt = nbt.NBTFile()
                    player_nbt.name = "" # Root tag has empty name
                    
                    # Copy all tags from Player into the new root
                    for tag in player_tag.tags:
                        player_nbt.tags.append(tag)
                        
                    # Inject UUID tag
                    if "UUID" in player_nbt:
                        del player_nbt["UUID"]
                    player_nbt.tags.append(nbt.TAG_String(name="UUID", value=host_username))
                    
                    # Parse the UID
                    if host_data.get("action") == "uid" and "uid" in host_data:
                        uid_str = host_data["uid"]
                        if uid_str.lower().startswith('0x'):
                            numeric_id = int(uid_str, 16)
                        else:
                            try:
                                numeric_id = int(uid_str)
                            except ValueError:
                                print(f"Warning: UID for {host_username} is not valid. Falling back to hash.")
                                numeric_id = get_numeric_id(uid_str)
                    else:
                        numeric_id = get_numeric_id(host_username)
                        
                    new_path = os.path.join(players_dir, f"{numeric_id}.dat")
                    temp_path = new_path + ".tmp"
                    player_buf = io.BytesIO()
                    player_nbt.write_file(buffer=player_buf)
                    with open(temp_path, "wb") as f:
                        f.write(player_buf.getvalue())
                    os.rename(temp_path, new_path)
                    print(f"Extracted Host '{host_username}' to {numeric_id}.dat")
                
                # Always remove Player tag from level.dat to comply with LCE structure
                del data_tag["Player"]
                
                # Save level.dat uncompressed
                temp_level = level_dat_path + ".tmp"
                level_buf = io.BytesIO()
                level_nbt.write_file(buffer=level_buf)
                with open(temp_level, "wb") as f:
                    f.write(level_buf.getvalue())
                os.rename(temp_level, level_dat_path)
                print("Cleaned Player tag from level.dat")
        except Exception as e:
            print(f"Failed to process level.dat: {e}")
            
    # 2. Process players_dir guests
    if os.path.exists(players_dir):
        for filename in os.listdir(players_dir):
            if not filename.endswith(".dat"): continue
            
            username = filename[:-4]
            filepath = os.path.join(players_dir, filename)
            
            # Skip completely numeric files that might have just been generated
            if username.isdigit() and len(username) > 10:
                continue
                
            if username in mapping_dict:
                data = mapping_dict[username]
                if data.get("source") == "players_dir":
                    if data.get("action") != "ignore":
                        try:
                            with open(filepath, "rb") as f:
                                player_nbt = nbt.NBTFile(buffer=f)
                                
                            if "UUID" in player_nbt:
                                del player_nbt["UUID"]
                            player_nbt.tags.append(nbt.TAG_String(name="UUID", value=username))
                            
                            if data.get("action") == "uid" and "uid" in data:
                                uid_str = data["uid"]
                                if uid_str.lower().startswith('0x'):
                                    numeric_id = int(uid_str, 16)
                                else:
                                    try:
                                        numeric_id = int(uid_str)
                                    except ValueError:
                                        print(f"Warning: UID for {username} is not valid. Falling back to hash.")
                                        numeric_id = get_numeric_id(uid_str)
                            else:
                                numeric_id = get_numeric_id(username)
                                
                            new_path = os.path.join(players_dir, f"{numeric_id}.dat")
                            temp_path = new_path + ".tmp"
                            player_buf = io.BytesIO()
                            player_nbt.write_file(buffer=player_buf)
                            with open(temp_path, "wb") as f:
                                f.write(player_buf.getvalue())
                            os.rename(temp_path, new_path)
                            print(f"Converted guest '{username}' to {numeric_id}.dat")
                        except Exception as e:
                            print(f"Failed to convert player {username}: {e}")
                    
                    # Delete the old <username>.dat file
                    try: os.remove(filepath)
                    except: pass
                else:
                    # Player was mapped to level.dat or ignored, drop the players_dir copy
                    try: os.remove(filepath)
                    except: pass
            else:
                # Unmapped non-numeric player. Delete it to prevent errors.
                try: os.remove(filepath)
                except: pass

if __name__ == "__main__":
    pass
