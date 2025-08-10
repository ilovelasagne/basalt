#!/usr/bin/env bash
# This script has been modified to remove all systemd service creation and
# autologin configuration. It sets up the unlock script and a secure wrapper,
# and directly configures /etc/rc.local to execute the wrapper on boot.

set -e

# --- Configuration Variables ---
# The name of the new script to be run for the unlock process.
UNLOCK_SCRIPT_NAME="testcode.py"
UNLOCK_SCRIPT_PATH="/usr/local/bin/$UNLOCK_SCRIPT_NAME"

# The name of the final script to be run after installation.#!/usr/bin/env bash
# This script has been modified to remove the virtual environment and
# to use the --break-system-packages flag for a system-wide installation.
# It sets up the unlock script and a secure wrapper, and directly
# configures /etc/rc.local to execute the wrapper on boot.

set -e

# --- Configuration Variables ---
# The name of the new script to be run for the unlock process.
UNLOCK_SCRIPT_NAME="testcode.py"
UNLOCK_SCRIPT_PATH="/usr/local/bin/$UNLOCK_SCRIPT_NAME"

# The name of the final script to be run after installation.
POST_INSTALL_SCRIPT="test.py"

# The secure wrapper script that handles failure counts and runs the unlock script.
SECURE_WRAPPER="/usr/local/bin/face_unlock_secure.sh"

# The user and TTY to configure for autologin.
USER_NAME="$(logname)"
TTY_NUM="1"

# File to track failure count for the secure wrapper's failsafe.
FAIL_COUNT_FILE="/tmp/face_unlock_failcount"

# URL for the dependencies file and the files to download.
DEPENDENCIES_URL="https://raw.githubusercontent.com/ilovelasagne/basalt/main/dependencies.txt"
DEPENDENCIES_FILE="dependencies.txt"

# --- Helper Functions ---
err() { echo "[ERROR] $1" >&2; exit 1; }
info() { echo "[INFO] $1"; }
ok() { echo "[OK] $1"; }

# --- Installation Steps ---

# Fetch the necessary Python scripts from GitHub
info "Fetching Python scripts from GitHub..."
curl -o "$UNLOCK_SCRIPT_NAME" https://raw.githubusercontent.com/ilovelasagne/basalt/refs/heads/main/testcode.py || err "Failed to download $UNLOCK_SCRIPT_NAME"
curl -o "$POST_INSTALL_SCRIPT" https://raw.githubusercontent.com/ilovelasagne/basalt/refs/heads/main/test.py || err "Failed to download $POST_INSTALL_SCRIPT"

# Fetch dependencies
info "Fetching dependencies from GitHub..."
curl -o "$DEPENDENCIES_FILE" "$DEPENDENCIES_URL" || err "Failed to download dependencies.txt"

# Install dependencies using the system's pip with --break-system-packages
info "Installing Python dependencies with --break-system-packages..."
# Check if python3-pip is installed
if ! command -v pip3 &> /dev/null
then
    info "pip3 not found, installing it now."
    sudo apt-get update && sudo apt-get install -y python3-pip || err "Failed to install python3-pip"
fi
sudo python3 -m pip install -r "$DEPENDENCIES_FILE" --break-system-packages || err "Failed to install dependencies"

# Check if the unlock script exists after fetching.
[ -f "$UNLOCK_SCRIPT_NAME" ] || err "$UNLOCK_SCRIPT_NAME not found in current directory. Download failed."

info "Copying $UNLOCK_SCRIPT_NAME to $UNLOCK_SCRIPT_PATH"
sudo cp "$UNLOCK_SCRIPT_NAME" "$UNLOCK_SCRIPT_PATH" || err "Failed to copy $UNLOCK_SCRIPT_NAME to $UNLOCK_SCRIPT_PATH"
# We need to make the script executable since we are not using the virtual environment.
sudo chmod +x "$UNLOCK_SCRIPT_PATH" || err "Failed to make $UNLOCK_SCRIPT_PATH executable"

# --- RCONF or Init System Configuration ---
# This section adds the command to /etc/rc.local, which is the rconf runlevel file.
# The command now points to our secure wrapper script.

info "Configuring rconf by adding a command to /etc/rc.local"
# Ensure the file exists and is executable
sudo touch /etc/rc.local
sudo chmod +x /etc/rc.local

# Add the command to the file.
# The `exec` command is used to replace the current shell with the new process,
# which is a common practice for init scripts to keep the process in the foreground.
# We also add a failsafe comment to make it easier to find and remove later.
if ! grep -q "$SECURE_WRAPPER" /etc/rc.local; then
    sudo sed -i '/^exit 0/d' /etc/rc.local
    echo "# Face Unlock Failsafe - Do not remove this comment." | sudo tee -a /etc/rc.local >/dev/null
    echo "exec $SECURE_WRAPPER" | sudo tee -a /etc/rc.local >/dev/null
    echo "exit 0" | sudo tee -a /etc/rc.local >/dev/null
else
    info "The secure wrapper is already configured in /etc/rc.local."
fi

info "Creating secure wrapper script at $SECURE_WRAPPER"
cat <<EOF | sudo tee "$SECURE_WRAPPER" >/dev/null
#!/usr/bin/env bash
# This wrapper script handles the failure count and the failsafe mechanism.
# It runs the unlock script using the system's python interpreter.
trap '' INT TSTP TERM HUP QUIT
FAIL_FILE="$FAIL_COUNT_FILE"

if [ ! -f "\$FAIL_FILE" ]; then
    echo 0 > "\$FAIL_FILE"
fi

COUNT=\$(cat "\$FAIL_FILE")
if [ "\$COUNT" -ge 3 ]; then
    echo "[FAILSAFE] Too many failures, disabling autologin..."
    # If the number of failures reaches the failsafe limit, remove the autologin line
    # from the rc.local file. We use a failsafe comment to ensure we only remove our line.
    sudo sed -i '/exec $SECURE_WRAPPER/d' /etc/rc.local
    sudo sed -i '/# Face Unlock Failsafe/d' /etc/rc.local
    
    loginctl terminate-user "\$USER"
    exit 1
fi

# Run the user's unlock script in the foreground using the system's python interpreter.
python3 /usr/local/bin/$UNLOCK_SCRIPT_NAME
if [ \$? -ne 0 ]; then
    COUNT=\$((COUNT + 1))
    echo "\$COUNT" > "\$FAIL_FILE"
    echo "[FAIL] Unlock script failed (\$COUNT/3)."
    sleep 3
    loginctl terminate-user "\$USER"
else
    echo 0 > "\$FAIL_FILE"
fi
EOF
sudo chmod +x "$SECURE_WRAPPER" || err "Failed to make "$SECURE_WRAPPER" executable"

# --- Final Execution ---

info "Installation setup complete."

# Execute the final script.
info "Executing $POST_INSTALL_SCRIPT..."
[ -f "$POST_INSTALL_SCRIPT" ] || err "$POST_INSTALL_SCRIPT not found in current directory."
# The final execution command now uses the system's python interpreter.
python3 "$POST_INSTALL_SCRIPT" || err "Failed to execute $POST_INSTALL_SCRIPT"

ok "All tasks finished."

POST_INSTALL_SCRIPT="test.py"

# The secure wrapper script that handles failure counts and runs the unlock script.
SECURE_WRAPPER="/usr/local/bin/face_unlock_secure.sh"

# The user and TTY to configure for autologin.
USER_NAME="$(logname)"
TTY_NUM="1"

# File to track failure count for the secure wrapper's failsafe.
FAIL_COUNT_FILE="/tmp/face_unlock_failcount"

# URL for the dependencies file
DEPENDENCIES_URL="https://raw.githubusercontent.com/ilovelasagne/basalt/main/dependencies.txt"
DEPENDENCIES_FILE="dependencies.txt"

# --- Helper Functions ---
err() { echo "[ERROR] $1" >&2; exit 1; }
info() { echo "[INFO] $1"; }
ok() { echo "[OK] $1"; }

# --- Installation Steps ---

# Fetch the necessary Python scripts from GitHub
info "Fetching Python scripts from GitHub..."
curl -o "$UNLOCK_SCRIPT_NAME" https://raw.githubusercontent.com/ilovelasagne/basalt/refs/heads/main/testcode.py || err "Failed to download $UNLOCK_SCRIPT_NAME"
curl -o "$POST_INSTALL_SCRIPT" https://raw.githubusercontent.com/ilovelasagne/basalt/refs/heads/main/test.py || err "Failed to download $POST_INSTALL_SCRIPT"

# Fetch dependencies
info "Fetching dependencies from GitHub..."
curl -o "$DEPENDENCIES_FILE" "$DEPENDENCIES_URL" || err "Failed to download dependencies.txt"

# Install dependencies using pip
info "Installing Python dependencies..."
# Check if python3-pip is installed
if ! command -v pip3 &> /dev/null
then
    info "pip3 not found, installing it now."
    sudo apt-get update && sudo apt-get install -y python3-pip || err "Failed to install python3-pip"
fi
sudo python3 -m pip install -r "$DEPENDENCIES_FILE" || err "Failed to install dependencies"

# Check if the unlock script exists after fetching.
[ -f "$UNLOCK_SCRIPT_NAME" ] || err "$UNLOCK_SCRIPT_NAME not found in current directory. Download failed."

info "Copying $UNLOCK_SCRIPT_NAME to $UNLOCK_SCRIPT_PATH"
sudo cp "$UNLOCK_SCRIPT_NAME" "$UNLOCK_SCRIPT_PATH" || err "Failed to copy $UNLOCK_SCRIPT_NAME to $UNLOCK_SCRIPT_PATH"
sudo chmod +x "$UNLOCK_SCRIPT_PATH" || err "Failed to make $UNLOCK_SCRIPT_PATH executable"

# --- RCONF or Init System Configuration ---
# The original systemd-specific autologin setup has been removed.
# This section adds the command to /etc/rc.local, which is the rconf runlevel file.

info "Configuring rconf by adding a command to /etc/rc.local"
# Ensure the file exists and is executable
sudo touch /etc/rc.local
sudo chmod +x /etc/rc.local

# Add the command to the file.
# The `exec` command is used to replace the current shell with the new process,
# which is a common practice for init scripts to keep the process in the foreground.
# We also add a failsafe comment to make it easier to find and remove later.
if ! grep -q "$SECURE_WRAPPER" /etc/rc.local; then
    sudo sed -i '/^exit 0/d' /etc/rc.local
    echo "# Face Unlock Failsafe - Do not remove this comment." | sudo tee -a /etc/rc.local >/dev/null
    echo "exec $SECURE_WRAPPER" | sudo tee -a /etc/rc.local >/dev/null
    echo "exit 0" | sudo tee -a /etc/rc.local >/dev/null
else
    info "The secure wrapper is already configured in /etc/rc.local."
fi

info "Creating secure wrapper script at $SECURE_WRAPPER"
cat <<EOF | sudo tee "$SECURE_WRAPPER" >/dev/null
#!/usr/bin/env bash
# This wrapper script handles the failure count and the failsafe mechanism.
# It runs the unlock script in the foreground.
trap '' INT TSTP TERM HUP QUIT
FAIL_FILE="$FAIL_COUNT_FILE"

if [ ! -f "\$FAIL_FILE" ]; then
    echo 0 > "\$FAIL_FILE"
fi

COUNT=\$(cat "\$FAIL_FILE")
if [ "\$COUNT" -ge 3 ]; then
    echo "[FAILSAFE] Too many failures, disabling autologin..."
    # If the number of failures reaches the failsafe limit, remove the autologin line
    # from the rc.local file. We use a failsafe comment to ensure we only remove our line.
    sudo sed -i '/exec $SECURE_WRAPPER/d' /etc/rc.local
    sudo sed -i '/# Face Unlock Failsafe/d' /etc/rc.local

    loginctl terminate-user "\$USER"
    exit 1
fi

# Run the user's unlock script in the foreground.
/usr/local/bin/$UNLOCK_SCRIPT_NAME
if [ \$? -ne 0 ]; then
    COUNT=\$((COUNT + 1))
    echo "\$COUNT" > "\$FAIL_FILE"
    echo "[FAIL] Unlock script failed (\$COUNT/3)."
    sleep 3
    loginctl terminate-user "\$USER"
else
    echo 0 > "\$FAIL_FILE"
fi
EOF
sudo chmod +x "$SECURE_WRAPPER" || err "Failed to make $SECURE_WRAPPER executable"

# --- Final Execution ---

info "Installation setup complete."

# Execute the final script.
info "Executing $POST_INSTALL_SCRIPT..."
[ -f "$POST_INSTALL_SCRIPT" ] || err "$POST_INSTALL_SCRIPT not found in current directory."
python3 "$POST_INSTALL_SCRIPT" || err "Failed to execute $POST_INSTALL_SCRIPT"

ok "All tasks finished."
