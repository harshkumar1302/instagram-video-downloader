#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Installing Python dependencies..."
python3 -m pip install -r requirements.txt

echo "Checking for FFmpeg..."

# Define the installation directory for FFmpeg
# We install it within the project directory so we don't need root/sudo
FFMPEG_DIR="$PWD/ffmpeg_bin"
mkdir -p "$FFMPEG_DIR"

if [ ! -f "$FFMPEG_DIR/ffmpeg" ]; then
    echo "Downloading static FFmpeg build..."
    
    # Download a static build of FFmpeg for Linux amd64
    curl -sLO https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
    
    echo "Extracting FFmpeg..."
    tar -xf ffmpeg-release-amd64-static.tar.xz

    # The tarball extracts a folder named like "ffmpeg-6.0-amd64-static"
    # We find it and move the binaries to our target directory
    extracted_dir=$(find . -maxdepth 1 -type d -name "ffmpeg-*-amd64-static" | head -n 1)
    
    if [ -n "$extracted_dir" ]; then
        mv "$extracted_dir/ffmpeg" "$FFMPEG_DIR/"
        mv "$extracted_dir/ffprobe" "$FFMPEG_DIR/"
        
        # Clean up the downloaded files and extracted folder
        rm -rf "$extracted_dir"
        rm ffmpeg-release-amd64-static.tar.xz
        
        echo "Successfully installed FFmpeg to $FFMPEG_DIR"
    else
        echo "Error finding extracted FFmpeg directory."
        exit 1
    fi
else
    echo "FFmpeg already exists at $FFMPEG_DIR/ffmpeg, skipping download."
fi

echo "Build complete."
