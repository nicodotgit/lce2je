#!/usr/bin/env bash

# LCE to Java World Converter - Bash Wrapper

# Navigate to the directory where the script is located
cd "$(dirname "$0")" || exit

VENV_DIR=".venv"
VENV_HASH_FILE="$VENV_DIR/.venv_hash"

# Check for python
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: 'python3' or 'python' is not installed or not in PATH."
    exit 1
fi

# Calculate hash of requirements
REQ_HASH=$(md5sum requirements.txt | cut -d' ' -f1)

build_venv() {
    echo "=> Creating Python virtual environment in $VENV_DIR..."
    rm -rf "$VENV_DIR"
    
    # Trap interruption globally during the build
    trap 'echo -e "\n=> Interrupted during installation. Cleaning up corrupted environment..."; kill -9 $CURRENT_PID 2>/dev/null; rm -rf "$VENV_DIR"; exit 1' INT TERM

    $PYTHON_CMD -m venv "$VENV_DIR" &
    CURRENT_PID=$!
    wait $CURRENT_PID
    
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment. Do you have 'python3-venv' installed?"
        rm -rf "$VENV_DIR"
        trap - INT TERM
        exit 1
    fi
    
    echo "=> Activating virtual environment and installing dependencies..."
    source "$VENV_DIR/bin/activate"
    
    pip install --upgrade pip &
    CURRENT_PID=$!
    wait $CURRENT_PID
    
    pip install -r requirements.txt &
    CURRENT_PID=$!
    wait $CURRENT_PID
    
    # Remove trap after successful install
    trap - INT TERM
    
    # Save the hash
    echo "$REQ_HASH" > "$VENV_HASH_FILE"
}

# Check if the virtual environment needs to be built
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_HASH_FILE" ]; then
    build_venv
else
    # Check if requirements changed
    STORED_HASH=$(cat "$VENV_HASH_FILE")
    if [ "$REQ_HASH" != "$STORED_HASH" ]; then
        echo "=> Dependencies updated. Rebuilding environment..."
        build_venv
    else
        source "$VENV_DIR/bin/activate"
    fi
fi

echo "=> Launching converter..."
echo ""

# Execute the main Python script
python je2lce_main.py "$@"

# Deactivate the virtual environment to leave the shell session clean
deactivate
