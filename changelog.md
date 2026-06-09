# lce2java - Technical Changelog & Discoveries

This document outlines the security, robustness, and state-management features implemented to ensure foolproof world conversions across Linux and Windows environments.


# 09-06-2026

## Core Discoveries

1. **Multiprocessing Interrupt Deadlocks**: Python's `ProcessPoolExecutor` hangs indefinitely if an unhandled `KeyboardInterrupt` propagates from a worker or is thrown during a `queue.get()` blocking call. Explicitly throwing an `os.kill(0, signal.SIGKILL)` from the main process is the only guaranteed way to instantaneously destroy the process group when a user requests an emergency "nuke" or "save" without hanging the terminal.
2. **Venv Signal Vulnerabilities**: `python3 -m venv` natively dumps a verbose stack trace if interrupted with `Ctrl+C` while operating in the foreground. Throwing the execution into a bash background job (`&`) and actively `wait`ing for it isolated the python process from terminal `SIGINT` signals. This allowed the bash wrapper to intercept the interrupt and cleanly `kill -9` the background job without emitting confusing Python tracebacks.
3. **Windows Batch Atomic Fallbacks**: Windows `cmd.exe` handles `SIGINT` entirely differently, forcibly prompting `Terminate batch job (Y/N)`. Using an atomic trailing `.venv_hash` creation mechanism ensures that any interrupted dependency install correctly triggers a deletion of the broken virtual environment on the next run, flawlessly mimicking bash trap safety without requiring complex process management.
4. **The Danger of Orphaned Temp Files**: Generating `.tmp` files directly circumvents data corruption if power is lost or the script is killed mid-write. Both the temp extraction folder *and* the target output folder are sweeped upon "resume" and "nuke" calls to ensure these orphaned `.tmp` files were fully cleared before attempting to safely `os.rmdir` empty directories.

## Technical Implementations

### 1. Atomic File Generation
Transitioned all `.mcr` to `.mca` parsing, `level.dat` GZip conversions, and player NBT injections to an atomic `.tmp` buffer format. The scripts now write exclusively to `filename.tmp` and execute a native `os.rename()` only when the I/O flush is completely finished, ensuring zero corruption if execution abruptly halts.

### 2. Centralized Progress State (`progress.py`)
Engineered a centralized `lce2java_progress.json` state tracker. 
- **Integrity**: Validates the absolute path of `input_ms` to strictly prevent mixing two different world saves inside the same output directory.
- **Micro-Tracking**: Maintains an array of `created_files` tracking exactly what specific chunks and metadata have been successfully processed and atomically renamed.

### 3. Smart Resume Logic
`main.py` utilizes the `ProgressManager` to skip `extract`, `convert_layout`, and `inject_player` macro-steps if they are flagged complete. `convert_chunks.py` actively maps its target files against the `created_files` array to seamlessly bypass fully parsed regions.

### 4. Interactive Interrupt Handling (`Ctrl+C`)
Wrapped the master chunk conversion loop inside a global signal handler. When trapped, it pauses execution and spawns an interactive prompt:
- `(s)ave`: Instantly stops workers, triggers a `.tmp` sweep, and calls `SIGKILL` to exit safely, preserving the `progress.json`.
- `(n)uke`: Invokes `nuke_progress()`. Selectively iterates through the JSON's `created_files` to surgicaly delete *only* generated data, preventing catastrophic recursive `shutil.rmtree` destruction if the user outputted the world directly to a sensitive directory like their `Desktop`.
- `(c)ancel`: Silently resumes execution and triggers a UI redraw callback (`g_on_resume`).

### 5. Automated Environment Bootstrapping
- **Linux (`convert.sh`)**: Dynamically computes the `md5sum` of `requirements.txt`. Hashes are stored in `.venv/.venv_hash`. If dependencies change, the `venv` auto-rebuilds. Uses robust background job trapping to safely nuke `.venv` upon user interruption.
- **Windows (`convert.bat`)**: Replicates MD5 hashing using a native Python one-liner to maintain cross-platform compatibility. Relies on trailing hash creation to guarantee atomic environment generation without the need for bash traps.

### 6. Graceful Corruption Handling
`extract_ms.py` was fortified with comprehensive `try-except` blocks encapsulating the `zlib.decompress` and byte-unpacking logic. If an invalid LCE world is parsed, it prints a clean error message, actively removes the `progress.json` lockfile from the target directory so it doesn't indefinitely squat the output folder, and exits cleanly.
