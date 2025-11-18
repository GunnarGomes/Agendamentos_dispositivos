from flask import Flask, redirect, url_for, session, render_template, request
from flask_sqlalchemy import SQLAlchemy
import requests
from oauthlib.oauth2 import WebApplicationClient
import json
import config
import os


app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


db = SQLAlchemy(app)
client = WebApplicationClient(config.GOOGLE_CLIENT_ID)

# -------------------- MODELS --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(100), unique=True)
    nome = db.Column(db.String(200))
    email = db.Column(db.String(200))

class Equipamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200))
    quantidade = db.Column(db.Integer)

class Agendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    equipamento_id = db.Column(db.Integer, db.ForeignKey("equipamento.id"))
    data = db.Column(db.String(20))
    quantidade_reservada = db.Column(db.Integer)

# -------------------- AUTENTICAÇÃO GOOGLE --------------------
def get_google_provider_cfg():
    return requests.get(config.GOOGLE_DISCOVERY_URL).json()

@app.route("/login")
def login():
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)

@app.route("/login/callback")
def callback():
    code = request.args.get("code")
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]

    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code,
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET),
    )

    client.parse_request_body_response(json.dumps(token_response.json()))

    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    data = userinfo_response.json()

    # cria usuário se não existir
    user = User.query.filter_by(email=data["email"]).first()
    if not user:
        user = User(
            google_id=data.get("sub"),
            nome=data.get("name"),
            email=data.get("email")
        )
        db.session.add(user)
        db.session.commit()

    session['user_id'] = user.id
    return redirect(url_for('dashboard'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# -------------------- ROTAS PRINCIPAIS --------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    equipamentos = Equipamento.query.all()
    return render_template("dashboard.html", equipamentos=equipamentos)

@app.route("/equipamentos", methods=["GET", "POST"])
def equipamentos():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if request.method == "POST":
        nome = request.form.get('nome')
        quantidade = int(request.form.get('quantidade', 1))
        novo = Equipamento(nome=nome, quantidade=quantidade)
        db.session.add(novo)
        db.session.commit()

    lista = Equipamento.query.all()
    return render_template("equipamentos.html", equipamentos=lista)

@app.route("/agendar/<int:id>", methods=["GET", "POST"])
def agendar(id):
    if 'user_id' not in session:
        return redirect(url_for('index'))

    equipamento = Equipamento.query.get_or_404(id)

    if request.method == "POST":
        data = request.form.get('data')
        quantidade = int(request.form.get('quantidade', 1))
        user_id = session['user_id']

        # simples: não valida conflitos aqui (podemos adicionar depois)
        novo = Agendamento(
            user_id=user_id,
            equipamento_id=id,
            data=data,
            quantidade_reservada=quantidade
        )
        db.session.add(novo)
        db.session.commit()
        return redirect(url_for('dashboard'))

    return render_template("agendar.html", equipamento=equipamento)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
