#!/bin/bash

# Define the target URLs
URLS=(
    "https://cscratch-dg-171510694317.us-central1.run.app/ping"
    "https://cscratch-171510694317.us-central1.run.app/ping"
)

echo "Keep-alive active. Pinging ${#URLS[@]} targets every 5 minutes..."
echo "Press Ctrl+C to stop."

while true; do
    TIMESTAMP=$(date +%H:%M:%S)
    
    for URL in "${URLS[@]}"; do
        # Curl the URL, silence the output, and capture the HTTP code
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
        echo "[$TIMESTAMP] $URL - Status: $HTTP_CODE"
    done

    # Wait 300 seconds (5 minutes)
    sleep 300
done