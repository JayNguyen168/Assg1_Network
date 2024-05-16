import json
import socket
import sys
import threading
from typing import Any


class TrackerBackEnd:
    def __init__(self, host, port, log_callback=None, log_request_callback=None):       
        self.host = host
        self.port = port
        # peers -> {peer_address: {"hostname": hostname, "files": [dictionary of files]}}
        self.peers = (
            {}
        )  
        self.lock = threading.Lock()
        self.is_running = False
        self.log_callback = log_callback
        self.log_request_callback = log_request_callback

    def start(self):
        self.log_callback("Tracker is starting...")
        server_thread = threading.Thread(target=self.run, daemon=True)
        server_thread.start()

    def stop(self):
        """Stop the tracker and close the socket"""
        self.is_running = False
        self._shutdown_socket()
        sys.exit()

    def run(self):
        """Setup socket for the tracker and start listening for peers' connections"""
        with self.lock:
            if self.is_running:
                self.log_callback("Tracker is already running!")
                return
            self._setup_socket()

        self._accept_connections()

    def handle_peer_conn(self, conn, addr):
        """Handle a peer connection

        Args:
            conn (socket): The peer's socket
            addr (tuple[str, int]): The peer's address
        """
        with self.lock:
            self.peers[addr] = {
                "hostname": None,
                "status": "active",
                "files": [],
            }

        if self.is_running:
            self.log_callback(f"New peer connection from {addr}")

        while self.peers[addr]["status"] == "active" and self.is_running:
            try:
                request = conn.recv(1024).decode("utf-8", "replace")
                if not request:
                    break
                try:
                    request = json.loads(request)
                except Exception as e:
                    self.log_callback(f"Error receiving command: {e}")
                self.handle_peer_request(conn, addr, request)
            
            except Exception as e:
                if self.peers[addr]["status"] == "offline":
                    break
                self.log_callback(f"Error peer handling {addr}: {e}")
                break

        with self.lock:
            if addr in self.peers:
                del self.peers[addr]
            if conn:
                conn.close()
            if self.is_running:
                self.log_callback(f"Peer {addr} has disconnected.")

    def handle_peer_request(self, conn, addr, request):
        with self.lock:
            if request["header"] == "publish":
                self.log_request_callback(
                    f"Peer {addr}: {request['header'].upper()}\n---\n"
                )
                self.publish(
                    addr,
                    request["payload"]["fname"],
                )
            elif request["header"] == "fetch":
                self.log_request_callback(
                    f"Peer {addr}: {request['header'].upper()}\n---\n"
                )
                self.fetch(conn, addr, request["payload"]["fname"])
            elif request["header"] == "sethost":
                self.log_request_callback(
                    f"Peer {addr}: {request['header'].upper()}\n---\n"
                )
                self.set_hostname(
                    conn, addr, request["payload"]["hostname"]
                )
            elif request["header"] == "discover":

                self.log_request_callback(
                    f"Peer {addr}: {request['header'].upper()}\n---\n"
                )
                self.peer_discover(
                    conn, addr
                )   
            else:
                self.log_request_callback(
                    f"Peer {addr}: Unknown command {request}"
                )

    def handle_command(self, cmd):
        """Process a command received from frontend

        Args:
            cmd (str): The command to process
        """
        with self.lock:
            if self.is_running:
                vals = cmd.split()

                if not cmd:
                    self.log_callback("Server command cannot be blank!")
                elif vals[0] == "discover":
                    self.server_discover(vals[1])
                elif vals[0] == "shutdown":
                    self.stop()
                else:
                    self.log_callback(f"Unknown command: {cmd}")
            else:
                self.log_callback("The tracker has not started yet!")

    def publish(self, addr, file_name):
        """Handle publish request from client

        Args:
            client_address (tuple[str, int]): The client's address
            fname (str): file name published from client to server 
        """
        if addr in self.peers:
            self.peers[addr]["files"].extend(file_name)
            file_names_str = ', '.join([f'"{file}"' for file in file_name])
            self.log_callback(
                f"Files {file_names_str} published by {addr}"
            )
        else:
            self.log_callback(f"Unknown client {addr}")

    def fetch(self, conn, requesting_peer_addr, file_name):
        """Handle fetch request from client

        Args:
            conn (socket): The peer's socket
            requesting_peer_addr (tuple[str, int]): Peer's address
            file_name (str): Requested file name from client
        """
        found_peer: list[tuple[tuple[str, int], Any]] = [
            (addr, data)
            for addr, data in self.peers.items()
            if any(file == file_name for file in data["files"])
            and addr != requesting_peer_addr
        ]

        if len(found_peer) > 0:
            response_data = {
                "header": "fetch",
                "type": 1,
                "payload": {
                    "success": True,
                    "message": f"File '{file_name}' found",
                    "fname": file_name,
                    "available_clients": [
                        {
                            "hostname": data["hostname"],
                            "address": addr,
                        }
                        for (addr, data) in found_peer
                    ],
                },
            }
            response = json.dumps(response_data)
            conn.send(response.encode("utf-8", "replace"))
        else:
            response_data = {
                "header": "fetch",
                "type": 1,
                "payload": {
                    "success": False,
                    "message": f"File '{file_name}' not found",
                    "fname": file_name,
                    "available_clients": [],
                },
            }
            response = json.dumps(response_data)
            conn.send(response.encode("utf-8", "replace"))

    def set_hostname(self, conn, addr, hostname: str):
        """Set the hostname for a peer

        Args:
            conn (socket): The peer's socket
            addr (tuple[str, int]): The peer's address
            hostname (str): The hostname to set
        """
        if addr in self.peers:
            if " " in hostname:
                response = json.dumps(
                    {
                        "header": "sethost",
                        "type": 1,
                        "payload": {
                            "success": False,
                            "message": "Hostname cannot contain spaces",
                            "hostname": hostname,
                            "address": addr,
                        },
                    }
                )
                conn.send(response.encode("utf-8", "replace"))
            else:
                if not any(
                    data["hostname"] == hostname
                    for addr, data in self.peers.items()
                    if addr != addr
                ):
                    self.peers[addr]["hostname"] = hostname
                    response_data = {
                        "header": "sethost",
                        "type": 1,
                        "payload": {
                            "success": True,
                            "message": f"Hostname '{hostname}' "
                            f"set for {addr}",
                            "hostname": hostname,
                            "address": addr,
                        },
                    }
                    response = json.dumps(response_data)
                    self.log_callback(response_data["payload"]["message"])
                    conn.send(response.encode("utf-8", "replace"))
                else:
                    response_data = {
                        "header": "sethost",
                        "type": 1,
                        "payload": {
                            "success": False,
                            "message": f"Hostname '{hostname}' already in use",
                            "hostname": hostname,
                            "address": addr,
                        },
                    }
                    response = json.dumps(response_data)
                    self.log_callback(response_data["payload"]["message"])
                    conn.send(response.encode("utf-8", "replace"))
        else:
            response_data = {
                "header": "sethost",
                "type": 1,
                "payload": {
                    "success": False,
                    "message": f"Unknown client {addr}",
                    "hostname": hostname,
                    "address": addr,
                },
            }
            response = json.dumps(response_data)
            self.log_callback(response_data["payload"]["message"])
            conn.send(response.encode("utf-8", "replace"))

    def server_discover(self, hostname):
        """Discover published files with the given hostname

        Args:
            hostname (str): The hostname to search for
        """
        found_client = None
        for addr, data in self.peers.items():
            if data["hostname"] == hostname:
                found_client = addr
                break
        found_files = [
            data["files"]
            for _, data in self.peers.items()
            if data["hostname"] == hostname
        ]
        
        if found_files:
            found_files = found_files[0]
        else:
            found_files = []

        if len(found_files) > 0:
            response = f"Files on hosts with hostname '{hostname}':\n"
            file_names_str = ', '.join([f'"{file}"' for file in found_files])
            response += file_names_str

        elif found_client:
            response = f"No files on hosts with hostname '{hostname}'\n"
        else:
            response = f"Hostname '{hostname}' not found"

        self.log_callback(response)

    def peer_discover(self, conn, requesting_peer):
        """Handle discovery request from peer

        Args:
            conn (socket): The peer's socket
        """
        peer_addr = conn.getpeername()
        peer_file = self.peers[peer_addr]["files"]
        all_file_names = []
        seen_files = set()

        for peer in self.peers.values():
            for file_name in peer["files"]:
                if file_name not in seen_files and file_name not in peer_file:
                    all_file_names.append(file_name)
                    seen_files.add(file_name)
        response_data = {
            "header": "discover",
            "type": 1,
            "payload": {
                "success": True,
                "message": "Discover list: ",
                "fname": [all_file_names],
            },
        }
        response = json.dumps(response_data)
        conn.send(response.encode("utf-8", "replace"))

    def _shutdown_socket(self):
        try:
            dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dummy_socket.connect((self.host, self.port))
            dummy_socket.close()
        except Exception as e:
            if self.is_running:
                self.log_callback(f"Error stopping the tracker: {e}")

    def _setup_socket(self):
        self.tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tracker_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tracker_socket.bind((self.host, self.port))
        self.tracker_socket.listen(5)
        self.is_running = True
        self.log_callback(f"Tracker is listening on {self.host}:{self.port}")

    def _accept_connections(self):
        while self.is_running:
            try:
                conn, addr = self.tracker_socket.accept()
                threading.Thread(
                    target=self.handle_peer_conn,
                    daemon=True,
                    args=(conn, addr),
                ).start()
            except OSError as e:
                self.log_callback(f"Error accepting connection: {e}")
    

