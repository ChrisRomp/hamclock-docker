#!/bin/bash

# retry_clearskyinstitute.sh
# A script to handle requests to clearskyinstitute.com with retry logic and exponential backoff
# Usage: ./retry_clearskyinstitute.sh <action> <url> [output_file]
# Actions: 
#   get_version - Fetch version info (returns first line)
#   download - Download a file
#   get_content - Get full content (saves to output_file or stdout)

set -e

ACTION="$1"
URL="$2"
OUTPUT_FILE="$3"

if [ -z "$ACTION" ] || [ -z "$URL" ]; then
    echo "Usage: $0 <action> <url> [output_file]"
    echo "Actions: get_version, download, get_content"
    exit 1
fi

# Retry function with exponential backoff
retry_with_backoff() {
    local action="$1"
    local url="$2"
    local output_file="$3"
    local max_attempts=8  # ~5 minutes total (1+2+4+8+16+32+64+128 = 255 seconds)
    local attempt=1
    local delay=1
    
    while [ $attempt -le $max_attempts ]; do
        echo "Attempt $attempt/$max_attempts: $action from $url" >&2
        
        case "$action" in
            "get_version")
                local timeout=10
                if result=$(curl -s -m $timeout "$url" | head -n 1); then
                    if [ -n "$result" ]; then
                        echo "$result"
                        return 0
                    fi
                fi
                ;;
            "download")
                local timeout=30
                local filename=$(basename "$url")
                if curl --max-time $timeout -O "$url"; then
                    if [ -f "$filename" ]; then
                        echo "Successfully downloaded $filename" >&2
                        return 0
                    fi
                fi
                # Clean up partial download
                rm -f "$filename"
                ;;
            "get_content")
                local timeout=15
                if [ -n "$output_file" ]; then
                    if curl -s -m $timeout "$url" > "$output_file"; then
                        if [ -s "$output_file" ]; then
                            echo "Successfully saved content to $output_file" >&2
                            return 0
                        fi
                    fi
                else
                    if result=$(curl -s -m $timeout "$url"); then
                        if [ -n "$result" ]; then
                            echo "$result"
                            return 0
                        fi
                    fi
                fi
                ;;
            *)
                echo "Unknown action: $action" >&2
                return 1
                ;;
        esac
        
        if [ $attempt -eq $max_attempts ]; then
            echo "Failed to $action after $max_attempts attempts" >&2
            return 1
        fi
        
        echo "Attempt $attempt failed, retrying in ${delay}s..." >&2
        sleep $delay
        delay=$((delay * 2))
        attempt=$((attempt + 1))
    done
}

# Execute the retry function
retry_with_backoff "$ACTION" "$URL" "$OUTPUT_FILE"
