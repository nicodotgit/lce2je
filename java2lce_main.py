import sys

if sys.version_info < (3, 8):
    print("Error: LCE2Java requires Python 3.8 or higher.", file=sys.stderr)
    sys.exit(1)

try:
    from nbt import nbt
except ImportError:
    print("Error: Required dependency 'nbt' is not installed.", file=sys.stderr)
    print("Please run the tool using the corresponding wrapper for your OS or install dependencies with 'pip install -r requirements.txt' inside your venv.", file=sys.stderr)
    sys.exit(1)

import os
import argparse
import shutil

from scripts.java_to_lce import convert_layout_to_lce
from scripts.convert_chunks_reverse import convert_all_regions_reverse
from scripts.extract_player import extract_all_players
from scripts.pack_ms import pack_ms
from scripts.progress import ProgressManager, setup_signal_handler

def main():
    parser = argparse.ArgumentParser(description="Convert Minecraft Java 1.6.4 worlds back to Legacy Console Edition (LCE) saveData.ms")
    parser.add_argument("input_dir", help="Path to the Java 1.6.4 world directory")
    parser.add_argument("output_ms", help="Path to the output saveData.ms file")
    
    args = parser.parse_args()
    
    input_dir = os.path.abspath(args.input_dir)
    output_ms = os.path.abspath(args.output_ms)
    
    if not os.path.isdir(input_dir):
        print(f"Error: Input directory {input_dir} does not exist.")
        sys.exit(1)
        
    if os.path.exists(output_ms):
        print(f"Error: The output file '{output_ms}' already exists. Please delete it or specify a different path.")
        sys.exit(1)
        
    temp_dir = os.path.abspath("_temp_java2lce")
    
    try:
        progress_mgr = ProgressManager(os.path.dirname(output_ms))
        progress_mgr.set_input_file(input_dir)
        progress_mgr.cleanup_temp_files(temp_dir)
        
        setup_signal_handler(progress_mgr, temp_dir, os.path.dirname(output_ms))
        
        # Step 1: Convert Directory Layout & Un-GZip Data
        if not progress_mgr.is_step_completed("layout"):
            print(f"--- Step 1: Converting Layout ---")
            convert_layout_to_lce(input_dir, temp_dir, progress_mgr)
            progress_mgr.mark_step_completed("layout")
        else:
            print(f"--- Step 1: Converting Layout (Skipped - Already completed) ---")
            
        # Step 2: Extract Player Data
        if not progress_mgr.is_step_completed("extract_player"):
            if not progress_mgr.has_player_mapping():
                print("\n--- Interactive Player Mapping ---")
                has_host = False
                host_username = None
                level_dat_src = os.path.join(input_dir, "level.dat")
                if os.path.exists(level_dat_src):
                    try:
                        level_nbt = nbt.NBTFile(level_dat_src)
                        if "Data" in level_nbt and "Player" in level_nbt["Data"]:
                            has_host = True
                    except Exception:
                        pass
                        
                players_in_dir = []
                players_src_dir = os.path.join(input_dir, "players")
                if os.path.exists(players_src_dir):
                    for f in os.listdir(players_src_dir):
                        if f.endswith(".dat"):
                            players_in_dir.append(f[:-4])
                            
                if not has_host and not players_in_dir:
                    print("No players found. Skipping player mapping.")
                    progress_mgr.set_player_mapping("skip_all", True)
                else:
                    canonical_players = set(players_in_dir)
                    level_dat_player_name = None
                    
                    if has_host:
                        while level_dat_player_name is None:
                            try:
                                ans = input("\nA player was found in level.dat. What is the username of the host player in this world? (Leave blank to ignore): ").strip()
                                level_dat_player_name = ans
                            except EOFError:
                                print("\nInterrupted.")
                                sys.exit(1)
                        if level_dat_player_name:
                            canonical_players.add(level_dat_player_name)
                    
                    mapping_dict = {}
                    if level_dat_player_name:
                        mapping_dict[level_dat_player_name] = {"source": "level.dat"}
                    for p in players_in_dir:
                        if p != level_dat_player_name:
                            mapping_dict[p] = {"source": "players_dir"}
                            
                    # Ask who is the LCE Win64 Host
                    player_list = sorted(list(canonical_players))
                    win64_host = None
                    if player_list:
                        print("\n--- Select LCE Win64 Host ---")
                        for i, p in enumerate(player_list):
                            source_str = " (from level.dat)" if p == level_dat_player_name else " (from players/)"
                            print(f" {i+1}) {p}{source_str}")
                        print(f" {len(player_list)+1}) None / Not using LCE Win64")
                        
                        while True:
                            try:
                                ans = input("Select the player who will be the local Host: ").strip()
                                if ans.isdigit():
                                    idx = int(ans) - 1
                                    if 0 <= idx < len(player_list):
                                        win64_host = player_list[idx]
                                        break
                                    elif idx == len(player_list):
                                        break
                            except EOFError:
                                print("\nInterrupted.")
                                sys.exit(1)
                                
                    if win64_host:
                        mapping_dict[win64_host]["action"] = "uid"
                        mapping_dict[win64_host]["uid"] = "16141134514358595374"
                        print(f"Assigned static Host UID to '{win64_host}'.")
                            
                    for p in player_list:
                        if p == win64_host:
                            continue
                        resolved = False
                        while not resolved:
                            try:
                                print(f"\nAction for player '{p}':")
                                ans = input("Enter exact LCE UID (hex/decimal), 'h' to generate a random hash, 'i' to ignore/delete: ").strip().lower()
                                if ans == 'i':
                                    mapping_dict[p]["action"] = "ignore"
                                    resolved = True
                                elif ans == 'h':
                                    mapping_dict[p]["action"] = "hash"
                                    resolved = True
                                elif ans != '':
                                    mapping_dict[p]["action"] = "uid"
                                    mapping_dict[p]["uid"] = ans
                                    resolved = True
                            except EOFError:
                                print("\nInterrupted.")
                                sys.exit(1)
                                
                    progress_mgr.set_player_mapping("mapping", mapping_dict)
            
            mapping_dict = progress_mgr.get_player_mapping("mapping")
            if mapping_dict:
                print(f"\n--- Step 2: Processing Player Data ---")
                level_dat = os.path.join(temp_dir, "level.dat")
                players_dir = os.path.join(temp_dir, "players")
                extract_all_players(level_dat, players_dir, mapping_dict)
            else:
                print(f"\n--- Step 2: Processing Player Data (Skipped) ---")
                
            progress_mgr.mark_step_completed("extract_player")
        else:
            print(f"\n--- Step 2: Processing Player Data (Skipped - Already completed) ---")
            
        # Step 3: Convert Chunks (Java Anvil to LCE payload)
        if not progress_mgr.is_step_completed("chunks"):
            print(f"\n--- Step 3: Converting Chunks ---")
            convert_all_regions_reverse(input_dir, temp_dir, progress_mgr)
            progress_mgr.mark_step_completed("chunks")
        else:
            print(f"\n--- Step 3: Converting Chunks (Skipped - Already completed) ---")
            
        # Step 4: Pack MS file
        if not progress_mgr.is_step_completed("pack"):
            print(f"\n--- Step 4: Packing {output_ms} ---")
            pack_ms(temp_dir, output_ms, progress_mgr)
        else:
            print(f"\n--- Step 4: Packing {output_ms} (Skipped - Already completed) ---")
            
        print("\n=== Conversion Completed Successfully! ===")
        print(f"Your LCE world is located at: {output_ms}")
        
    except ValueError as e:
        print(f"\nError during conversion: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError during conversion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        if os.path.exists(temp_dir):
            print(f"\nCleaning up temporary files...")
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()
