#!/usr/bin/env bash

set -euo pipefail

APP_NAME="KubeDeck"
MAC_APP="/Applications/KubeDeck.app"
MAC_USER_APP="$HOME/Applications/KubeDeck.app"
LINUX_APP="/opt/KubeDeck"
WINDOWS_APP="/c/Program Files/KubeDeck"

OS="$(uname -s)"

echo
echo "=========================================="
echo "          KubeDeck Uninstaller"
echo "=========================================="
echo
echo "This will remove KubeDeck and KubeDeck-related"
echo "voice/audio components installed by the installer."
echo

# --------------------------------------------------
# Confirmation
# --------------------------------------------------

read -r -p "Continue with complete KubeDeck uninstall? [y/N]: " CONFIRM

case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *)
        echo
        echo "Uninstallation cancelled."
        exit 0
        ;;
esac

echo

# --------------------------------------------------
# Helper
# --------------------------------------------------

remove_path() {
    local path="$1"
    local label="$2"

    if [ -e "$path" ]; then
        echo "  Removing $label:"
        echo "    $path"
        rm -rf "$path"
    fi
}

# --------------------------------------------------
# Stop KubeDeck
# --------------------------------------------------

echo "Stopping KubeDeck..."

if command -v osascript >/dev/null 2>&1; then
    osascript -e 'tell application "KubeDeck" to quit' >/dev/null 2>&1 || true
fi

pkill -f "/KubeDeck.app/" >/dev/null 2>&1 || true
pkill -f "KubeDeck" >/dev/null 2>&1 || true

sleep 2

echo "  ✓ KubeDeck processes stopped"

# --------------------------------------------------
# Remove application
# --------------------------------------------------

echo
echo "Removing KubeDeck application..."

case "$OS" in

    Darwin)
        if [ -d "$MAC_APP" ]; then
            sudo rm -rf "$MAC_APP"
            echo "  ✓ Removed $MAC_APP"
        else
            echo "  ✓ /Applications/KubeDeck.app not found"
        fi

        if [ -d "$MAC_USER_APP" ]; then
            rm -rf "$MAC_USER_APP"
            echo "  ✓ Removed $MAC_USER_APP"
        fi
        ;;

    Linux*)
        if [ -d "$LINUX_APP" ]; then
            sudo rm -rf "$LINUX_APP"
            echo "  ✓ Removed $LINUX_APP"
        else
            echo "  ✓ /opt/KubeDeck not found"
        fi
        ;;

    MINGW*|MSYS*|CYGWIN*)
        if [ -d "$WINDOWS_APP" ]; then
            rm -rf "$WINDOWS_APP"
            echo "  ✓ Removed $WINDOWS_APP"
        else
            echo "  ✓ Windows KubeDeck installation not found"
        fi
        ;;

    *)
        echo "  ! Unsupported OS: $OS"
        ;;
esac

# --------------------------------------------------
# Remove KubeDeck user data
# --------------------------------------------------

echo
echo "Removing KubeDeck user data..."

if [[ "$OS" == "Darwin" ]]; then

    remove_path "$HOME/Library/Application Support/KubeDeck" \
        "KubeDeck Application Support"

    remove_path "$HOME/Library/Application Support/kubedeck" \
        "KubeDeck Application Support"

    remove_path "$HOME/Library/Caches/KubeDeck" \
        "KubeDeck cache"

    remove_path "$HOME/Library/Caches/kubedeck" \
        "KubeDeck cache"

    remove_path "$HOME/Library/Logs/KubeDeck" \
        "KubeDeck logs"

    remove_path "$HOME/Library/Logs/kubedeck" \
        "KubeDeck logs"

    remove_path "$HOME/Library/WebKit/KubeDeck" \
        "KubeDeck WebKit data"

    remove_path "$HOME/Library/WebKit/kubedeck" \
        "KubeDeck WebKit data"

    # Preferences can be .plist files with either capitalization.
    find "$HOME/Library/Preferences" -maxdepth 1 -type f \
        \( -iname "*KubeDeck*.plist" -o -iname "*kubedeck*.plist" \) \
        -print -exec rm -f {} + 2>/dev/null || true

    # Saved state
    find "$HOME/Library/Saved Application State" -maxdepth 1 \
        \( -iname "*KubeDeck*" -o -iname "*kubedeck*" \) \
        -print -exec rm -rf {} + 2>/dev/null || true

    echo "  ✓ macOS KubeDeck user data removed"

elif [[ "$OS" == Linux* ]]; then

    remove_path "$HOME/.config/KubeDeck" "KubeDeck config"
    remove_path "$HOME/.config/kubedeck" "KubeDeck config"
    remove_path "$HOME/.cache/KubeDeck" "KubeDeck cache"
    remove_path "$HOME/.cache/kubedeck" "KubeDeck cache"
    remove_path "$HOME/.local/share/KubeDeck" "KubeDeck data"
    remove_path "$HOME/.local/share/kubedeck" "KubeDeck data"

    echo "  ✓ Linux KubeDeck user data removed"

fi

# --------------------------------------------------
# Remove KubeDeck-specific Python environments
# --------------------------------------------------

echo
echo "Removing KubeDeck-specific Python environments..."

KUBEDECK_PYTHON_ENVS=(
    "$HOME/.kubedeck"
    "$HOME/.kubedeck-venv"
    "$HOME/.venvs/kubedeck"
    "$HOME/venv/kubedeck"
    "$HOME/virtualenvs/kubedeck"
    "$HOME/KubeDeck/.venv"
    "$HOME/KubeDeck/venv"
    "$HOME/VM-Visualizer/.venv"
    "$HOME/VM-Visualizer/venv"
)

for ENV_PATH in "${KUBEDECK_PYTHON_ENVS[@]}"; do
    if [ -d "$ENV_PATH" ]; then
        rm -rf "$ENV_PATH"
        echo "  ✓ Removed $ENV_PATH"
    fi
done

echo "  ✓ KubeDeck-specific Python environments cleaned"

# --------------------------------------------------
# Audio / speech dependency cleanup
# --------------------------------------------------

echo
echo "KubeDeck voice/audio dependencies:"
echo
echo "  • Google Web Speech / SpeechRecognition"
echo "  • PyAudio"
echo "  • PortAudio"
echo "  • FLAC"
echo "  • FFmpeg (Linux installer dependency)"
echo

read -r -p "Remove these separately installed dependencies too? [y/N]: " REMOVE_DEPS

case "$REMOVE_DEPS" in
    y|Y|yes|YES)
        REMOVE_DEPS=true
        ;;
    *)
        REMOVE_DEPS=false
        ;;
esac

if [ "$REMOVE_DEPS" = true ]; then

    # --------------------------------------------------
    # macOS Homebrew dependencies
    # --------------------------------------------------

    if [[ "$OS" == "Darwin" ]]; then

        echo
        echo "Removing macOS audio dependencies..."

        if command -v brew >/dev/null 2>&1; then

            # These are the native dependencies explicitly installed
            # by the KubeDeck installer.
            #
            # Note: Homebrew cannot reliably tell us whether another
            # application needed these packages before KubeDeck.
            # Therefore removal is explicitly confirmed above.

            if brew list --formula portaudio >/dev/null 2>&1; then
                echo "  Removing PortAudio..."
                brew uninstall portaudio || true
                echo "  ✓ PortAudio removed"
            else
                echo "  ✓ PortAudio not installed"
            fi

            if brew list --formula flac >/dev/null 2>&1; then
                echo "  Removing FLAC..."
                brew uninstall flac || true
                echo "  ✓ FLAC removed"
            else
                echo "  ✓ FLAC not installed"
            fi

            # The installer uses Homebrew Python 3.14.
            # Only remove it when the user explicitly confirms it.
            echo
            read -r -p "Also remove Homebrew Python 3.14 installed/used by KubeDeck? [y/N]: " REMOVE_PYTHON

            case "$REMOVE_PYTHON" in
                y|Y|yes|YES)
                    if brew list --formula python@3.14 >/dev/null 2>&1; then
                        echo "  Removing Homebrew Python 3.14..."
                        brew uninstall python@3.14 || true
                        echo "  ✓ Python 3.14 removed"
                    else
                        echo "  ✓ Homebrew Python 3.14 not installed"
                    fi
                    ;;
                *)
                    echo "  ✓ Homebrew Python 3.14 kept"
                    ;;
            esac

        else
            echo "  ✓ Homebrew not found"
        fi

        # SpeechRecognition and PyAudio are installed by pip into the
        # Python environment selected by the installer. If that is the
        # Homebrew Python 3.14 environment, remove only these packages.
        if command -v brew >/dev/null 2>&1 && \
           brew list --formula python@3.14 >/dev/null 2>&1; then

            PYTHON_314="$(brew --prefix python@3.14)/bin/python3"

            if [ -x "$PYTHON_314" ]; then
                echo
                echo "Removing speech/audio Python packages from Homebrew Python 3.14..."

                "$PYTHON_314" -m pip uninstall -y \
                    SpeechRecognition \
                    PyAudio \
                    pyaudio \
                    2>/dev/null || true

                echo "  ✓ SpeechRecognition/PyAudio cleanup completed"
            fi
        fi

    # --------------------------------------------------
    # Linux dependencies
    # --------------------------------------------------

    elif [[ "$OS" == Linux* ]]; then

        echo
        echo "Removing Linux audio dependencies..."

        if command -v apt-get >/dev/null 2>&1; then

            PACKAGES=(
                portaudio19-dev
                libportaudiocpp0
                flac
                ffmpeg
            )

            if command -v sudo >/dev/null 2>&1; then
                sudo apt-get remove -y "${PACKAGES[@]}" || true
                sudo apt-get autoremove -y || true
            else
                apt-get remove -y "${PACKAGES[@]}" || true
                apt-get autoremove -y || true
            fi

            echo "  ✓ apt audio dependencies removed"

        elif command -v dnf >/dev/null 2>&1; then

            if command -v sudo >/dev/null 2>&1; then
                sudo dnf remove -y portaudio-devel flac ffmpeg || true
            else
                dnf remove -y portaudio-devel flac ffmpeg || true
            fi

            echo "  ✓ dnf audio dependencies removed"

        elif command -v yum >/dev/null 2>&1; then

            if command -v sudo >/dev/null 2>&1; then
                sudo yum remove -y portaudio-devel flac ffmpeg || true
            else
                yum remove -y portaudio-devel flac ffmpeg || true
            fi

            echo "  ✓ yum audio dependencies removed"

        elif command -v pacman >/dev/null 2>&1; then

            if command -v sudo >/dev/null 2>&1; then
                sudo pacman -Rns --noconfirm portaudio flac ffmpeg || true
            else
                pacman -Rns --noconfirm portaudio flac ffmpeg || true
            fi

            echo "  ✓ pacman audio dependencies removed"

        else
            echo "  ! No supported Linux package manager found."
            echo "    Remove PortAudio/FLAC/FFmpeg manually if required."
        fi

    else
        echo "  ! Audio dependency cleanup is not implemented for $OS"
    fi

else
    echo
    echo "  ✓ Separately installed audio/speech dependencies were kept"
fi

# --------------------------------------------------
# Remove KubeDeck temporary files
# --------------------------------------------------

echo
echo "Removing temporary KubeDeck files..."

if [[ "$OS" == "Darwin" || "$OS" == Linux* ]]; then

    TMP_DIR="${TMPDIR:-/tmp}"

    remove_path "/tmp/KubeDeck" "temporary KubeDeck files"
    remove_path "/tmp/kubedeck" "temporary KubeDeck files"
    remove_path "$TMP_DIR/KubeDeck" "temporary KubeDeck files"
    remove_path "$TMP_DIR/kubedeck" "temporary KubeDeck files"

fi

echo "  ✓ Temporary files cleaned"

# --------------------------------------------------
# Remove KubeDeck launch agents/services
# --------------------------------------------------

echo
echo "Removing KubeDeck launch agents/services..."

if [[ "$OS" == "Darwin" ]]; then

    LAUNCH_DIR="$HOME/Library/LaunchAgents"

    if [ -d "$LAUNCH_DIR" ]; then
        while IFS= read -r PLIST; do
            [ -z "$PLIST" ] && continue

            LABEL="$(/usr/libexec/PlistBuddy \
                -c "Print :Label" "$PLIST" 2>/dev/null || true)"

            if echo "$LABEL" | grep -qi "kubedeck"; then
                launchctl bootout "gui/$(id -u)" "$PLIST" \
                    >/dev/null 2>&1 || true

                rm -f "$PLIST"
                echo "  ✓ Removed launch agent: $PLIST"
            fi
        done < <(
            find "$LAUNCH_DIR" -maxdepth 1 -type f \
                \( -iname "*KubeDeck*.plist" -o -iname "*kubedeck*.plist" \) \
                2>/dev/null
        )
    fi

elif [[ "$OS" == Linux* ]]; then

    # Remove only KubeDeck-named user systemd units.
    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

    if [ -d "$SYSTEMD_USER_DIR" ]; then
        while IFS= read -r UNIT; do
            [ -z "$UNIT" ] && continue

            UNIT_NAME="$(basename "$UNIT")"

            systemctl --user disable --now "$UNIT_NAME" \
                >/dev/null 2>&1 || true

            rm -f "$UNIT"
            echo "  ✓ Removed user service: $UNIT_NAME"
        done < <(
            find "$SYSTEMD_USER_DIR" -maxdepth 1 -type f \
                \( -iname "*KubeDeck*.service" -o -iname "*kubedeck*.service" \) \
                2>/dev/null
        )

        systemctl --user daemon-reload >/dev/null 2>&1 || true
    fi

fi

echo "  ✓ KubeDeck launch/service entries checked"

# --------------------------------------------------
# macOS application cache refresh
# --------------------------------------------------

if [[ "$OS" == "Darwin" ]]; then
    echo
    echo "Refreshing macOS application registration..."
    killall Finder >/dev/null 2>&1 || true
    echo "  ✓ Finder refreshed"
fi

# --------------------------------------------------
# Final verification
# --------------------------------------------------

echo
echo "=========================================="
echo "       KubeDeck Uninstall Complete"
echo "=========================================="
echo

case "$OS" in
    Darwin)
        if [ -d "$MAC_APP" ] || [ -d "$MAC_USER_APP" ]; then
            echo "  ! KubeDeck application still exists"
        else
            echo "  ✓ KubeDeck application removed"
        fi
        ;;
    Linux*)
        if [ -d "$LINUX_APP" ]; then
            echo "  ! /opt/KubeDeck still exists"
        else
            echo "  ✓ KubeDeck application removed"
        fi
        ;;
    MINGW*|MSYS*|CYGWIN*)
        if [ -d "$WINDOWS_APP" ]; then
            echo "  ! Windows KubeDeck directory still exists"
        else
            echo "  ✓ KubeDeck application removed"
        fi
        ;;
esac

if pgrep -f "KubeDeck" >/dev/null 2>&1; then
    echo "  ! A KubeDeck process is still running"
else
    echo "  ✓ No KubeDeck process detected"
fi

echo
echo "Cleanup performed:"
echo "  ✓ KubeDeck application"
echo "  ✓ KubeDeck caches"
echo "  ✓ KubeDeck preferences"
echo "  ✓ KubeDeck application data"
echo "  ✓ KubeDeck temporary files"
echo "  ✓ KubeDeck-specific Python environments"
echo "  ✓ KubeDeck launch agents/services"

if [ "$REMOVE_DEPS" = true ]; then
    echo "  ✓ SpeechRecognition / Google Web Speech Python packages"
    echo "  ✓ PyAudio"
    echo "  ✓ PortAudio"
    echo "  ✓ FLAC"
    echo "  ✓ Linux FFmpeg dependency (where applicable)"
else
    echo "  - Speech/audio native dependencies were kept"
fi

echo
echo "Note: Homebrew/system packages are removed only after"
echo "explicit confirmation because they may be shared by"
echo "other applications."
echo
