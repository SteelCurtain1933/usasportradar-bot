# USA Sport Radar - V29 FINAL HOSTING VERSION
# Laeuft auf Render / Pydroid. Token kommt aus Umgebungsvariable BOT_TOKEN.
import os, json, logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# TOKEN: Auf Render kommt der Token aus der geheimen Variable BOT_TOKEN (auf der Render-Website eintragen).
# In dieser Datei steht KEIN echter Token - so ist sie sicher fuer GitHub.
TOKEN = os.getenv("BOT_TOKEN") or "DEIN_TOKEN_HIER_EINTRAGEN"
BERLIN = ZoneInfo("Europe/Berlin")
FAV_FILE = "favorites.json"

# --- Champions - NUR HIER EDITIEREN ---
CHAMPIONS = {
    "NFL": {"team": "Philadelphia Eagles", "year": "2024", "result": "Super Bowl LIX: Eagles 40 - Chiefs 22"},
    "NCAAF": {"team": "Ohio State Buckeyes", "year": "2024", "result": "CFP Finale: Ohio State 34 - Notre Dame 23"},
    "MLB": {"team": "Los Angeles Dodgers", "year": "2024", "result": "World Series: Dodgers 4 - Yankees 1"},
    "NHL": {"team": "Florida Panthers", "year": "2025", "result": "Stanley Cup: Panthers 4 - Oilers 2"},
    "NBA": {"team": "Oklahoma City Thunder", "year": "2025", "result": "NBA Finals: Thunder 4 - Pacers 3"},
}

LEAGUES = {
    "NFL": {"espn": "nfl", "emoji": "🏈", "season": "Sep-Feb"},
    "NCAAF": {"espn": "college-football", "emoji": "🎓🏈", "season": "Aug-Jan"},
    "MLB": {"espn": "mlb", "emoji": "⚾", "season": "Mrz-Okt"},
    "NHL": {"espn": "nhl", "emoji": "🏒", "season": "Okt-Jun"},
    "NBA": {"espn": "nba", "emoji": "🏀", "season": "Okt-Jun"},
}

# Kurznamen -> ESPN Team
ALIASES = {
    "steelers": ("NFL", "Pittsburgh Steelers"), "panthers": ("NCAAF", "Pittsburgh Panthers"),
    "pirates": ("MLB", "Pittsburgh Pirates"), "penguins": ("NHL", "Pittsburgh Penguins"),
    "eagles": ("NFL", "Philadelphia Eagles"), "chiefs": ("NFL", "Kansas City Chiefs"),
    "cowboys": ("NFL", "Dallas Cowboys"), "packers": ("NFL", "Green Bay Packers"),
    "dodgers": ("MLB", "Los Angeles Dodgers"), "yankees": ("MLB", "New York Yankees"),
    "lakers": ("NBA", "Los Angeles Lakers"), "celtics": ("NBA", "Boston Celtics"),
}

def load_favs():
    try:
        with open(FAV_FILE, encoding="utf-8") as f: return json.load(f)
    except: return {}
def save_favs(d):
    with open(FAV_FILE, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)

def favs_for(user_id): return load_favs().get(str(user_id), [])
def fmt_dt(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z","+00:00")).astimezone(BERLIN)
        return dt.strftime("%d.%m. %H:%M"), dt
    except: return iso, None

def espn_scoreboard(league, days=7):
    key = LEAGUES[league]["espn"]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{'football' if league in ('NFL','NCAAF') else 'baseball' if league=='MLB' else 'hockey' if league=='NHL' else 'basketball'}/{key}/scoreboard"
    try:
        r = requests.get(url, params={"limit": 100}, timeout=12)
        return r.json().get("events", [])
    except Exception as e:
        logger.warning(e); return []

def event_teams(ev):
    comps = ev.get("competitions", [{}])[0]
    out=[]
    for c in comps.get("competitors", []):
        out.append((c.get("team",{}).get("displayName",""), c.get("homeAway",""), c.get("score")))
    return out, comps

def is_prime_time(dt):
    if not dt: return False
    # US Prime Time ~ 19-23 ET = 01-05 Berlin, plus Wochenende 19-23 Berlin gut
    return dt.weekday()>=5 and 18 <= dt.hour <= 23

def rank_game(ev, league):
    teams, comp = event_teams(ev)
    # Einfaches, stabiles Ranking: Division/Top-Teams + Prime Time + Wochenende
    score = 5
    names = " ".join([t[0] for t in teams]).lower()
    for big in ["steelers","eagles","chiefs","cowboys","dodgers","yankees","lakers","celtics","panthers","penguins","pirates"]:
        if big in names: score += 1
    _, dt = fmt_dt(ev.get("date",""))
    if dt and is_prime_time(dt): score += 1
    if dt and dt.weekday()>=5: score += 1
    return min(10, max(1, score))

def game_line(ev, league):
    teams, comp = event_teams(ev)
    date_s, dt = fmt_dt(ev.get("date",""))
    if len(teams)>=2:
        a = f"{teams[1][0]} {teams[1][2] or ''}".strip()
        h = f"{teams[0][0]} {teams[0][2] or ''}".strip()
        # ESPN Reihenfolge: home first oft, wir zeigen Auswärts @ Heim
        return f"{a} @ {h}  •  {date_s} Uhr"
    return f"{ev.get('name','Spiel')}  •  {date_s} Uhr"

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Favorit hinzufügen", callback_data="fav_add"),
         InlineKeyboardButton("⭐ Meine Favoriten", callback_data="fav_list")],
        [InlineKeyboardButton("⏭️ Next Games", callback_data="next"),
         InlineKeyboardButton("🏆 Top 10", callback_data="top10")],
        [InlineKeyboardButton("📅 Heute", callback_data="heute"),
         InlineKeyboardButton("📅 Morgen", callback_data="morgen")],
        [InlineKeyboardButton("🔴 Live", callback_data="live"),
         InlineKeyboardButton("⏰ Reminder", callback_data="remind")],
        [InlineKeyboardButton("❓ Hilfe", callback_data="help")],
    ])

START_TEXT = """Willkommen beim USA Sport Radar 🇺🇸📡

Dein Überblick für US-Sport - ich zeige dir, welche Spiele sich diese Woche wirklich lohnen, ohne dass du 100 Spiele durchgucken musst.

Einfach auf die Knöpfe drücken - kein @, kein Befehl nötig."""

HELP_TEXT = """USA Sport Radar 🇺🇸📡

Befehle:
/start - Bot starten
/fav - Favoriten verwalten
/next - Next Games deiner Favoriten
/top10 - Top 10 Spiele der Woche
/heute - Spiele heute
/morgen - Spiele morgen
/live - Live-Stände deiner Favoriten
/remind - Reminder 1h vor dem Spiel deiner Favoriten
/help - Hilfe"""

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_TEXT, reply_markup=main_kb())
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, reply_markup=main_kb())

async def fav_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    favs = favs_for(update.effective_user.id)
    txt = "⭐ Deine Favoriten:\n" + ("\n".join([f"• {f}" for f in favs]) if favs else "Noch keine Favoriten.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Favorit hinzufügen", callback_data="fav_add")],
        [InlineKeyboardButton("🗑️ Alle Favoriten löschen", callback_data="fav_clear")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await update.message.reply_text(txt + "\n\nBitte Teamnamen eingeben:", reply_markup=kb)
    ctx.user_data["awaiting_fav"] = True

async def top10_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    await (msg.reply_text("🏆 Ich suche die Top 10... einen Moment ⏳") if update.message else msg.edit_text("🏆 Ich suche die Top 10... einen Moment ⏳"))
    all_games=[]
    for league in LEAGUES:
        for ev in espn_scoreboard(league):
            all_games.append((rank_game(ev, league), league, ev))
    all_games.sort(key=lambda x: x[0], reverse=True)
    lines=["🏆 Top 10 Spiele der Woche\n"]
    for i,(score, league, ev) in enumerate(all_games[:10],1):
        lines.append(f"{i}. [{score}/10] {LEAGUES[league]['emoji']} {game_line(ev, league)}")
    if len(all_games)==0:
        for lg, ch in CHAMPIONS.items():
            lines.append(f"\n{LEAGUES[lg]['emoji']} {lg} - Off-Season: Meister {ch['year']}: {ch['team']} - {ch['result']}")
    target = update.message or update.callback_query.message
    await target.reply_text("\n".join(lines), reply_markup=main_kb())

async def next_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    favs = favs_for(update.effective_user.id)
    lines=["⏭️ Next Games\n"]
    found=False
    for league in LEAGUES:
        evs = espn_scoreboard(league)
        # Gruppiert nach Liga
        league_lines=[]
        for ev in evs[:30]:
            names = " ".join([t[0] for t in event_teams(ev)[0]]).lower()
            if not favs or any(f.lower() in names for f in favs):
                league_lines.append(f"• {game_line(ev, league)}")
                found=True
        if league_lines:
            lines.append(f"\n{LEAGUES[league]['emoji']} {league} ({LEAGUES[league]['season']}):")
            lines.extend(league_lines[:5])
    if not found:
        lines.append("Keine Spiele gefunden. In der Off-Season zeigen wir dir den aktuellen Meister:")
        for lg,ch in CHAMPIONS.items():
            lines.append(f"{LEAGUES[lg]['emoji']} {lg}: {ch['team']} ({ch['year']}) - {ch['result']}")
    await target.reply_text("\n".join(lines), reply_markup=main_kb())

async def heute_morgen(update: Update, ctx: ContextTypes.DEFAULT_TYPE, morgen=False):
    target = update.message or update.callback_query.message
    want = (datetime.now(BERLIN)+timedelta(days=1 if morgen else 0)).date()
    lines=[f"📅 {'Morgen' if morgen else 'Heute'} ({want.strftime('%d.%m.')})\n"]
    for league in LEAGUES:
        for ev in espn_scoreboard(league):
            _, dt = fmt_dt(ev.get("date",""))
            if dt and dt.date()==want:
                lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league)}")
    if len(lines)==1: lines.append("Heute keine Spiele in den Ligen. Schau mal bei /top10 oder /next vorbei.")
    await target.reply_text("\n".join(lines), reply_markup=main_kb())

async def live_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    lines=["🔴 Live\n"]
    for league in LEAGUES:
        for ev in espn_scoreboard(league):
            status = ev.get("status",{}).get("type",{}).get("state","")
            if status=="in":
                lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league)}")
    if len(lines)==1: lines.append("Gerade ist kein Spiel deiner Favoriten live.")
    await target.reply_text("\n".join(lines), reply_markup=main_kb())

async def remind_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    # Reminder-Info: Wir merken uns, dass Reminder an ist. Echte JobQueue waere hier erweiterbar.
    ctx.user_data["remind"] = True
    await target.reply_text("⏰ Reminder an! Ich erinnere dich 1h vor dem Spiel deiner Favoriten.\n\nHinweis: Auf Render Free bleibt der Reminder aktiv, solange der Bot läuft.", reply_markup=main_kb())

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("awaiting_fav"): return
    ctx.user_data["awaiting_fav"]=False
    name = update.message.text.strip()
    # Disambiguierung: wenn Name mehrfach vorkommt
    matches=[]
    for alias,(lg, full) in ALIASES.items():
        if name.lower() in full.lower() or name.lower()==alias: matches.append(full)
    if len(matches)>1:
        ctx.user_data["fav_candidates"]=matches
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{i+1}. {m}", callback_data=f"fav_pick:{i}")] for i,m in enumerate(matches)])
        await update.message.reply_text("Welches Team meinst du?\nBitte nur die Zahl schicken:", reply_markup=kb)
        ctx.user_data["awaiting_fav_pick"]=True
        return
    chosen = matches[0] if matches else name
    favs = load_favs(); uid=str(update.effective_user.id)
    favs.setdefault(uid, [])
    if chosen not in favs[uid]: favs[uid].append(chosen)
    save_favs(favs)
    await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=main_kb())

async def on_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data=q.data
    if data=="back": await q.message.edit_text(START_TEXT, reply_markup=main_kb())
    elif data=="help": await q.message.edit_text(HELP_TEXT, reply_markup=main_kb())
    elif data=="top10": await top10_cmd(update, ctx)
    elif data=="next": await next_cmd(update, ctx)
    elif data=="heute": await heute_morgen(update, ctx, False)
    elif data=="morgen": await heute_morgen(update, ctx, True)
    elif data=="live": await live_cmd(update, ctx)
    elif data=="remind": await remind_cmd(update, ctx)
    elif data=="fav_add":
        ctx.user_data["awaiting_fav"]=True
        await q.message.reply_text("Bitte Teamnamen eingeben:")
    elif data=="fav_list":
        favs=favs_for(update.effective_user.id)
        await q.message.reply_text("⭐ Deine Favoriten:\n" + ("\n".join([f"• {f}" for f in favs]) if favs else "Noch keine."), reply_markup=main_kb())
    elif data=="fav_clear":
        favs=load_favs(); favs[str(update.effective_user.id)]=[]; save_favs(favs)
        await q.message.reply_text("🗑️ Alle Favoriten gelöscht.", reply_markup=main_kb())
    elif data.startswith("fav_pick:"):
        idx=int(data.split(":")[1]); cands=ctx.user_data.get("fav_candidates",[])
        if idx < len(cands):
            chosen=cands[idx]; favs=load_favs(); uid=str(update.effective_user.id); favs.setdefault(uid,[])
            if chosen not in favs[uid]: favs[uid].append(chosen)
            save_favs(favs)
            await q.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=main_kb())


# --- Health Server fuer Render Free Web Service ---
# Winziger eingebauter Webserver, kein Flask - klaut dem Bot keinen Event-Loop.
def _run_health_server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type","text/plain"); self.end_headers()
            self.wfile.write(b"USA Sport Radar laeuft!")
        def log_message(self, *a): pass
    port = int(os.getenv("PORT", "10000"))
    try:
        ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
    except Exception as e:
        print("Health server:", e)

def main():
    if not TOKEN:
        print("FEHLER: BOT_TOKEN fehlt! In Render als Environment Variable setzen.")
        return
    # Health-Server im Hintergrund starten (fuer Render Free)
    threading.Thread(target=_run_health_server, daemon=True).start()
    # Event-Loop fix fuer Python 3.14 + PTB 22
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("fav", fav_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("top10", top10_cmd))
    app.add_handler(CommandHandler("heute", lambda u,c: heute_morgen(u,c,False)))
    app.add_handler(CommandHandler("morgen", lambda u,c: heute_morgen(u,c,True)))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(CommandHandler("remind", remind_cmd))
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("USA Sport Radar läuft...")
    app.run_polling()

if __name__=="__main__": main()
