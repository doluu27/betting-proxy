from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os
import anthropic

app = Flask(__name__)
CORS(app)

ALLOWED_SPORTS = [
    "tennis_atp", "tennis_wta",
    "soccer_france_ligue_one", "soccer_epl",
    "soccer_uefa_champs_league", "soccer_spain_la_liga",
    "soccer_germany_bundesliga", "soccer_italy_serie_a"
]

# Clé API Football (gratuite sur api-football.com)
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
def send_telegram(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=5
        )
        return True
    except:
        return False

# ─── FORME ÉQUIPE via API-Football ────────────────────────────────────────────
def get_team_form(team_name, league_name):
    """Récupère les 5 derniers résultats d'une équipe."""
    if not API_FOOTBALL_KEY:
        return None
    
    league_ids = {
        "Ligue 1": 61, "Premier League": 39,
        "Champions League": 2, "La Liga": 140,
        "Bundesliga": 78, "Serie A": 135,
    }
    league_id = next((v for k, v in league_ids.items() if k.lower() in league_name.lower()), None)
    if not league_id:
        return None

    try:
        # Chercher l'équipe
        res = requests.get(
            "https://v3.football.api-sports.io/teams",
            headers={"x-apisports-key": API_FOOTBALL_KEY},
            params={"name": team_name, "league": league_id, "season": 2024},
            timeout=5
        )
        teams = res.json().get("response", [])
        if not teams:
            return None
        
        team_id = teams[0]["team"]["id"]
        
        # Récupérer les derniers matchs
        res2 = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": API_FOOTBALL_KEY},
            params={"team": team_id, "league": league_id, "season": 2024, "last": 5},
            timeout=5
        )
        fixtures = res2.json().get("response", [])
        
        form = []
        for f in fixtures:
            home_id = f["teams"]["home"]["id"]
            home_goals = f["goals"]["home"]
            away_goals = f["goals"]["away"]
            if home_goals is None or away_goals is None:
                continue
            if f["teams"]["home"]["id"] == team_id:
                if home_goals > away_goals: form.append("W")
                elif home_goals < away_goals: form.append("L")
                else: form.append("D")
            else:
                if away_goals > home_goals: form.append("W")
                elif away_goals < home_goals: form.append("L")
                else: form.append("D")
        
        wins = form.count("W")
        draws = form.count("D")
        losses = form.count("L")
        form_str = "".join(form[-5:])
        
        return {
            "team": team_name,
            "form": form_str,
            "wins": wins, "draws": draws, "losses": losses,
            "form_score": wins * 3 + draws
        }
    except:
        return None

# ─── ANALYSE IA via Claude ────────────────────────────────────────────────────
def generate_ai_analysis(match, league, selection, odds, edge, confidence,
                          market, home_form, away_form, is_arb, arb_profit):
    """Génère une analyse pronostiqueur via Claude."""
    if not ANTHROPIC_KEY:
        return generate_basic_analysis(selection, odds, edge, confidence, market, is_arb, arb_profit)
    
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        
        home, away = match.split(" vs ") if " vs " in match else (match, "")
        
        form_context = ""
        if home_form:
            form_context += f"Forme de {home} (5 derniers matchs) : {home_form['form']} ({home_form['wins']}V {home_form['draws']}N {home_form['losses']}D)\n"
        if away_form:
            form_context += f"Forme de {away} (5 derniers matchs) : {away_form['form']} ({away_form['wins']}V {away_form['draws']}N {away_form['losses']}D)\n"
        
        prompt = f"""Tu es un pronostiqueur sportif expert. Génère une analyse courte (3-4 phrases max) et percutante pour ce pick.

Match : {match}
Compétition : {league}
Sélection : {selection}
Marché : {market}
Cote : {odds}
Edge value : {edge:.1f}%
Score de confiance : {confidence}/10
{form_context}

{"C'est un arbitrage avec profit garanti de " + str(arb_profit) + "%" if is_arb else ""}

Règles :
- Commence directement par l'argument principal (pas de "ce pick..." ou "nous recommandons...")
- Cite les données de forme si disponibles
- Mentionne l'enjeu du match si pertinent
- Conclus par le niveau de confiance en 1 phrase
- Ton : direct, professionnel, comme un vrai pronostiqueur
- Maximum 4 phrases
- Réponds en français"""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except:
        return generate_basic_analysis(selection, odds, edge, confidence, market, is_arb, arb_profit)

def generate_basic_analysis(selection, odds, edge, confidence, market, is_arb, arb_profit):
    """Analyse de fallback sans IA."""
    if is_arb:
        return f"Divergence de cotes détectée entre bookmakers — profit garanti de +{arb_profit:.1f}% sans risque."
    
    quality = "excellente" if edge > 8 else "bonne" if edge > 4 else "légère"
    conf_txt = "Très haute confiance." if confidence >= 8 else "Bonne confiance." if confidence >= 6 else "Confiance modérée."
    return f"Cote de {odds:.2f} supérieure à la valeur juste avec un edge de +{edge:.1f}% — {quality} opportunité. {conf_txt}"

# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "betting-bot-proxy"})

@app.route("/pronosbot")
def pronosbot():
    return send_from_directory(".", "pronosbot.html")

@app.route("/odds")
def odds():
    api_key = request.args.get("key")
    sport = request.args.get("sport")
    markets = request.args.get("markets", "h2h,totals")
    if not api_key:
        return jsonify({"error": "Missing API key"}), 400
    if not sport or sport not in ALLOWED_SPORTS:
        return jsonify({"error": f"Invalid sport: {sport}"}), 400
    try:
        res = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
            params={"apiKey": api_key, "regions": "eu", "markets": markets,
                    "bookmakers": "winamax,betclic,unibet", "oddsFormat": "decimal"},
            timeout=10
        )
        return jsonify(res.json()), res.status_code
    except requests.exceptions.Timeout:
        return jsonify({"error": "Timeout"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/alert", methods=["POST"])
def alert():
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    tag        = data.get("tag", "🎯 PICK")
    match      = data.get("match", "")
    selection  = data.get("selection", "")
    odds_val   = data.get("odds", 0)
    edge       = data.get("edge", 0)
    confidence = data.get("confidence", 0)
    stake      = data.get("stake", 0)
    bookmaker  = data.get("bookmaker", "")
    league     = data.get("league", "")
    market     = data.get("market", "")
    is_arb     = data.get("is_arb", False)
    arb_legs   = data.get("arb_legs", [])
    arb_profit = data.get("arb_profit", 0)

    # Récupérer la forme des équipes si foot
    home_form, away_form = None, None
    if " vs " in match and "tennis" not in league.lower():
        home, away = match.split(" vs ", 1)
        home_form = get_team_form(home.strip(), league)
        away_form = get_team_form(away.strip(), league)

    # Générer l'analyse
    analysis = generate_ai_analysis(
        match, league, selection, odds_val, edge, confidence,
        market, home_form, away_form, is_arb, arb_profit
    )

    if is_arb and arb_legs:
        o1 = arb_legs[0]["odds"] if len(arb_legs) > 0 else 2.0
        o2 = arb_legs[1]["odds"] if len(arb_legs) > 1 else 2.0
        s1 = round((stake / o1) / (1/o1 + 1/o2))
        s2 = stake - s1
        legs_text = (
            f"  1️⃣ <b>{arb_legs[0]['name']}</b> @ {o1} sur {arb_legs[0].get('bm','?')} → <b>{s1}€</b>\n"
            f"  2️⃣ <b>{arb_legs[1]['name']}</b> @ {o2} sur {arb_legs[1].get('bm','?')} → <b>{s2}€</b>"
        )
        message = (
            f"🔒 <b>ARBITRAGE — Profit garanti</b>\n\n"
            f"🏆 {league} — {match}\n\n"
            f"📌 <b>Comment jouer :</b>\n{legs_text}\n\n"
            f"💰 Profit : <b>+{arb_profit:.2f}%</b> · Mise : <b>{stake}€</b>\n\n"
            f"💡 <i>{analysis}</i>"
        )
    else:
        # Forme dans le message
        form_lines = ""
        if home_form:
            form_lines += f"\n📊 Forme {home_form['team']} : <b>{home_form['form']}</b>"
        if away_form:
            form_lines += f"\n📊 Forme {away_form['team']} : <b>{away_form['form']}</b>"

        message = (
            f"{tag}\n\n"
            f"🏆 {league} — <b>{match}</b>\n\n"
            f"✅ <b>Jouer : {selection}</b>\n"
            f"📋 Marché : {market}\n"
            f"💰 Cote : <b>{odds_val:.2f}</b> sur {bookmaker}\n"
            f"📈 Edge : <b>+{edge:.1f}%</b> · Confiance : <b>{confidence}/10</b>\n"
            f"💵 Mise : <b>{stake}€</b>"
            f"{form_lines}\n\n"
            f"💡 <i>{analysis}</i>"
        )

    sent = send_telegram(message)
    if sent:
        return jsonify({"status": "sent"})
    return jsonify({"error": "Telegram non configuré"}), 500

@app.route("/test-telegram")
def test_telegram():
    sent = send_telegram("✅ <b>PronosBot connecté !</b>\n\n🎯 Prêt à recevoir des picks.")
    if sent:
        return jsonify({"status": "Message envoyé"})
    return jsonify({"error": "TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
