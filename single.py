"""
Example of a single player connecting to an offline server
"""
from enum import Enum
from protocol import Player 
import asyncio
import socket
import threading

def start_server(host="0.0.0.0", port=8080):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((host, port))
        server_socket.listen(5)
        print(f"Serving on {host}:{port}")

        while True:
            client_socket, client_address = server_socket.accept()
            with client_socket:
                request = client_socket.recv(1024).decode()
                if request.startswith("GET"):
                    response = "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: text/plain\r\n\r\nOK"
                    client_socket.sendall(response.encode())

async def send_periodic_chat(agent):
    """Send a chat message every second"""
    while True:
        await asyncio.sleep(1)
        #await agent.chat("hello world")

class Commands(Enum):
    DIE = "kill @s"
    HEAL = "heal 20"

async def start(ip: str="127.0.0.1", port: int=25565):
    """

    """
    server = threading.Thread(target=start_server, daemon=True)
    server.start()

    agent = Player(name="operator")
    
    try:
        await agent.connect(ip, port)
    except Exception as e:
        print("Disconnected ", e)

if __name__ == "__main__":
    asyncio.run(start())

