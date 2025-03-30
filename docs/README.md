# Legion
Headless Minecraft client written in python. Simulate any amount of players on offline servers without needing multiple accounts and with low resource utilization.

## Progress
This library is currently in heavy development. Features currently implemented:
- [x] player connections
- [x] login and handshake packets
- [x] Full chunk data packets
- [ ] Player walking
- [ ] Physics (gravity and knockback)
- [ ] Control web app with minimap and chunk rendering

## Usage
1. Install the requirements pip install -r requirements.txt
2. Run ./start.sh command to automatically install and start a vanilla 1.21.4 Minecraft server on localhost:25565 in offline mode
3. Run the command python single.py

A fake player will then iniate a connection, join the server, then read the chunk data at the spawn position 

https://github.com/user-attachments/assets/f639a928-c296-490a-854f-5028942386a4
