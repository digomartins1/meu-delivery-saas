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

# --- WEBSOCKET MANAGER ---
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

# --- ROTAS DE UTILIDADE ---
@app.get("/api/db-reset")
def db_reset(db: Session = Depends(get_db)):
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    return "BANCO ZERADO"

@app.get("/api/setup")
def setup(db: Session = Depends(get_db)):
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password="123", store_id=1)); db.commit()
    return "OK"

@app.post("/api/login")
async def login(data: dict, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == data['username'], User.password == data['password']).first()
    if not u: raise HTTPException(status_code=401)
    return {"store_id": u.store_id, "username": u.username}

# --- ROTAS DE PRODUTOS (CRUD) ---
@app.get("/api/products/{s_id}")
def list_p(s_id: int, db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.store_id == s_id).all()

@app.post("/api/products/{s_id}")
def add_p(s_id: int, data: dict, db: Session = Depends(get_db)):
    db.add(Product(**data, store_id=s_id)); db.commit(); return "OK"

@app.put("/api/products/{p_id}")
def update_p(p_id: int, data: dict, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == p_id).first()
    if p:
        p.name=data['name']; p.price=data['price']; p.category=data['category']; p.image_url=data.get('image_url')
        db.commit()
    return "OK"

@app.delete("/api/products/{p_id}")
def delete_p(p_id: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == p_id).first(); db.delete(p); db.commit(); return "OK"

# --- ROTAS DE PEDIDOS ---
@app.get("/api/orders/{s_id}")
def list_active(s_id: int, db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.store_id == s_id, Order.status != "Concluído").order_by(Order.id.desc()).all()

@app.get("/api/history/{s_id}")
def get_h(s_id: int, db: Session = Depends(get_db)):
    limite = datetime.now() - timedelta(days=15)
    return db.query(Order).filter(Order.store_id == s_id, Order.created_at >= limite).all()

@app.get("/api/order-status/{o_id}")
def get_status(o_id: int, db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == o_id).first()
    return {"status": o.status} if o else HTTPException(status_code=404)

@app.post("/order/{s_id}")
async def create_o(s_id: int, data: dict, db: Session = Depends(get_db)):
    o = Order(cliente=data['cliente'], itens=data['itens'], total=data['total'], store_id=s_id)
    db.add(o); db.commit(); db.refresh(o)
    await manager.send(s_id, {"id": o.id, "status": "update"})
    return {"order_id": o.id}

@app.post("/api/orders/{o_id}/status")
async def up_status(o_id: int, data: dict, db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == o_id).first()
    if o:
        o.status = data['status']; db.commit()
        await manager.send(o.store_id, {"id": o_id, "status": data['status']})
    return "OK"

@app.websocket("/ws/{s_id}")
async def ws_route(ws: WebSocket, s_id: int):
    await manager.connect(ws, s_id)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws, s_id)

app.mount("/static", StaticFiles(directory="static"), name="static")
@app.get("/")
def home():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")
