import sys
import os
from nbt import nbt


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

def inject_player_data(level_dat_path: str, players_dir: str, target_username: str, kept_players: list = None):
    if not os.path.exists(level_dat_path):
        print(f"Error: {level_dat_path} does not exist.")
        return
        
    if not os.path.exists(players_dir):
        print(f"Error: {players_dir} does not exist.")
        return
        
    try:
        level_nbt = nbt.NBTFile(level_dat_path)
    except Exception as e:
        print(f"Failed to open level.dat: {e}")
        return
        
    data_tag = level_nbt.get("Data")
    if not data_tag:
        print("Error: Invalid level.dat format.")
        return

    found_main = False
    
    # Process all player files
    for filename in os.listdir(players_dir):
        if not filename.endswith(".dat"):
            continue
            
        old_path = os.path.join(players_dir, filename)
        try:
            # Safely attempt to read as GZIP, fallback to uncompressed if it fails
            try:
                player_nbt = nbt.NBTFile(old_path)
            except Exception:
                import io
                with open(old_path, 'rb') as f:
                    player_nbt = nbt.NBTFile(buffer=io.BytesIO(f.read()))
            
            uuid_tag = player_nbt.get("UUID")
            
            if uuid_tag and isinstance(uuid_tag, nbt.TAG_String):
                username = uuid_tag.value
                
                # Handle kept_players filter
                if kept_players is not None and username not in kept_players:
                    print(f"Discarding player '{username}'...")
                    del player_nbt
                    try: os.remove(old_path)
                    except: pass
                    continue
                    
                # Fix malformed UUID strings to prevent Modern Minecraft upgrade crashes
                fix_uuid_strings(player_nbt)
                
                # Check if this is the target main player
                if username == target_username:
                    print(f"Found main player '{username}' in {filename}. Injecting into level.dat...")
                    
                    # Remove existing Player tag if it exists to prevent duplication corruption
                    if "Player" in data_tag:
                        del data_tag["Player"]
                        
                    # Clone the player data to the Player tag
                    player_nbt.name = "Player"
                    data_tag.tags.append(player_nbt)
                    found_main = True
                
                # Rename the file to username.dat for LAN/Multiplayer compatibility in 1.6.4
                new_filename = f"{username}.dat"
                new_path = os.path.join(players_dir, new_filename)
                
                # Save the fixed player NBT as GZIPPED (Java 1.6.4 requirement)
                import gzip
                temp_path = new_path + ".tmp"
                with gzip.open(temp_path, "wb") as f:
                    player_nbt.write_file(buffer=f)
                
                if old_path != new_path and os.path.exists(old_path):
                    try: os.remove(old_path)
                    except: pass
                    
                if os.path.exists(new_path):
                    try: os.remove(new_path)
                    except: pass
                os.rename(temp_path, new_path)
                
                if old_path != new_path:
                    print(f"Renamed and fixed {filename} -> {new_filename}")
                else:
                    print(f"Fixed UUIDs in {filename}")
                    
        except Exception as e:
            print(f"Failed to process {filename}: {e}")
            
    if found_main:
        # Save level.dat atomically to prevent corruption on interrupt
        temp_path = level_dat_path + ".tmp"
        level_nbt.write_file(temp_path)
        
        if os.path.exists(level_dat_path):
            # On Windows, os.rename can fail if target exists
            try: os.remove(level_dat_path)
            except: pass
        os.rename(temp_path, level_dat_path)
        
        print(f"Successfully injected player '{target_username}' into level.dat!")
    else:
        print(f"\n[ALERT] Target player '{target_username}' not found in world data. No changes made to level.dat.")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python 4_inject_player.py <level_dat_path> <players_dir> <target_username>")
        sys.exit(1)
        
    inject_player_data(sys.argv[1], sys.argv[2], sys.argv[3])
