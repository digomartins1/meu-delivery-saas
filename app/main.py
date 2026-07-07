from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from sqlalchemy import Column, Integer, String, Float
from pydantic import BaseModel

# --- MODELOS ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String) # Em prod, usaríamos hash
    store_id = Column(Integer)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String); price = Column(Float); store_id = Column(Integer)

Base.metadata.create_all(bind=engine)

# --- SCHEMAS ---
class LoginData(BaseModel):
    username: str
    password: str

class ProductCreate(BaseModel):
    name: str; price: float

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- ROTA DE LOGIN ---
@app.post("/api/login")
def login(data: LoginData, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username, User.password == data.password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    return {"status": "ok", "store_id": user.store_id, "username": user.username}

# --- ROTAS DE PRODUTOS ---
@app.get("/api/products/{s_id}")
def list_products(s_id: int, db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.store_id == s_id).all()

@app.post("/api/products/{s_id}")
def create_product(s_id: int, prod: ProductCreate, db: Session = Depends(get_db)):
    db_prod = Product(name=prod.name, price=prod.price, store_id=s_id)
    db.add(db_prod); db.commit()
    return {"status": "ok"}

@app.post("/order/{s_id}")
async def order(s_id: int, data: dict):
    await manager.send(s_id, data)
    return {"ok": True}

# --- WEBSOCKETS ---
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

app.mount("/", StaticFiles(directory="static", html=True), name="static")
