from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from sqlalchemy import Column, Integer, String, Float
from pydantic import BaseModel
import json

# 1. Definição do Banco
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    store_id = Column(Integer)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Float)
    store_id = Column(Integer)
    category = Column(String, default="Lanches")

# Criação das tabelas
Base.metadata.create_all(bind=engine)

# 2. Configuração do App
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 3. ROTAS DE EMERGÊNCIA (ESTÃO NO TOPO PARA FUNCIONAR)
@app.get("/api/db-reset")
def db_reset(db: Session = Depends(get_db)):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return {"msg": "BANCO RESETADO COM SUCESSO"}

@app.get("/api/setup")
def setup(db: Session = Depends(get_db)):
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password="123", store_id=1))
        db.commit()
        return {"msg": "ADMIN CRIADO: user admin / senha 123"}
    return {"msg": "ADMIN JA EXISTE"}

# 4. ROTAS DE PRODUTOS E LOGIN
class LoginData(BaseModel): username: str; password: str
class ProductCreate(BaseModel): name: str; price: float; category: str

@app.post("/api/login")
def login(data: LoginData, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username, User.password == data.password).first()
    if not user: raise HTTPException(status_code=401)
    return {"status": "ok", "store_id": user.store_id, "username": user.username}

@app.get("/api/products/{s_id}")
def list_p(s_id: int, db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.store_id == s_id).all()

@app.post("/api/products/{s_id}")
def add_p(s_id: int, p: ProductCreate, db: Session = Depends(get_db)):
    db.add(Product(name=p.name, price=p.price, store_id=s_id, category=p.category))
    db.commit()
    return {"status": "ok"}

@app.post("/order/{s_id}")
async def order(s_id: int, data: dict):
    await manager.send(s_id, data)
    return {"ok": True}

# 5. WEBSOCKET
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

@app.websocket("/ws/{s_id}")
async def ws_route(ws: WebSocket, s_id: int):
    await manager.connect(ws, s_id)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws, s_id)

# 6. ARQUIVOS ESTÁTICOS (POR ÚLTIMO)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")
