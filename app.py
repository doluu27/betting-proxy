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

LEAGUE_IDS = {
    "ligue 1": 61, "premier league": 39,
    "champions league": 2, "la liga": 140,
    "bundesliga": 78, "serie a": 135,
    "tennis atp": None, "tennis wta": None,
}

API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "")

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

# ─── API FOOTBALL ─────────────────────────────────────────────────────────────
def get_team_stats(team_name, league_id):
    if not API_FOOTBALL_KEY or not league_id:
        return None
    try:
        # Trouver l'équipe
        r = requests.get(
            "https://v3.football.api-sports.io/teams",
            headers={"x-apisports-key": API_FOOTBALL_KEY},
            params={"name": team_name, "league": league_id, "season": 2024},
            timeout=5
        )
        teams = r.json().get("response", [])
        if not teams:
            return None
        team_id = teams[0]["team"]["id"]

        # 5 derniers matchs
        r2 = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": API_FOOTBALL_KEY},
            params={"team": team_id, "league": league_id, "season": 2024, "last": 5, "status": "FT"},
            timeout=5
        )
        fixtures = r2.json().get("response", [])

        form = []
        goals_scored = []
        goals_conceded = []

        for f in fixtures:
            is_home = f["teams"]["home"]["id"] == team_id
            gh = f["goals"]["home"] or 0
            ga = f["goals"]["away"] or 0
            scored = gh if is_home else ga
            conceded = ga if is_home else gh
            goals_scored.append(scored)
            goals_conceded.append(conceded)
            if scored > conceded: form.append("W")
            elif scored < conceded: form.append("L")
            else: form.append("D")

        wins = form.count("W")
        draws = form.count("D")
        losses = form.count("L")
        pts = wins * 3 + draws
        avg_scored = round(sum(goals_scored) / len(goals_scored), 1) if goals_scored else 0
        avg_conceded = round(sum(goals_conceded) / len(goals_conceded), 1) if goals_conceded else 0

        # Série en cours
        streak = ""
        if form:
            last = form[-1]
            count = 0
            for r in reversed(form):
                if r == last: count += 1
                else: break
            if count >= 2:
                streak = f"{'Serie' if last == 'W' else 'Serie negative' if last == 'L' else 'Serie nul'} de {count}"

        return {
            "team": team_name,
            "form": "".join(form),
            "wins": wins, "draws": draws, "losses": losses,
            "pts": pts,
            "avg_scored": avg_scored,
            "avg_conceded": avg_conceded,
            "streak": streak,
            "last_result": form[-1] if form else None,
        }
    except Exception as e:
        return None

# ─── ANALYSE EXPERTE (règles) ─────────────────────────────────────────────────
def generate_expert_analysis(match, league, selection, odds, edge, confidence,
                               market, home_stats, away_stats, is_arb, arb_profit):
    if is_arb:
        return (
            f"Divergence de cotes détectée entre bookmakers sur ce match. "
            f"En couvrant les deux issues selon la répartition indiquée, "
            f"tu encaisses <b>+{arb_profit:.1f}%</b> de profit net quoi qu'il arrive — zéro risque."
        )

    parts = []
    home = away = ""
    if " vs " in match:
        home, away = match.split(" vs ", 1)

    # 1. Analyse de la forme
    if home_stats and away_stats:
        h, a = home_stats, away_stats
        if h["pts"] > a["pts"] + 3:
            parts.append(f"{home} est en bien meilleure forme ({h['form']}, {h['pts']}pts) face à {away} ({a['form']}, {a['pts']}pts)")
        elif a["pts"] > h["pts"] + 3:
            parts.append(f"{away} domine la forme récente ({a['form']}, {a['pts']}pts) contre {home} en difficulté ({h['form']}, {h['pts']}pts)")
        else:
            parts.append(f"Équilibre en forme récente : {home} {h['form']} vs {away} {a['form']}")

        # Attaque/défense
        if h["avg_scored"] >= 2.0:
            parts.append(f"{home} est prolifique avec {h['avg_scored']} buts/match en moyenne")
        if a["avg_conceded"] >= 2.0:
            parts.append(f"{away} est fragile défensivement ({a['avg_conceded']} buts encaissés/match)")
        if h["avg_scored"] >= 1.5 and a["avg_scored"] >= 1.5:
            parts.append(f"Les deux équipes marquent régulièrement, ce qui favorise les marchés de buts")

        # Séries
        if h["streak"] and "negative" not in h["streak"].lower():
            parts.append(f"{home} est sur une {h['streak'].lower()}")
        if a["streak"] and "negative" not in a["streak"].lower():
            parts.append(f"{away} est sur une {a['streak'].lower()}")

    elif home_stats:
        h = home_stats
        parts.append(f"{home} présente une forme de {h['form']} sur ses 5 derniers matchs ({h['pts']}pts)")
        if h["avg_scored"] >= 1.5:
            parts.append(f"avec une attaque productive à {h['avg_scored']} buts/match")

    elif away_stats:
        a = away_stats
        parts.append(f"{away} affiche {a['form']} sur ses 5 derniers matchs")

    # 2. Analyse du marché
    if market == "Victoire" or market == "h2h":
        if home_stats and away_stats:
            if home_stats["pts"] > away_stats["pts"]:
                parts.append(f"La sélection <b>{selection}</b> s'appuie sur une supériorité de forme claire")
            else:
                parts.append(f"Malgré une forme équilibrée, la cote de <b>{odds:.2f}</b> offre une value réelle")
        else:
            parts.append(f"La cote de <b>{odds:.2f}</b> est supérieure à la valeur juste estimée par le marché")

    elif "buts" in market.lower() or "totals" in market.lower():
        if home_stats and away_stats:
            total_avg = (home_stats["avg_scored"] + away_stats["avg_scored"])
            if "over" in selection.lower() or "plus" in selection.lower():
                if total_avg >= 2.5:
                    parts.append(f"Les deux équipes combinent {total_avg:.1f} buts/match — le Over est cohérent")
                else:
                    parts.append(f"La moyenne de buts ({total_avg:.1f}/match) justifie cette sélection avec l'edge de +{edge:.1f}%")
            else:
                if total_avg <= 2.0:
                    parts.append(f"Avec seulement {total_avg:.1f} buts/match en moyenne, le Under est bien positionné")

    # 3. Edge et confiance
    if edge > 8:
        parts.append(f"Edge exceptionnel de +{edge:.1f}% — une des meilleures opportunités du scan")
    elif edge > 4:
        parts.append(f"Edge solide de +{edge:.1f}% confirmant la value de cette sélection")
    elif edge > 0:
        parts.append(f"Edge positif de +{edge:.1f}% suffisant pour justifier la mise")

    # 4. Confiance finale
    if confidence >= 8:
        parts.append(f"Confiance maximale ({confidence}/10) — pick prioritaire.")
    elif confidence >= 6:
        parts.append(f"Bonne confiance ({confidence}/10) — pick recommandé.")
    else:
        parts.append(f"Confiance modérée ({confidence}/10) — mise réduite conseillée.")

    # Assembler (max 4 phrases)
    sentences = []
    seen = set()
    for p in parts:
        clean = p.strip()
        if clean and clean not in seen:
            seen.add(clean)
            sentences.append(clean)
        if len(sentences) >= 4:
            break

    return ". ".join(sentences) + "."

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

    # Stats équipes
    home_stats = away_stats = None
    league_id = next((v for k, v in LEAGUE_IDS.items() if k in league.lower()), None)
    if " vs " in match and league_id:
        home, away = match.split(" vs ", 1)
        home_stats = get_team_stats(home.strip(), league_id)
        away_stats = get_team_stats(away.strip(), league_id)

    # Analyse
    analysis = generate_expert_analysis(
        match, league, selection, odds_val, edge, confidence,
        market, home_stats, away_stats, is_arb, arb_profit
    )

    if is_arb and len(arb_legs) >= 2:
        o1, o2 = arb_legs[0]["odds"], arb_legs[1]["odds"]
        s1 = round((stake / o1) / (1/o1 + 1/o2))
        s2 = stake - s1
        legs_text = (
            f"  1️⃣ <b>{arb_legs[0]['name']}</b> @ {o1} — {arb_legs[0].get('bm','?')} → <b>{s1}€</b>\n"
            f"  2️⃣ <b>{arb_legs[1]['name']}</b> @ {o2} — {arb_legs[1].get('bm','?')} → <b>{s2}€</b>"
        )
        message = (
            f"🔒 <b>ARBITRAGE — Profit garanti</b>\n\n"
            f"🏆 {league} — {match}\n\n"
            f"📌 <b>Comment jouer :</b>\n{legs_text}\n\n"
            f"💰 Profit : <b>+{arb_profit:.2f}%</b> · Mise totale : <b>{stake}€</b>\n\n"
            f"💡 <i>{analysis}</i>"
        )
    else:
        # Ligne forme
        form_line = ""
        if home_stats and away_stats:
            form_line = f"\n📊 Forme : {home_stats['team']} <b>{home_stats['form']}</b> · {away_stats['team']} <b>{away_stats['form']}</b>"
        elif home_stats:
            form_line = f"\n📊 Forme {home_stats['team']} : <b>{home_stats['form']}</b>"
        elif away_stats:
            form_line = f"\n📊 Forme {away_stats['team']} : <b>{away_stats['form']}</b>"

        message = (
            f"{tag}\n\n"
            f"🏆 {league} — <b>{match}</b>\n\n"
            f"✅ <b>Jouer : {selection}</b>\n"
            f"📋 Marché : {market}\n"
            f"💰 Cote : <b>{odds_val:.2f}</b> sur {bookmaker}\n"
            f"📈 Edge : <b>+{edge:.1f}%</b> · Confiance : <b>{confidence}/10</b>\n"
            f"💵 Mise : <b>{stake}€</b>"
            f"{form_line}\n\n"
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
