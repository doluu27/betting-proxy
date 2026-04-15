from flask import Flask, request, jsonify
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

@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "betting-bot-proxy"})

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
            params={
                "apiKey": api_key,
                "regions": "eu",
                "markets": markets,
                "bookmakers": "winamax,betclic,unibet",
                "oddsFormat": "decimal"
            },
            timeout=10
        )
        return jsonify(res.json()), res.status_code
    except requests.exceptions.Timeout:
        return jsonify({"error": "Timeout fetching odds"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
