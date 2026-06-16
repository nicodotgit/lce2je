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

from scripts.extract_ms import extract_ms
from scripts.lce_to_java import convert_layout
from scripts.convert_chunks import convert_all_regions
from scripts.inject_player import inject_player_data
from scripts.progress import ProgressManager, setup_signal_handler

def main():
    parser = argparse.ArgumentParser(description="Convert Minecraft Legacy Console Edition (LCE) worlds to Java 1.6.4")
    parser.add_argument("input_ms", help="Path to the LCE saveData.ms file")
    parser.add_argument("output_dir", help="Path to the output Java 1.6.4 world directory")
    
    args = parser.parse_args()
    
    input_ms = os.path.abspath(args.input_ms)
    output_dir = os.path.abspath(args.output_dir)
    
    if not os.path.exists(input_ms):
        print(f"Error: Input file {input_ms} does not exist.")
        sys.exit(1)
        
    done_file = os.path.join(output_dir, ".lce2java_done")
    if os.path.exists(done_file):
        print(f"Error: The output directory '{output_dir}' already contains a completely converted world.")
        sys.exit(1)
        
    temp_dir = os.path.abspath("_temp_lce_extract")
    
    try:
        progress_mgr = ProgressManager(output_dir)
        progress_mgr.set_input_file(input_ms)
        progress_mgr.cleanup_temp_files(temp_dir)
        
        setup_signal_handler(progress_mgr, temp_dir, output_dir)
        
        # Step 1: Extract MS file
        if not progress_mgr.is_step_completed("extract"):
            print(f"--- Step 1: Extracting {input_ms} ---")
            extract_ms(input_ms, temp_dir, progress_mgr)
            progress_mgr.mark_step_completed("extract")
        else:
            print(f"--- Step 1: Extracting {input_ms} (Skipped - Already completed) ---")
            
        # Warning for non 1:8 Nether
        level_dat_temp = os.path.join(temp_dir, "level.dat")
        if os.path.exists(level_dat_temp):
            try:
                import io
                from nbt import nbt
                with open(level_dat_temp, "rb") as f:
                    l_nbt = nbt.NBTFile(buffer=io.BytesIO(f.read()))
                if "Data" in l_nbt and "HellScale" in l_nbt["Data"]:
                    hell_scale = l_nbt["Data"]["HellScale"].value
                    if hell_scale != 8:
                        has_nether = False
                        for fn in os.listdir(temp_dir):
                            if fn.startswith("DIM-1r.") and fn.endswith(".mcr"):
                                has_nether = True
                                break
                        if has_nether:
                            print(f"\nWARNING: This LCE world has a generated Nether with a 1:{hell_scale} ratio.")
                            print("Java Edition uses a strict 1:8 Nether ratio. Your existing Nether portals will not link correctly in Java.")
                            print("You may need to manually destroy and rebuild portals in Java to fix the linking.")
            except Exception:
                pass
            
        # Step 2: Convert Directory Layout & GZip Data
        if not progress_mgr.is_step_completed("layout"):
            print(f"\n--- Step 2: Converting Layout ---")
            convert_layout(temp_dir, output_dir, progress_mgr)
            progress_mgr.mark_step_completed("layout")
        else:
            print(f"\n--- Step 2: Converting Layout (Skipped - Already completed) ---")
            
        # Step 3: Convert Chunks (LCE payload to Java Anvil)
        if not progress_mgr.is_step_completed("chunks"):
            print(f"\n--- Step 3: Converting Chunks ---")
            convert_all_regions(temp_dir, output_dir, progress_mgr)
            progress_mgr.mark_step_completed("chunks")
        else:
            print(f"\n--- Step 3: Converting Chunks (Skipped - Already completed) ---")
            
        # Step 4: Inject Player Data (Optional)
        if not progress_mgr.is_step_completed("inject_player"):
            level_dat = os.path.join(output_dir, "level.dat")
            players_dir = os.path.join(output_dir, "players")
            
            target_username = progress_mgr.get_player_mapping("host_player")
            kept_players = progress_mgr.get_player_mapping("kept_players")
            if kept_players is None or target_username is None:
                print("\n--- Interactive Player Mapping ---")
                players = []
                if os.path.exists(players_dir):
                    for filename in os.listdir(players_dir):
                        if not filename.endswith(".dat"): continue
                        try:
                            player_nbt = nbt.NBTFile(os.path.join(players_dir, filename))
                            uuid_tag = player_nbt.get("UUID")
                            if uuid_tag and isinstance(uuid_tag, nbt.TAG_String):
                                players.append(uuid_tag.value)
                        except Exception as e:
                            print(f"Failed to read {filename}: {e}")
                
                if not players:
                    print("No players found. Skipping player injection.")
                    kept_players = []
                    target_username = ""
                    progress_mgr.set_player_mapping("kept_players", kept_players)
                    progress_mgr.set_player_mapping("host_player", target_username)
                else:
                    kept_players = []
                    print("\nPlayer Selection:")
                    for name in players:
                        ans = ""
                        while ans not in ["K", "D"]:
                            try:
                                ans = input(f"Keep player '{name}'? (K=Keep / D=Discard): ").strip().upper()
                            except EOFError:
                                print("\nInterrupted.")
                                sys.exit(1)
                        if ans == "K":
                            kept_players.append(name)
                            
                    progress_mgr.set_player_mapping("kept_players", kept_players)
                    
                    if not kept_players:
                        print("All players discarded. Skipping host injection.")
                        target_username = ""
                    else:
                        while target_username is None:
                            print("\nKept Players:")
                            for i, name in enumerate(kept_players):
                                print(f"[{i+1}] {name}")
                            print("[0] Skip (Do not inject any host)")
                            try:
                                ans = input("\nEnter the number of the player to inject into level.dat as the world Host: ").strip()
                            except EOFError:
                                print("\nInterrupted.")
                                sys.exit(1)
                                
                            try:
                                idx = int(ans)
                                if idx == 0:
                                    target_username = ""
                                elif 1 <= idx <= len(kept_players):
                                    target_username = kept_players[idx-1]
                                else:
                                    print("Invalid selection.")
                            except ValueError:
                                print("Please enter a valid number.")
                    progress_mgr.set_player_mapping("host_player", target_username)

            if target_username:
                print(f"\n--- Step 4: Injecting Player Data for '{target_username}' ---")
            else:
                print(f"\n--- Step 4: Processing Player Data (No Host Injected) ---")
                
            inject_player_data(level_dat, players_dir, target_username, kept_players)
            progress_mgr.mark_step_completed("inject_player")
        else:
            print(f"\n--- Step 4: Injecting Player Data (Skipped - Already completed) ---")
            
        # Completion
        with open(done_file, "w") as f:
            f.write("done")
        progress_mgr.mark_file_created(done_file)
            
        print("\n=== Conversion Completed Successfully! ===")
        print(f"Your Java 1.6.4 world is located at: {output_dir}")
        
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
