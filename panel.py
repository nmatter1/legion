"""Control panel for connected agents"""
import socket
import logging
from typing import Dict

def not_found():
    return ""

def handle_request(
        response: socket.socket, 
        method: str, 
        path: str, 
        http_version: str, 
        headers: Dict[str, str],
        templates: Dict[str, str]):
    
    if method == "GET":
        if path == "/sdffavicon.ico":
            return not_found()
        elif path == "/":
            template = templates["index"]
            res_headers = {
                "Content-Length": len(template), 
                "Content-Type": "text/html; charset=utf-8"
            }

            result = ("HTTP/1.1 200 OK\r\n" + build_http_headers(res_headers) + "\r\n" + template)
            response.sendall(result.encode("utf-8"))
        elif path == "/tileset.png":
            template = templates["tileset"]
            res_headers = {
                "Content-Length": len(template), 
                "Content-Type": "text/plain"
            }

            result = ("HTTP/1.1 200 OK\r\n" + build_http_headers(res_headers) + "\r\n\r\n" + template)
            response.sendall(result.encode("utf-8"))
    else:
        logging.error("Method not supported")

async def start_server(host="0.0.0.0", port=8080):
    """Start the control panel web page to view chunk data and player information"""
    templates = {}

    with open("./panel/index.html", "r") as file:
        templates["index"] = file.read()
    
    with open("./panel/tileset.png", "rb") as file:
        templates["tileset"] = file.read()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
            server_socket.bind((host, port))
            server_socket.listen(5)
            logging.info(f"Serving on {host}:{port}")

            while True:
                client, client_address = server_socket.accept()
                with client:
                    request = client.recv(1024).decode() # XXX: max bytes may send less
                    method, path, version = parse_request_line(request)
                    headers = parse_http_headers(request)
                    
                    if len(request) == 0:
                        raise IOError("Connection closed")
                    
                    handle_request(client, method, path, version, headers, templates) 

def build_http_headers(headers_map):
    headers = []
    
    for key, value in headers_map.items():
        headers.append(f"{key}: {value}")
    
    return "\r\n".join(headers)

def parse_request_line(request_line):
    parts = request_line.split()
    if len(parts) >= 3:
        method = parts[0]
        path = parts[1]
        version = parts[2]
        return method, path, version
    else:
        raise ValueError("Invalid request line format")

def parse_http_headers(header_data) -> Dict[str, str]:
    headers = header_data.splitlines()

    parsed_headers = {}

    for header in headers:
        if not header.strip():
            continue

        header_parts = header.split(":", 1)
        if len(header_parts) == 2:
            key = header_parts[0].strip()
            value = header_parts[1].strip()
            parsed_headers[key] = value

    return parsed_headers

