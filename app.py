from flask import Flask, redirect, url_for, session, render_template, request, jsonify
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

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(200), nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipamento.id"), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    shift = db.Column(db.String(20), nullable=False)

    aulas = db.Column(db.JSON, nullable=False)  # lista de aulas
    quantidade = db.Column(db.Integer, nullable=False)

    equipamento = db.relationship("Equipamento")

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
    session['email'] = user.email
    session['nome'] = user.nome

    return redirect(url_for('dashboard'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# -------------------- PÁGINAS --------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect("/login")

    equipamentos = Equipamento.query.all()
    agendamentos = Booking.query.all()

    equipamentos_info = []

    for eq in equipamentos:
        total = eq.quantidade
        
        # Soma todas as quantidades agendadas para esse equipamento
        usados = db.session.query(db.func.sum(Booking.quantidade)) \
            .filter(Booking.equipment_id == eq.id).scalar() or 0

        disponivel = total - usados

        equipamentos_info.append({
            "id": eq.id,
            "nome": eq.nome,
            "total": total,
            "usados": usados,
            "disponivel": disponivel
        })

    return render_template(
        "dashboard.html",
        equipamentos=equipamentos_info,
        agendamentos=agendamentos
    )

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

# -------------------- API: Verificar disponibilidade --------------------
@app.route("/api/disponibilidade/<int:equip_id>")
def api_disponibilidade(equip_id):
    date = request.args.get("data")
    shift = request.args.get("turno")

    equip = Equipamento.query.get_or_404(equip_id)

    # inicia com todo mundo disponível
    disponivel = {i: equip.quantidade for i in range(1, 8)}

    bookings = Booking.query.filter_by(
        equipment_id=equip_id,
        date=date,
        shift=shift
    ).all()

    for b in bookings:
        for aula in b.aulas:
            disponivel[aula] -= b.quantidade
            if disponivel[aula] < 0:
                disponivel[aula] = 0

    return jsonify(disponivel)

# -------------------- AGENDAR --------------------
@app.route("/agendar/<int:id>", methods=["GET", "POST"])
def agendar(id):
    if 'user_id' not in session:
        return redirect(url_for('index'))

    equipamento = Equipamento.query.get_or_404(id)

    if request.method == "POST":
        date = request.form.get('data')
        shift = request.form.get('turno')
        aulas = sorted(map(int, request.form.getlist('aulas')))
        quantidade = int(request.form.get("quantidade"))

        if not aulas:
            return "Selecione ao menos 1 aula", 400

        # calcular disponível
        disponivel = {i: equipamento.quantidade for i in range(1, 8)}

        bookings = Booking.query.filter_by(
            equipment_id=id,
            date=date,
            shift=shift
        ).all()

        for b in bookings:
            for aula in b.aulas:
                disponivel[aula] -= b.quantidade

        # validar disponibilidade
        for aula in aulas:
            if quantidade > disponivel[aula]:
                return f"Erro: Aula {aula} só possui {disponivel[aula]} disponíveis.", 400

        novo = Booking(
            user_email=session['email'],
            equipment_id=id,
            date=date,
            shift=shift,
            aulas=aulas,
            quantidade=quantidade
        )

        db.session.add(novo)
        db.session.commit()

        return redirect(url_for("dashboard"))

    return render_template("agendar.html", equipamento=equipamento)

# -------------------- RUN --------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
