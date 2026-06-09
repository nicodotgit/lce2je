import sys

if sys.version_info < (3, 8):
    print("Error: LCE2Java requires Python 3.8 or higher.", file=sys.stderr)
    sys.exit(1)

try:
    import nbt
except ImportError:
    print("Error: Required dependency 'nbt' is not installed.", file=sys.stderr)
    print("Please run the tool using the corresponding wrapper for your OS or install dependencies with 'pip install -r requirements.txt'.", file=sys.stderr)
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
    parser.add_argument("--player", "-p", help="Main username to inject into level.dat for Singleplayer host compatibility")
    
    args = parser.parse_args()
    
    input_ms = os.path.abspath(args.input_ms)
    output_dir = os.path.abspath(args.output_dir)
    main_username = args.player
    
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
        if main_username and not progress_mgr.is_step_completed("inject_player"):
            print(f"\n--- Step 4: Injecting Player Data for '{main_username}' ---")
            level_dat = os.path.join(output_dir, "level.dat")
            players_dir = os.path.join(output_dir, "players")
            inject_player_data(level_dat, players_dir, main_username)
            progress_mgr.mark_step_completed("inject_player")
        elif main_username:
            print(f"\n--- Step 4: Injecting Player Data for '{main_username}' (Skipped - Already completed) ---")
            
        # Completion
        with open(done_file, "w") as f:
            f.write("done")
            
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
