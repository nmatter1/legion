#!/bin/bash

SERVER_URL="https://piston-data.mojang.com/v1/objects/baab122c7652b302621f7befd5be40abef9b9b7c/server.jar"
SERVER_DIR="./server"
SERVER_FILE="server.jar"
EULA_FILE="eula.txt"
PROPERTIES_FILE="server.properties"

mkdir -p "$SERVER_DIR"
cd "$SERVER_DIR"

if [ ! -f "$SERVER_FILE" ]; then
  echo "Downloading Minecraft server..."
  wget "$SERVER_URL" -O "$SERVER_FILE"
fi

if [ ! -f "$EULA_FILE" ]; then
  echo "eula=true" > "$EULA_FILE"
else
  sed -i 's/eula=false/eula=true/' "$EULA_FILE"
fi

if [ -f "$PROPERTIES_FILE" ]; then
  sed -i 's/online-mode=true/online-mode=false/' "$PROPERTIES_FILE"
else
  echo "server.properties not found."
fi

echo "Starting Minecraft server..."
java -Xmx1024M -Xms1024M -Dserver.properties=./server/server.properties -jar "$SERVER_FILE" nogui
