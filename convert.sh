#!/usr/bin/env bash

# LCE to Java World Converter - Bash Wrapper

# Navigate to the directory where the script is located
cd "$(dirname "$0")" || exit

VENV_DIR=".venv"

# Check if the virtual environment directory exists
if [ ! -d "$VENV_DIR" ]; then
    echo "=> Creating Python virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    
    echo "=> Activating virtual environment and installing dependencies..."
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip just in case, then install requirements
    pip install --upgrade pip
    pip install -r requirements.txt
else
    # Simply activate it if it already exists
    source "$VENV_DIR/bin/activate"
fi

echo "=> Launching converter..."
echo ""

# Execute the main Python script, passing along any CLI arguments
python main.py "$@"

# Deactivate the virtual environment to leave the shell session clean
deactivate
