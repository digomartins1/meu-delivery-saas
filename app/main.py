from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean
from datetime import datetime, timedelta
import json

# --- MODELOS ---
class User(Base):
    __tablename__ = "users"; id = Column(Integer, primary_key=True)
    username = Column(String, unique=True); password = Column(String); store_id = Column(Integer)
    is_open = Column(Boolean, default=True)

class Product(Base):
    __tablename__ = "products"; id = Column(Integer, primary_key=True)
    name = Column(String); price = Column(Float); store_id = Column(Integer)
    category = Column(String); image_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)

class Customer(Base):
    __tablename__ = "customers"; id = Column(Integer, primary_key=True)
    phone = Column(String, index=True); name = Column(String)
    stamps = Column(Integer, default=0); store_id = Column(Integer)

class Order(Base):
    __tablename__ = "orders"; id = Column(Integer, primary_key=True)
    cliente = Column(String); phone = Column(String, nullable=True)
    itens = Column(Text); total = Column(String)
    status = Column(String, default="Pendente"); store_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)

Base.metadata.create_all(bind=engine)
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

# --- ROTAS DE CONFIGURAÇÃO ---
@app.get("/api/db-reset")
def db_reset(db: Session = Depends(get_db)):
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    return "BANCO ZERADO"

@app.get("/api/setup")
def setup(db: Session = Depends(get_db)):
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password="123", store_id=1, is_open=True))
        db.commit(); return "CRIADO: admin / 123"
    return "OK"

# --- ROTAS DA LOJA (CORRIGIDAS) ---
@app.get("/api/store-status/{s_id}")
def get_st_loja(s_id: int, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.store_id == s_id).first()
    return {"is_open": u.is_open if u else True}

@app.post("/api/store-status/{s_id}")
async def toggle_loja(s_id: int, data: dict, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.store_id == s_id).first()
    if u:
        u.is_open = data['is_open']
        db.commit()
        # Avisa todos os clientes via WebSocket que a loja mudou de status
        await manager.send(s_id, {"type": "store_status", "is_open": u.is_open})
        return {"status": "ok", "is_open": u.is_open}
    raise HTTPException(404)

# --- RESTANTE DAS ROTAS (LOGIN, PRODUTOS, PEDIDOS) ---
@app.post("/api/login")
async def login(data: dict, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == data['username'], User.password == data['password']).first()
    if not u: raise HTTPException(401)
    return {"store_id": u.store_id, "username": u.username}

@app.get("/api/products/{s_id}")
def list_p(s_id: int, db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.store_id == s_id).all()

@app.post("/api/products/{s_id}")
def add_p(s_id: int, data: dict, db: Session = Depends(get_db)):
    db.add(Product(**data, store_id=s_id)); db.commit(); return "OK"

@app.put("/api/products/{p_id}")
def up_p(p_id: int, data: dict, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == p_id).first()
    if p:
        for k,v in data.items(): setattr(p, k, v)
        db.commit(); return "OK"

@app.delete("/api/products/{p_id}")
def del_p(p_id: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == p_id).first(); db.delete(p); db.commit(); return "OK"

@app.get("/api/orders/{s_id}")
def list_o(s_id: int, db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.store_id == s_id, Order.status != "Concluído").order_by(Order.id.desc()).all()

@app.get("/api/history/{s_id}")
def get_h(s_id: int, db: Session = Depends(get_db)):
    lim = datetime.now() - timedelta(days=15)
    return db.query(Order).filter(Order.store_id == s_id, Order.created_at >= lim).all()

@app.get("/api/order-status/{o_id}")
def get_o_st(o_id: int, db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == o_id).first()
    return {"status": o.status, "cliente": o.cliente} if o else HTTPException(404)

@app.get("/api/loyalty/{s_id}/{phone}")
def get_loyalty(s_id: int, phone: str, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.phone == phone, Customer.store_id == s_id).first()
    if not c: return {"stamps": 0};
    return {"stamps": c.stamps}

@app.post("/order/{s_id}")
async def create_o(s_id: int, data: dict, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.store_id == s_id).first()
    if not u or not u.is_open: raise HTTPException(403)
    o = Order(cliente=data['cliente'], phone=data.get('phone'), itens=data['itens'], total=data['total'], store_id=s_id)
    db.add(o); db.commit(); db.refresh(o)
    await manager.send(s_id, {"id": o.id, "cliente": o.cliente, "total": o.total, "itens": o.itens, "status": "Pendente"})
    return {"order_id": o.id}

@app.post("/api/orders/{o_id}/status")
async def up_st(o_id: int, data: dict, db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == o_id).first()
    if o:
        o.status = data['status']
        if o.status == "Concluído" and o.phone:
            c = db.query(Customer).filter(Customer.phone == o.phone, Customer.store_id == o.store_id).first()
            if not c: db.add(Customer(phone=o.phone, name=o.cliente, store_id=o.store_id, stamps=1))
            else: c.stamps += 1
        db.commit()
        await manager.send(o.store_id, {"id": o.id, "status": o.status})
    return "OK"

@app.websocket("/ws/{s_id}")
async def ws_route(ws: WebSocket, s_id: int):
    await manager.connect(ws, s_id)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws, s_id)

app.mount("/static", StaticFiles(directory="static"), name="static")
@app.get("/")
def home(): from fastapi.responses import RedirectResponse; return RedirectResponse("/static/index.html")
