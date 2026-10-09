from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def connect(self, socket: WebSocket):
        await socket.accept()
        self.clients.add(socket)

    def disconnect(self, socket: WebSocket):
        self.clients.discard(socket)

    async def broadcast(self, message: dict):
        dead=[]
        for socket in tuple(self.clients):
            try:await socket.send_json(message)
            except Exception:dead.append(socket)
        for socket in dead:self.disconnect(socket)


manager=ConnectionManager()
