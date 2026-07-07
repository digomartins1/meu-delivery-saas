from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Manager:
    def __init__(self): self.cons = {}
    async def connect(self, ws, s_id):
        await ws.accept()
        if s_id not in self.cons: self.cons[s_id] = []
        self.cons[s_id].append(ws)
    def disconnect(self, ws, s_id): 
        if s_id in self.cons: self.cons[s_id].remove(ws)
    async def send(self, s_id, data):
        if s_id in self.cons:
            for ws in self.cons[s_id]: await ws.send_json(data)

manager = Manager()

@app.post("/order/{s_id}")
async def order(s_id: int, data: dict):
    await manager.send(s_id, data)
    return {"ok": True}

@app.websocket("/ws/{s_id}")
async def ws_route(ws: WebSocket, s_id: int):
    await manager.connect(ws, s_id)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws, s_id)

app.mount("/", StaticFiles(directory="static", html=True), name="static")
