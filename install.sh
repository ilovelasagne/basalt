#!/bin/bash

# ==============================================================================
# WARNING: This script modifies system files and requires superuser privileges.
# Please review the code before running it. Use at your own risk.
# ==============================================================================

# --- Configuration ---
# Get the current user and home directory to ensure paths are correct.
USER_NAME=$(whoami)
HOME_DIR=$(eval echo ~$USER_NAME)
SERVICE_NAME="testcode.service"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME"

# URLs for the Python scripts and the requirements file on GitHub
TESTCODE_URL="https://raw.githubusercontent.com/ilovelasagne/basalt/main/testcode.py"
TEST_URL="https://raw.githubusercontent.com/ilovelasagne/basalt/main/test.py"
REQUIREMENTS_URL="https://raw.githubusercontent.com/ilovelasagne/basalt/main/requirements.txt"

# Define the full paths for the downloaded files
SCRIPT_PATH="$HOME_DIR/$(basename $TESTCODE_URL)"
TEST_SCRIPT_PATH="$HOME_DIR/$(basename $TEST_URL)"
REQUIREMENTS_FILE_PATH="$HOME_DIR/$(basename $REQUIREMENTS_URL)"
LOG_FILE="$HOME_DIR/boot_log.txt"

# --- Step 1: Download Python scripts and requirements file from GitHub ---
echo "1. Downloading Python scripts and requirements.txt from GitHub..."
wget -O "$SCRIPT_PATH" "$TESTCODE_URL"
wget -O "$TEST_SCRIPT_PATH" "$TEST_URL"
wget -O "$REQUIREMENTS_FILE_PATH" "$REQUIREMENTS_URL"

# --- Step 2: Make the Python script executable ---
echo "2. Making the Python script executable..."
chmod +x "$SCRIPT_PATH"

# --- Step 3: Install dependencies ---
echo "3. Installing dependencies for the Python scripts..."

# First, install apt packages for Python development and GUI library.
sudo apt-get update
sudo apt-get install -y python3-pip python3-tk python3-dev

# Next, use pip to install the required Python libraries.
pip3 install opencv-python face-recognition Pillow numpy --break-system-packages

# --- Step 4: Create the systemd service file ---
echo "4. Creating systemd service file: $SERVICE_FILE_PATH"
# We use 'sudo tee' to write the service file to the protected directory.
sudo tee "$SERVICE_FILE_PATH" > /dev/null << EOF
[Unit]
Description=My custom boot script
# This ensures the network is up before the script runs.
After=network.target

[Service]
# The full path to the executable script.
ExecStart=$SCRIPT_PATH
# 'oneshot' means the service is short-lived and exits after running.
Type=oneshot
# 'RemainAfterExit=yes' keeps the service in an 'active' state after it finishes.
RemainAfterExit=yes
# Runs the script as the current user, not as the root user.
User=$USER_NAME

[Install]
# The service will be started during the boot process after all multi-user services are up.
WantedBy=multi-user.target
EOF

# --- Step 5: Reload, enable, and start the service ---
echo "5. Reloading systemd to recognize the new service..."
sudo systemctl daemon-reload

echo "6. Enabling the service to start on boot..."
sudo systemctl enable "$SERVICE_NAME"

echo "7. Starting the service now to test it..."
sudo systemctl start "$SERVICE_NAME"

# --- Step 6: Verify and provide next steps ---
echo "---"
echo "Setup complete. Here is the current status of the service:"
sudo systemctl status "$SERVICE_NAME"
echo "You can check the log file at: $LOG_FILE"
echo ""
echo "To disable this service from starting at boot, run:"
echo "    sudo systemctl disable $SERVICE_NAME"
echo "To completely remove the service and scripts, run:"
echo "    sudo rm $SERVICE_FILE_PATH"
echo "    sudo rm $SCRIPT_PATH"
echo "    sudo rm $TEST_SCRIPT_PATH"
echo "    sudo rm $REQUIREMENTS_FILE_PATH"
echo "You may also want to remove the log file with: rm $LOG_FILE"
