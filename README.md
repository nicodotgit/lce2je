# LCE to Java World Converter

This repository contains scripts to convert Minecraft Legacy Console Edition (LCE) `.ms` world saves (such as those found in development leaks) to standard Minecraft Java Edition 1.6.4 saves, and vice-versa.

## LCE `.ms` File Format Technical Breakdown

The `saveData.ms` file is a custom archive format designed for the Console Edition. Here is how it is structured:

### 1. Archive Wrapper
The outer wrapper of the `.ms` file is Zlib-compressed, but typically includes an 8-byte uncompressed header:
- **Bytes 0-3**: Padding/Reserved (`0x00000000`)
- **Bytes 4-7**: Decompressed size in bytes (Little-Endian Uint32)
- **Bytes 8+**: Standard Zlib stream (starting with `0x78 0x9C` or similar) containing the filesystem.

### 2. Uncompressed Archive Payload
Once decompressed, the file is a flat binary blob containing internal files and a File Allocation Table (FAT) located near the end of the file.
- **Bytes 0-3**: File Allocation Table Offset (Little-Endian Uint32). This points to the absolute offset in the uncompressed data where the directory records start.
- **Bytes 4 to (FAT Offset - 1)**: Raw concatenated binary data for all the internal files (Level metadata, region files, player data, etc.).
- **Bytes (FAT Offset) to EOF**: The directory FAT.

### 3. File Allocation Table (FAT)
The FAT consists of continuous `144-byte` records. Each record describes one internal file:
- **Bytes 0-127**: A UTF-16LE null-terminated string representing the file path (e.g., `level.dat`, `DIM-1r.0.0.mcr`).
- **Bytes 128-131**: File size in bytes (Little-Endian Uint32).
- **Bytes 132-135**: File content offset in bytes from the start of the uncompressed archive (Little-Endian Uint32).
- **Bytes 136-143**: Additional metadata/padding (usually zeroes).

The list concludes when a record with a null or empty file name is reached, or the end of the file is hit.

### 4. Level and Player Data Configuration
Because `.ms` files are themselves wrapped in Zlib compression, LCE does not store `level.dat` and `players/*.dat` files using standard GZip compression. In order for standard Java Edition builds to recognize and list these worlds, they must be locally compressed using GZip upon extraction.

### 5. Region File Differences (.mcr)
LCE `.mcr` Region Files look deceptively similar to Java McRegion/Anvil files, but contain dramatic structural differences requiring bit-level rewriting to port:
- **Chunk Headers Endianness:** Java stores standard region chunk offsets with 3 bytes of offset followed by 1 byte of size in **Big-Endian**. LCE inverses and modifies this, using 1 byte for size followed by 3 bytes for offset in **Little-Endian**.
- **Payload Lengths:** Upon reaching the offset location, Java reads a 4-byte chunk size in Big-Endian. LCE reads a 4-byte chunk size in Little-Endian.
- **Chunk Payload Structure:** LCE chunks do not use native string-based NBT key mappings. The decompressed Zlib payload is further obfuscated by an RLE-encoding layer. Once fully decompressed, the chunk is an engineered C++ binary struct containing:
  1. A binary header with version (8 or 9), coordinates, and timestamps.
  2. `CompressedTileStorage`: Two 128-height block ID structures using complex bit-packed palettes mapped via 3D Z-order curves.
  3. `SparseNibbleStorage`: Four 128-height data arrays (Data, SkyLight, BlockLight) utilizing plane indices and 4-bit packed nibbles.
  4. Flat 256-byte arrays for HeightMaps and Biomes.
  5. A standard Java NBT tag appended at the very end to store dynamic `Entities` and `TileEntities`.
- **Metadata Extraction Mathematics:** To successfully parse LCE `SparseNibbleStorage` back into Java's 256-height flat format without corrupting block states (e.g. wool colors, stair facings), the data must be read using the 1D index `pos = (xz << 8) | y`. Failure to shift the coordinate plane by 8 bits results in massive array collisions, stripping the chunk of all metadata and defaulting blocks to ID `0` equivalents.

### 6. Player Data Quirks
Java 1.6.4 Singleplayer explicitly stores the host player's inventory and location inside `level.dat` under a native `Player` tag. Legacy Console Edition completely abandons this format, splitting *all* players (including the host) into the `players/` directory using numerical account IDs (e.g., `16141134514358595374.dat`).

However, while LCE uses numeric filenames, it hides the player's true username internally within the `.dat` file inside a standard `UUID` NBT String tag. To perfectly convert the world for Java Singleplayer and LAN Multiplayer, the converter reads these internal `UUID` tags, injects the host's `.dat` back into `level.dat`, and automatically renames the remaining numeric files to match their usernames.

## Usage / Scripts

The repository features a seamless automated workflow. To convert an LCE `.ms` save file to Java 1.6.4, simply run the master entry point:

```bash
python main.py <path_to_saveData.ms> <output_directory> -p [optional_username]
```
*Example: `python main.py saveData.ms ./ConvertedWorld -p TurboLightning`*

**Internal Scripts:**
1. `scripts/1_extract_ms.py` - Unpacks the `.ms` file into raw LCE files via Zlib/FAT decoding.
2. `scripts/2_lce_to_java.py` - Translates LCE `.ms` extraction output paths to native Java Edition folder trees, and GZips `.dat` metadata files.
3. `scripts/3_convert_chunks.py` - Deeply parses LCE `.mcr` binary structs and translates them into standard Anvil NBT `.mca` files.
4. `scripts/4_inject_player.py` - Reads LCE numerical `.dat` files, maps `UUID` string tags to rename LAN player profiles, and injects host data into `level.dat`.
