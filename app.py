from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

ALLOWED_SPORTS = [
    "tennis_atp", "tennis_wta",
    "soccer_france_ligue_one", "soccer_epl",
    "soccer_uefa_champs_league", "soccer_spain_la_liga",
    "soccer_germany_bundesliga", "soccer_italy_serie_a"
]

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

    tag       = data.get("tag", "🎯 PICK")
    match     = data.get("match", "")
    selection = data.get("selection", "")
    odds      = data.get("odds", 0)
    edge      = data.get("edge", 0)
    conf      = data.get("confidence", 0)
    stake     = data.get("stake", 0)
    bookmaker = data.get("bookmaker", "")
    league    = data.get("league", "")
    market    = data.get("market", "")
    is_arb    = data.get("is_arb", False)
    arb_legs  = data.get("arb_legs", [])
    arb_profit= data.get("arb_profit", 0)

    edge_str  = f"+{edge:.1f}%" if edge > 0 else f"{edge:.1f}%"
    conf_str  = f"{conf}/10 {'★' * conf}{'☆' * (10 - conf)}"

    if is_arb and arb_legs:
        legs_text = "\n".join([f"  • {l['name']} @ <b>{l['odds']}</b> ({l['bm']})" for l in arb_legs])
        message = (
            f"🔒 <b>ARBITRAGE DÉTECTÉ</b>\n\n"
            f"🏆 <b>{league}</b>\n"
            f"⚽ <b>{match}</b>\n\n"
            f"📌 Sélections :\n{legs_text}\n\n"
            f"💰 Profit garanti : <b>+{arb_profit:.2f}%</b>\n"
            f"🎯 Confiance : <b>10/10</b>\n"
            f"💵 Mise totale : <b>{stake}€</b>"
        )
    else:
        message = (
            f"{tag}\n\n"
            f"🏆 <b>{league}</b>\n"
            f"⚽ <b>{match}</b>\n\n"
            f"✅ Sélection : <b>{selection}</b>\n"
            f"📊 Marché : {market}\n"
            f"💰 Cote : <b>{odds:.2f}</b> ({bookmaker})\n"
            f"📈 Edge : <b>{edge_str}</b>\n"
            f"🎯 Confiance : <b>{conf_str}</b>\n"
            f"💵 Mise : <b>{stake}€</b>"
        )

    sent = send_telegram(message)
    if sent:
        return jsonify({"status": "sent"})
    return jsonify({"error": "Telegram non configuré"}), 500

@app.route("/test-telegram")
def test_telegram():
    sent = send_telegram(
        "✅ <b>PronosBot connecté !</b>\n\n"
        "Les alertes value bet arrivent ici.\n"
        "🎯 Prêt à recevoir des picks."
    )
    if sent:
        return jsonify({"status": "Message envoyé"})
    return jsonify({"error": "TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
