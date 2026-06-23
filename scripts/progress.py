import json
import os
import glob

class ProgressManager:
    def __init__(self, output_dir):
        self.filepath = os.path.join(output_dir, "lce2je_progress.json")
        self.output_dir = output_dir
        self.state = {"input_file": None, "completed_steps": [], "created_files": [], "player_mapping": {}}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as f:
                self.state = json.load(f)

    def save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(self.state, f, indent=4)

    def cleanup_temp_files(self, temp_dir):
        # Nuke incomplete .tmp files
        for d in [temp_dir, self.output_dir]:
            if not os.path.exists(d): continue
            for root, _, files in os.walk(d):
                for f in files:
                    if f.endswith(".tmp"):
                        try:
                            os.remove(os.path.join(root, f))
                        except:
                            pass

    def is_file_created(self, path):
        return os.path.abspath(path) in self.state["created_files"]

    def mark_file_created(self, path):
        abs_path = os.path.abspath(path)
        if abs_path not in self.state["created_files"]:
            self.state["created_files"].append(abs_path)
            self.save()

    def is_step_completed(self, step):
        return step in self.state["completed_steps"]

    def mark_step_completed(self, step):
        if step not in self.state["completed_steps"]:
            self.state["completed_steps"].append(step)
            self.save()

    def set_input_file(self, input_file):
        abs_in = os.path.abspath(input_file)
        if self.state.get("input_file") is None:
            self.state["input_file"] = abs_in
            self.save()
        elif self.state["input_file"] != abs_in:
            raise ValueError("Cannot resume: Output directory contains partial data from a different world!")

    def get_player_mapping(self, key):
        return self.state.get("player_mapping", {}).get(key)

    def set_player_mapping(self, key, mapping_data):
        if "player_mapping" not in self.state:
            self.state["player_mapping"] = {}
        self.state["player_mapping"][key] = mapping_data
        self.save()

    def has_player_mapping(self):
        return bool(self.state.get("player_mapping", {}))

    def nuke_progress(self, temp_dir):
        # 0. Sweep the output dir and temp dir for .tmp files
        self.cleanup_temp_files(temp_dir)
        
        # 1. Delete all tracked created files to prevent touching user files
        for f in self.state.get("created_files", []):
            if os.path.exists(f):
                try: os.remove(f)
                except: pass
        
        # 2. Delete the progress log
        if os.path.exists(self.filepath):
            try: os.remove(self.filepath)
            except: pass
            
        # 3. Clean up the temp dir since we own it completely
        if os.path.exists(temp_dir):
            import shutil
            try: shutil.rmtree(temp_dir)
            except: pass
            
        # 4. Attempt to safely remove any empty directories inside the output dir
        for root, dirs, files in os.walk(self.output_dir, topdown=False):
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
                    
        # 5. Try to remove the output dir itself if it's completely empty
        try:
            os.rmdir(self.output_dir)
        except OSError:
            pass

import signal
import multiprocessing
import shutil

g_progress_mgr = None
g_temp_dir = None
g_output_dir = None
g_on_resume = None

def sigint_handler(sig, frame):
    # Only the main process should prompt the user
    if multiprocessing.current_process().name != 'MainProcess':
        return
        
    ans = ""
    while ans not in ['s', 'n', 'c']:
        try:
            ans = input("\n[Ctrl+C Detected] Do you want to: (s)ave progress and exit, (n)uke all progress and exit, or (c)ancel and resume? ").strip().lower()
        except EOFError:
            break
            
    if ans == 's':
        print("\nSaving progress and exiting immediately...")
        if g_progress_mgr and g_temp_dir:
            g_progress_mgr.cleanup_temp_files(g_temp_dir)
        os.kill(0, signal.SIGKILL)
    elif ans == 'n':
        print("\nNuking progress... Safely deleting only the generated data.")
        if g_progress_mgr and g_temp_dir:
            g_progress_mgr.nuke_progress(g_temp_dir)
        elif g_temp_dir and os.path.exists(g_temp_dir):
            shutil.rmtree(g_temp_dir)
        os.kill(0, signal.SIGKILL)
    else:
        print("\nResuming...")
        if g_on_resume:
            g_on_resume()

def setup_signal_handler(progress_mgr, temp_dir, output_dir):
    global g_progress_mgr, g_temp_dir, g_output_dir
    g_progress_mgr = progress_mgr
    g_temp_dir = temp_dir
    g_output_dir = output_dir
    signal.signal(signal.SIGINT, sigint_handler)
