import sys
import os
from nbt import nbt

def inject_player_data(level_dat_path: str, players_dir: str, target_username: str):
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
            player_nbt = nbt.NBTFile(old_path)
            uuid_tag = player_nbt.get("UUID")
            
            if uuid_tag and isinstance(uuid_tag, nbt.TAG_String):
                username = uuid_tag.value
                
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
                
                del player_nbt
                
                # Only rename if it's not already named correctly
                if old_path != new_path:
                    # If target exists (e.g. overwriting an older save), remove it first
                    if os.path.exists(new_path):
                        os.remove(new_path)
                    os.rename(old_path, new_path)
                    print(f"Renamed {filename} -> {new_filename}")
                    
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
