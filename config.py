import os
from dotenv import load_dotenv

load_dotenv()

# Coloque aqui suas credenciais do Google OAuth (ou configure via variáveis de ambiente)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "SUA_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "SUA_GOOGLE_SECRET")

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Chave secreta do Flask (em produção, gere/guarde em variável de ambiente)
SECRET_KEY = os.urandom(24)

# Banco de dados SQLite local
DATABASE_URI = "sqlite:///database.db"
