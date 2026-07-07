from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from sqlalchemy import Column, Integer, String, Float, Text
from pydantic import BaseModel
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

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- SCHEMAS ---
class ProductCreate(BaseModel): name: str; price: float; category: str; image_url: str = None
class OrderStatusUpdate(BaseModel): status: str

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

# --- ROTAS ---
@app.get("/api/db-reset")
def db_reset(db: Session = Depends(get_db)):
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    return "BANCO ZERADO"

@app.get("/api/setup")
def setup(db: Session = Depends(get_db)):
    if not db.query(User).first():
        db.add(User(username="admin", password="123", store_id=1)); db.commit()
    return "OK"

@app.get("/api/products/{s_id}")
def list_p(s_id: int, db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.store_id == s_id).all()

@app.post("/api/products/{s_id}")
def add_p(s_id: int, p: ProductCreate, db: Session = Depends(get_db)):
    db.add(Product(**p.dict(), store_id=s_id)); db.commit(); return "OK"

@app.get("/api/orders/{s_id}")
def list_orders(s_id: int, db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.store_id == s_id).order_by(Order.id.desc()).all()

@app.post("/order/{s_id}")
async def create_order(s_id: int, data: dict, db: Session = Depends(get_db)):
    new_order = Order(cliente=data['cliente'], itens=data['itens'], total=data['total'], store_id=s_id)
    db.add(new_order); db.commit(); db.refresh(new_order)
    payload = {"id": new_order.id, "cliente": new_order.cliente, "itens": new_order.itens, "total": new_order.total, "status": new_order.status}
    await manager.send(s_id, payload); return "OK"

@app.post("/api/orders/{o_id}/status")
def update_status(o_id: int, data: OrderStatusUpdate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == o_id).first()
    if order: order.status = data.status; db.commit()
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
