import os
import shutil
import traceback
import traceback
import sys
import time
import re
import threading
from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop

try:
    from nbt import nbt
except ImportError:
    pass

from scripts.extract_ms import extract_ms
from scripts.lce_to_java import convert_layout
from scripts.convert_chunks import convert_all_regions
from scripts.inject_player import inject_player_data
from scripts.progress import ProgressManager

class PrintRedirector:
    def __init__(self, signal, original_stream, is_stderr=False, progress_signal=None):
        self.signal = signal
        self.original_stream = original_stream
        self.is_stderr = is_stderr
        self.progress_signal = progress_signal
        self.last_error = ""
        self.last_emit_time = 0
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        self.completed_chunks = 0
        self.total_chunks = 0

    def write(self, text):
        if self.original_stream:
            self.original_stream.write(text)
            self.original_stream.flush()
            
        clean_text = self.ansi_escape.sub('', text).strip()
        if clean_text:
            if self.is_stderr:
                self.last_error = clean_text
            else:
                # Reset counter if a new chunk step starts
                if "Converting Chunks" in clean_text:
                    self.completed_chunks = 0
                
                # Check for completed chunks (only matches 100%)
                if "100% [" in clean_text:
                    match = re.search(r'\(\s*\d+/\s*(\d+)\)', clean_text)
                    if match and self.progress_signal:
                        self.total_chunks = int(match.group(1))
                        self.completed_chunks += 1
                        self.progress_signal.emit(self.completed_chunks, self.total_chunks)
                        return

                if clean_text.startswith("--- Step") or clean_text.startswith("WARNING") or clean_text.startswith("Error"):
                    self.signal.emit(clean_text)

    def flush(self):
        pass

class ConversionWorker(QThread):
    log_msg = pyqtSignal(str)
    error_msg = pyqtSignal(str)
    finished_success = pyqtSignal(str)
    chunk_progress = pyqtSignal(int, int)

    ask_lce_player_mapping = pyqtSignal(list)

    def __init__(self, mode, input_path, output_path):
        super().__init__()
        self.mode = mode
        self.input_path = input_path
        self.output_path = output_path
        
        self.sync_event = threading.Event()
        
    # Dialog responses
    lce_players_kept = []
    lce_host_player = ""
    uid_mapping_result = {}
    player_mapping_result = {}

    def run(self):
        self.redirector = PrintRedirector(self.log_msg, sys.stdout, progress_signal=self.chunk_progress)
        sys.stdout = self.redirector
        
        self.err_redirector = PrintRedirector(self.log_msg, sys.stderr, is_stderr=True)
        sys.stderr = self.err_redirector
        
        try:
            self.run_lce2je()
        except SystemExit as e:
            # Script called sys.exit(), which raises SystemExit
            err_msg = self.err_redirector.last_error if self.err_redirector.last_error else "Conversion halted due to a critical error."
            self.error_msg.emit(f"Conversion Failed:\n{err_msg}")
        except Exception as e:
            if self.err_redirector and self.err_redirector.original_stream:
                self.err_redirector.original_stream.write(f"Error during conversion: {str(e)}\n{traceback.format_exc()}\n")
                self.err_redirector.original_stream.flush()
            self.error_msg.emit(f"{str(e)}")
        finally:
            sys.stdout = self.redirector.original_stream
            sys.stderr = self.err_redirector.original_stream

    # --- LCE to Java ---
    def on_lce_player_mapping_resolved(self, kept, host):
        self.lce2je_kept = kept
        self.lce2je_host = host
        self.sync_event.set()

    def run_lce2je(self):
        input_ms = self.input_path
        output_dir = self.output_path
        
        done_file = os.path.join(output_dir, ".lce2je_done")
        if os.path.exists(done_file):
            raise ValueError(f"The output directory '{output_dir}' already contains a completely converted world.")
            
        temp_dir = os.path.abspath("_temp_lce_extract")
        progress_mgr = ProgressManager(output_dir)
        self.progress_mgr = progress_mgr
        self.temp_dir = temp_dir
        progress_mgr.set_input_file(input_ms)
        progress_mgr.cleanup_temp_files(temp_dir)
        
        try:
            if not progress_mgr.is_step_completed("extract"):
                print(f"--- Step 1: Extracting {input_ms} ---")
                extract_ms(input_ms, temp_dir, progress_mgr)
                progress_mgr.mark_step_completed("extract")
            else:
                print(f"--- Step 1: Extracting (Skipped - Already completed) ---")
                
            level_dat_temp = os.path.join(temp_dir, "level.dat")
            if os.path.exists(level_dat_temp):
                try:
                    import io
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
                                print("Java Edition uses a strict 1:8 Nether ratio.")
                except Exception:
                    pass
                
            if not progress_mgr.is_step_completed("layout"):
                print(f"\n--- Step 2: Converting Layout ---")
                convert_layout(temp_dir, output_dir, progress_mgr)
                progress_mgr.mark_step_completed("layout")
            else:
                print(f"\n--- Step 2: Converting Layout (Skipped) ---")
                
            if not progress_mgr.is_step_completed("chunks"):
                print(f"\n--- Step 3: Converting Chunks ---")
                convert_all_regions(temp_dir, output_dir, progress_mgr)
                progress_mgr.mark_step_completed("chunks")
            else:
                print(f"\n--- Step 3: Converting Chunks (Skipped) ---")
                
            if not progress_mgr.is_step_completed("inject_player"):
                print(f"\n--- Step 4: Injecting Player Data ---")
                level_dat = os.path.join(output_dir, "level.dat")
                players_dir = os.path.join(output_dir, "players")
                
                target_username = progress_mgr.get_player_mapping("host_player")
                kept_players = progress_mgr.get_player_mapping("kept_players")
                
                if kept_players is None or target_username is None:
                    players = []
                    if os.path.exists(players_dir):
                        for filename in os.listdir(players_dir):
                            if not filename.endswith(".dat"): continue
                            try:
                                p_path = os.path.join(players_dir, filename)
                                try:
                                    player_nbt = nbt.NBTFile(p_path)
                                except Exception:
                                    import io
                                    with open(p_path, 'rb') as f:
                                        player_nbt = nbt.NBTFile(buffer=io.BytesIO(f.read()))
                                        
                                uuid_tag = player_nbt.get("UUID")
                                if uuid_tag and isinstance(uuid_tag, nbt.TAG_String):
                                    players.append(uuid_tag.value)
                            except Exception:
                                pass
                                
                    if not players:
                        kept_players = []
                        target_username = ""
                        progress_mgr.set_player_mapping("kept_players", kept_players)
                        progress_mgr.set_player_mapping("host_player", target_username)
                    else:
                        # Emitting signal to GUI and waiting
                        self.sync_event.clear()
                        self.ask_lce_player_mapping.emit(players)
                        self.sync_event.wait()
                        
                        kept_players = self.lce2je_kept
                        target_username = self.lce2je_host
                        
                        progress_mgr.set_player_mapping("kept_players", kept_players)
                        progress_mgr.set_player_mapping("host_player", target_username)
                        
                inject_player_data(level_dat, players_dir, target_username, kept_players)
                progress_mgr.mark_step_completed("inject_player")
            else:
                print(f"\n--- Step 4: Injecting Player Data (Skipped) ---")
                
            with open(done_file, "w") as f:
                f.write("done")
            progress_mgr.mark_file_created(done_file)
            
            print("\n=== Conversion Completed Successfully! ===")
            self.finished_success.emit(output_dir)
            
        finally:
            if os.path.exists(temp_dir):
                print(f"\nCleaning up temporary files...")
                shutil.rmtree(temp_dir)


    # --- Java to LCE ---
    def on_world_size_resolved(self, size):
        self.j2l_size = size
        self.sync_event.set()
        
    def on_level_dat_player_resolved(self, name):
        self.j2l_level_dat_player = name
        self.sync_event.set()
        
    def on_oob_resolved(self, action):
        self.j2l_oob_action = action
        self.sync_event.set()
        
    def on_win64_host_resolved(self, host):
        self.j2l_win64_host = host
        self.sync_event.set()
        
    def on_uid_mapping_resolved(self, mapping):
        self.j2l_uid_mapping = mapping
        self.sync_event.set()
