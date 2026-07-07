from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from pydantic import BaseModel
from datetime import datetime, timedelta
import json

# --- MODELOS ---
class User(Base):
    __tablename__ = "users"; id = Column(Integer, primary_key=True)
    username = Column(String, unique=True); password = Column(String); store_id = Column(Integer)

class Product(Base):
    __tablename__ = "products"; id = Column(Integer, primary_key=True)
    name = Column(String); price = Column(Float); store_id = Column(Integer)
    category = Column(String); image_url = Column(String, nullable=True)

class Order(Base):
    __tablename__ = "orders"; id = Column(Integer, primary_key=True)
    cliente = Column(String); itens = Column(Text); total = Column(String)
    status = Column(String, default="Pendente"); store_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- WEBSOCKET ---
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

# -
