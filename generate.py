"""Generate all packets, blocks, and other asset data extracted from Minecraft"""
import logging
import json

def generate():
    packets = None
    
    if packets is None:
        with open("./generated/generated/reports/packets.json", "r") as file:
            packets = json.load(file)
    
    pool = packets["play"]["clientbound"]
    
    with open("./packets.py", "w") as file:
        file.write("from typing import Literal, Dict\n")
        file.write("\n")
        file.write("Protocol = Literal[\n")
        
        for packet in pool:
            protocol_id = pool[packet]["protocol_id"]
            packet = packet.split(":")[1]
            file.write(f"    \"{packet}\",\n")
        
        file.write("]")
        file.write("\n")
        file.write("clientbound: Dict[Protocol, int] = {\n")

        for packet in pool:
            protocol_id = pool[packet]["protocol_id"]
            packet = packet.split(":")[1]
            file.write(f"    \"{packet}\": {hex(protocol_id)},\n")
        
        file.write("}\n\n")
        file.flush()
        file.close()

if __name__ == "__main__":
    import subprocess
    import argparse

    parser = argparse.ArgumentParser(description="Generate the packets.py file from generated server reports")
    parser.add_argument("-r", "--reports", help="Generate the reports from the server jar", action='store_true')

    # Parse arguments
    args = parser.parse_args()
    
    if args.reports:
        rv = subprocess.call(("cd ./generated && " +
                          "java -DbundlerMainClass='net.minecraft.data.Main' -jar " +
                          "../server/server.jar --reports"
                          ), shell=True)

    generate()

