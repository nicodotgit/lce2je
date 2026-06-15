# lce2java - Technical Changelog & Discoveries

This document outlines the security, robustness, and state-management features implemented to ensure foolproof world conversions across Linux and Windows environments.


# 15-06-2026

## Core Discoveries

1. **LCE Metadata Bounding Boxes**: Java Edition generates truly infinite worlds, omitting engine-specific bounding box schemas from `level.dat`. Attempting to load a native Java world into LCE without these 15 proprietary tags (e.g., `XZSize`, `ClassicMoat`, `StrongholdX`) causes the engine to throw a fatal exception during the file-loading thread. Programmatically injecting these tags into the NBT tree dynamically resolves the issue.
2. **FAT Header & Padding Architectures**: Native LCE engines require an 8-byte global payload header `[Num_FAT_Records] + [09 00 09 00]` prefixed immediately after the 4-byte FAT pointer. Furthermore, LCE files append a 32-bit Little-Endian UNIX timestamp to the end of every 144-byte FAT record, and rigidly iterate exactly up to the uncompressed data offset without relying on a null-terminating 144-byte record.
3. **Region Payload Compression & Memory Exhaustion**: Using a standard 256-block height multiplier against LCE's 128-block `SparseNibbleStorage` array structure bloats the decompressed chunk weight heavily. Restoring the bitwise `(xz << 7) | y` index and dynamically engaging LCE's header-flag trimming for homogenous empty-air chunks is absolutely mandatory; otherwise, the uncompressed chunks instantly exhaust the rigid 512MB RAM heap allocated by the console engine.
4. **Xbox Live Network UID Randomization**: The 64-bit numerical IDs utilized by the LCE engine (e.g., `17964124366068773039`) are completely mathematically disconnected from the player's username. They are 100% randomly generated upon a profile's very first launch and permanently cached in a local `uid.dat` file.
5. **Win64 Hardcoded Host Dev UID**: Because the leaked Windows LCE port uses a cracked offline Xbox Live spoofing wrapper, local hosting often forces the session to fall back to a hardcoded 4J Studios Developer XUID (`16141134514358595374` / `0xE000D45248242F2E`).

## Technical Implementations

### 1. Fully Bidirectional Conversion (`java2lce`)
Implemented a completely reversed pipeline that accurately converts standard Java 1.6.4 infinite worlds back into perfectly tailored, memory-efficient LCE `saveData.ms` archives capable of running seamlessly on the Windows Win64 port.

### 2. Interactive Player UI 
Ripped out the outdated hardcoded `-p` command-line argument format. The script now parses the `UUID` NBT tags inside the numerical LCE player `.dat` files at runtime and renders an interactive terminal UI. Users are now dynamically prompted to assign the local Host player (automatically binding the static Win64 Dev UID when converting back to LCE) and manually resolve network UID mapping for LAN profiles, bridging the gap between Java's `level.dat` format and LCE's `players/` directory architecture.

### 3. Native GZip/Un-GZip Abstraction
Java Edition `level.dat` and `players/*.dat` metadata strictly require GZip compression to be correctly listed and executed, while LCE's `saveData.ms` expects raw binary payloads natively since the entire MS archive is already Zlib-compressed. The layout translation layer (`lce_to_java.py` and `java_to_lce.py`) now dynamically handles GZip compression and decompression transparently during the `os.walk()` layout phase.

### 4. Wrapper Script Evolution
Forked the master wrapper scripts to establish dedicated entrypoints (`lce2java` and `java2lce`). Maintained complete integration with the atomic `progress.py` state manager, verifying that the smart `[Ctrl+C]` signal handler interacts gracefully and safely with Python's native blocking `input()` I/O loops across both pipelines.

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
