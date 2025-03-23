#!/bin/bash

SERVER_URL="https://piston-data.mojang.com/v1/objects/4707d00eb834b446575d89a61a11b5d548d8c001/server.jar"
SERVER_DIR="./server"
SERVER_FILE="server.jar"
EULA_FILE="eula.txt"
PROPERTIES_FILE="server.properties"

mkdir -p "$SERVER_DIR"
cd "$SERVER_DIR"

if [ ! -f "$SERVER_FILE" ]; then
  echo "Downloading Minecraft server..."
  wget "$SERVER_URL" -O "$SERVER_FILE"
  java -Xmx1024M -Xms1024M -jar "$SERVER_FILE" nogui
fi

if [ ! -f "$EULA_FILE" ]; then
  echo "eula=true" > "$EULA_FILE"
else
  sed -i 's/eula=false/eula=true/' "$EULA_FILE"
fi

sed -i 's/online-mode=true/online-mode=false/' "$PROPERTIES_FILE"
sed -i 's/network-compression-threshold=256/network-compression-threshold=-1/' "$PROPERTIES_FILE"

echo "Starting Minecraft server..."
java -Xmx1024M -Xms1024M -jar "$SERVER_FILE" nogui
