# lce2je - Technical Changelog & Discoveries

This document outlines the security, robustness, and state-management features implemented to ensure foolproof world conversions across Linux and Windows environments.

# 22-06-2026

## Core Discoveries

1. **GitHub Actions Runner Permissions and Environment Injectors**: By default, automated GitHub Release deployments utilize restricted, read-only `GITHUB_TOKEN`. To push dynamically compiled `.exe` and `.AppImage` artifacts directly to a repository's Release tab, the workflow's permissions mapping must explicitly declare `contents: write`.
2. **Cross-Platform PyQt6 Path Resolution Constraints**: Hardcoding directory delimiters (`/` or `\`) strictly triggers unhandled path traversal failures when resolving bundled binaries or extraction routines outside their native architectures. Wrapping all nested payload architectures in native `os.path.join` algorithms guarantees absolute parity across MacOS, Linux POSIX, and Windows NTFS virtual path arrays.

## Technical Implementations

### 1. Dedicated GUI Architecture Refactoring
Added the frontend GUI and background `gui_worker.py` threads. 

### 2. CI/CD Deployment Orchestration
The pipeline differentiates between `debug` (artifact-only) and `release` channels. Upon execution, the workflow bootstraps PyInstaller via `pip`, synchronizes dependencies, compiles compressed `.exe` and `.AppImage` standalone binaries using host-agnostic `--onefile` and `--onedir`, and automatically bundles Git-native commit histories into formally tagged GitHub Release pages.

### 4. Branding Standardization
Formalized structural identification metadata for PyInstaller payload compilation. Configured Window-native file description mapping within `version_info.txt`, linked to the interactive About Dialog.

# 16-06-2026

## Core Discoveries

1. **Modern DataFixer UUID Crashes**: In certain cases, Legacy Console Edition stores entity and player UUIDs utilizing custom string prefixes (e.g., `ent81b8883cdb2a41799adead7d9cf3589f`). When a standard Java 1.6.4 `level.dat` or region chunk containing these custom formats is loaded into modern Minecraft (1.18+), the internal `EntityStringUuidFix` DataFixer crashes trying to upgrade the string. Natively recalculating and injecting mathematically correct `UUIDMost` and `UUIDLeast` 64-bit Long equivalents entirely bypasses the crash and securely restores legacy ownership attributes (like pet taming).
2. **Java Edition Strict GZip Architectures**: Java 1.6.4 structurally enforces strict GZip encapsulation for `level.dat` and `players/*.dat` NBT files. However, modern Java builds fallback when encountering raw Uncompressed NBT. Explicitly trapping Python's `gzip.BadGzipFile` exceptions ensures cross-compatibility regardless of the underlying extraction method.
3. **LCE Fixed World Constraints**: Unlike Java's infinite generation algorithm, Legacy Console architectures constrain world geometries into preset boundaries (Classic, Small, Medium, Large) using injected NBT parameter thresholds like `XZSize` and `HellScale`. Discrepancies between generating dimensional boundaries mathematically require rigorous clipping of out-of-bounds region chunk coordinates, and enforcing teleportation protocols for stranded player entities to prevent native console execution panics.

## Technical Implementations

### 1. Intelligent Java-to-LCE World Pruning
Integrated an interactive coordinate boundary algorithm into the `je2lce` pipeline allowing users to select standard LCE geometries (Classic 864x864, Small 1024x1024, Medium 3072x3072, Large 5120x5120). The chunk parser dynamically calculates dimensional radiuses (incorporating strict 1:3 nether-overworld ratios for Classic/Small formats) and prunes any extraneous chunks to respect console memory limitations.

### 2. Player Boundary Enforcement
To accompany world pruning, the player extraction matrix automatically loops through multiplayer profiles and the central host to verify boundary legality. If a player is positioned in the void beyond the selected geometry, their NBT position is securely teleported back to the spawn coordinates to prevent permanent infinite-fall loops upon LCE load.

### 3. Deep NBT UUID Sanitization 
Rewrote the `decode_lce_chunk_payload` mapping loop to utilize a recursive compound scanner. The script scrubs every nested node within the decompressed `Entities` and `TileEntities` lists, purging proprietary LCE string IDs and recomputing them into valid `UUIDMost`/`UUIDLeast` integer values, future-proofing all exported chunks for 26.1+ modernization.

### 4. Player Mapping Refinements
The `lce2je` pipeline has been polished to allow explicitly keeping or discarding guest profiles, deleting discarded players from the extracted directory before generating the finalized save to securely prevent tracking bloat.

### 5. Non-Standard Nether Warnings
The `lce2je` extraction sequence now probes the `HellScale` parameter and alerts the user if the LCE world possessed a non 1:8 nether ratio format, warning them that their pre-existing portals will inherently de-sync due to Java's immutable spatial dimensions.

# 15-06-2026

## Core Discoveries

1. **LCE Metadata Bounding Boxes**: Java Edition generates truly infinite worlds, omitting engine-specific bounding box schemas from `level.dat`. Attempting to load a native Java world into LCE without these 15 proprietary tags (e.g., `XZSize`, `ClassicMoat`, `StrongholdX`) causes the engine to throw a fatal exception during the file-loading thread. Programmatically injecting these tags into the NBT tree dynamically resolves the issue.
2. **FAT Header & Padding Architectures**: Native LCE engines require an 8-byte global payload header `[Num_FAT_Records] + [09 00 09 00]` prefixed immediately after the 4-byte FAT pointer. Furthermore, LCE files append a 32-bit Little-Endian UNIX timestamp to the end of every 144-byte FAT record, and rigidly iterate exactly up to the uncompressed data offset without relying on a null-terminating 144-byte record.
3. **Region Payload Compression & Memory Exhaustion**: Using a standard 256-block height multiplier against LCE's 128-block `SparseNibbleStorage` array structure bloats the decompressed chunk weight heavily. Restoring the bitwise `(xz << 7) | y` index and dynamically engaging LCE's header-flag trimming for homogenous empty-air chunks is absolutely mandatory; otherwise, the uncompressed chunks instantly exhaust the rigid 512MB RAM heap allocated by the console engine.
4. **Xbox Live Network UID Randomization**: The 64-bit numerical IDs utilized by the LCE engine (e.g., `17964124366068773039`) are completely mathematically disconnected from the player's username. They are 100% randomly generated upon a profile's very first launch and permanently cached in a local `uid.dat` file.
5. **Win64 Hardcoded Host Dev UID**: Because the leaked Windows LCE port uses a cracked offline Xbox Live spoofing wrapper, local hosting often forces the session to fall back to a hardcoded 4J Studios Developer XUID (`16141134514358595374` / `0xE000D45248242F2E`).

## Technical Implementations

### 1. Fully Bidirectional Conversion (`je2lce`)
Implemented a completely reversed pipeline that accurately converts standard Java 1.6.4 infinite worlds back into perfectly tailored, memory-efficient LCE `saveData.ms` archives capable of running seamlessly on the Windows Win64 port.

### 2. Interactive Player UI 
Ripped out the outdated hardcoded `-p` command-line argument format. The script now parses the `UUID` NBT tags inside the numerical LCE player `.dat` files at runtime and renders an interactive terminal UI. Users are now dynamically prompted to assign the local Host player (automatically binding the static Win64 Dev UID when converting back to LCE) and manually resolve network UID mapping for LAN profiles, bridging the gap between Java's `level.dat` format and LCE's `players/` directory architecture.

### 3. Native GZip/Un-GZip Abstraction
Java Edition `level.dat` and `players/*.dat` metadata strictly require GZip compression to be correctly listed and executed, while LCE's `saveData.ms` expects raw binary payloads natively since the entire MS archive is already Zlib-compressed. The layout translation layer (`lce_to_java.py` and `java_to_lce.py`) now dynamically handles GZip compression and decompression transparently during the `os.walk()` layout phase.

### 4. Wrapper Script Evolution
Forked the master wrapper scripts to establish dedicated entrypoints (`lce2je` and `je2lce`). Maintained complete integration with the atomic `progress.py` state manager, verifying that the smart `[Ctrl+C]` signal handler interacts gracefully and safely with Python's native blocking `input()` I/O loops across both pipelines.

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
Engineered a centralized `lce2je_progress.json` state tracker. 
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
