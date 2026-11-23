# USA Sport Radar - V251 FINAL - FIX: Nach dem Schliessen eines Live-Spiels ging die naechste Zahl nicht mehr! Flag war One-Shot! Jetzt: Flag bleibt nach dem Tippen an, alle anderen Listen schalten ihn beim Oeffnen aus - so geht jede Zahl, bis eine andere Liste kommt! NFL-Regeln + alle 32 Team-Seiten + alle HOF-Listen + HOF-Detailseiten fuer Steelers + groesste Legenden! Alle Fakten kuratiert & geprueft (keine Live-API fuer Geschichte/HOF) - Detailseiten fuer Rest der Liga folgen in Phase 2!
# V251: Hilfe-Split - Riesen-Fenster weg! Ueberall nur noch Kategorien (8 Themen, neu geschrieben fuer alle neuen Features)! "Ganze Hilfe" = Kategorien-Menue!
# V250: Meine Woche geht nie mehr per Auto-Schliessen weg - sie kriegt den gleichen Schutz wie das Hauptmenue (nur Zurueck / Fenster schliessen / Alle schliessen macht sie zu)!
# V249: Auto-Schliessen FIX - V248 hing nur an _cb_edit, aber die meisten Listen schicken per reply_text direkt -> nie gegriffen! Jetzt zentral im Dispatcher on_cb: Klick aus Hauptmenue -> alte Fenster zu!
# V248: Lade-Anzeigen fuer Detailansicht/Naechste Spiele/Team-News + Auto-Schliessen: Neues Fenster aus Hauptmenue macht alte Fenster zu (An/Aus in Einstellungen, Standard AN)!
# V247 CACHE: Team-News (5 Min), Tabellen (5 Min), Verletzungen (5 Min), Spiel-Details (60 Sek) cachen - Fenster oeffnen sich sofort! Scoreboard-Cache gab es schon seit V114 (30 Sek)!
# Laeuft auf Render / Pydroid. Token kommt aus Umgebungsvariable BOT_TOKEN.
import os, json, logging, re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# V116: CLEAN LOGS! Nur Warnungen + Fehler, kein INFO-Gelaber!
# Vorher: level=INFO -> APScheduler hat alle 60 Sek "Running job..." geloggt, Logs vollgemüllt!
# Jetzt: level=WARNING -> Nur noch: Bot online + echte Fehler! Saubere Render-Logs!
logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)
# APScheduler + Telegram + HTTP leise machen - die labern am meisten!
for _n in ["apscheduler", "apscheduler.executors.default", "apscheduler.scheduler", "apscheduler.jobstores.default", "httpx", "telegram", "telegram.ext", "urllib3", "httpcore"]:
    logging.getLogger(_n).setLevel(logging.WARNING)

# TOKEN: Auf Render kommt der Token aus der geheimen Variable BOT_TOKEN (auf der Render-Website eintragen).
# In dieser Datei steht KEIN echter Token - so ist sie sicher fuer GitHub.
TOKEN = os.getenv("BOT_TOKEN") or "DEIN_TOKEN_HIER_EINTRAGEN"
BERLIN = ZoneInfo("Europe/Berlin")
FAV_FILE = "favorites.json"

# --- Champions - NUR HIER EDITIEREN ---
# V81: Alle Champions auf 2026 aktualisiert! Wir haben November 2026, nicht mehr 2024/2025!
# NFL: Super Bowl LX (Feb 2026, Saison 2025) - Seahawks 29-13 gegen Patriots!
# NCAAF: CFP Finale (Jan 2026, Saison 2025) - Indiana 27-21 gegen Miami, 16-0 ungeschlagen!
# MLB: World Series 2026 - Brewers 4-1 gegen Rays, erster Titel ever!
# NHL: Stanley Cup 2026 - Hurricanes 4-2 gegen Golden Knights!
# NBA: NBA Finals 2026 - Knicks 4-1 gegen Spurs, erster Titel seit 1973!
# V84: Champions-Jahr = Jahr vom FINALE, nicht Saison-Start! Wir sind in Season 2026!
# NFL: Super Bowl LX Feb 2026 -> zeigt 2026, nicht 2025! NCAAF: CFP Finale Jan 2026 -> zeigt 2026!
# Sonst denkt man "2025 = alt"! Alle Champions zeigen jetzt 2026!
CHAMPIONS = {
    "NFL": {"team": "Seattle Seahawks", "year": "2026", "result": "Super Bowl LX: Seahawks 29 - Patriots 13", "note": "2. Titel, erster seit Super Bowl XLVIII (2014)!"},
    "NCAAF": {"team": "Indiana Hoosiers", "year": "2026", "result": "CFP Finale: Indiana 27 - Miami 21 (16-0)", "note": "Erster Titel ever! 16-0 ungeschlagen!"},
    "MLB": {"team": "Milwaukee Brewers", "year": "2026", "result": "World Series: Brewers 4 - Rays 1", "note": "Erster Titel ever!"},
    "NHL": {"team": "Carolina Hurricanes", "year": "2026", "result": "Stanley Cup: Hurricanes 4 - Golden Knights 2", "note": "2. Titel, erster seit 2006!"},
    "NBA": {"team": "New York Knicks", "year": "2026", "result": "NBA Finals: Knicks 4 - Spurs 1", "note": "Erster Titel seit 1973!"},
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


# ===== KOMPLETTE TEAM-DATENBANK - ALLE LIGEN, ALLE TEAMS =====
# Wenn du ein Team hinzufuegen willst, nur hier eintragen. Der Bot baut daraus automatisch:
# - Kurznamen (z.B. "Steelers" -> Pittsburgh Steelers)
# - Stadt-Suche (z.B. "Texas" -> alle Texas-Teams)
# - Mehrdeutigkeits-Check (z.B. "Panthers" -> fragt nach)
TEAMS = {
 "NFL": ["Arizona Cardinals","Atlanta Falcons","Baltimore Ravens","Buffalo Bills","Carolina Panthers","Chicago Bears","Cincinnati Bengals","Cleveland Browns","Dallas Cowboys","Denver Broncos","Detroit Lions","Green Bay Packers","Houston Texans","Indianapolis Colts","Jacksonville Jaguars","Kansas City Chiefs","Las Vegas Raiders","Los Angeles Chargers","Los Angeles Rams","Miami Dolphins","Minnesota Vikings","New England Patriots","New Orleans Saints","New York Giants","New York Jets","Philadelphia Eagles","Pittsburgh Steelers","San Francisco 49ers","Seattle Seahawks","Tampa Bay Buccaneers","Tennessee Titans","Washington Commanders"],
 "NBA": ["Atlanta Hawks","Boston Celtics","Brooklyn Nets","Charlotte Hornets","Chicago Bulls","Cleveland Cavaliers","Dallas Mavericks","Denver Nuggets","Detroit Pistons","Golden State Warriors","Houston Rockets","Indiana Pacers","Los Angeles Clippers","Los Angeles Lakers","Memphis Grizzlies","Miami Heat","Milwaukee Bucks","Minnesota Timberwolves","New Orleans Pelicans","New York Knicks","Oklahoma City Thunder","Orlando Magic","Philadelphia 76ers","Phoenix Suns","Portland Trail Blazers","Sacramento Kings","San Antonio Spurs","Toronto Raptors","Utah Jazz","Washington Wizards"],
 "MLB": ["Arizona Diamondbacks","Atlanta Braves","Baltimore Orioles","Boston Red Sox","Chicago Cubs","Chicago White Sox","Cincinnati Reds","Cleveland Guardians","Colorado Rockies","Detroit Tigers","Houston Astros","Kansas City Royals","Los Angeles Angels","Los Angeles Dodgers","Miami Marlins","Milwaukee Brewers","Minnesota Twins","New York Mets","New York Yankees","Oakland Athletics","Philadelphia Phillies","Pittsburgh Pirates","San Diego Padres","San Francisco Giants","Seattle Mariners","St. Louis Cardinals","Tampa Bay Rays","Texas Rangers","Toronto Blue Jays","Washington Nationals"],
 "NHL": ["Anaheim Ducks","Arizona Coyotes","Boston Bruins","Buffalo Sabres","Calgary Flames","Carolina Hurricanes","Chicago Blackhawks","Colorado Avalanche","Columbus Blue Jackets","Dallas Stars","Detroit Red Wings","Edmonton Oilers","Florida Panthers","Los Angeles Kings","Minnesota Wild","Montreal Canadiens","Nashville Predators","New Jersey Devils","New York Islanders","New York Rangers","Ottawa Senators","Philadelphia Flyers","Pittsburgh Penguins","San Jose Sharks","Seattle Kraken","St. Louis Blues","Tampa Bay Lightning","Toronto Maple Leafs","Utah Mammoth", "Utah Hockey Club","Vancouver Canucks","Vegas Golden Knights","Washington Capitals","Winnipeg Jets"],
  "NCAAF": ["Air Force Falcons","Akron Zips","Alabama Crimson Tide","Appalachian State Mountaineers","Arizona Wildcats","Arizona State Sun Devils","Arkansas Razorbacks","Arkansas State Red Wolves","Army Black Knights","Auburn Tigers","Ball State Cardinals","Baylor Bears","Boise State Broncos","Boston College Eagles","Bowling Green Falcons","Buffalo Bulls","BYU Cougars","California Bears","Central Michigan Chippewas","Charlotte 49ers","Cincinnati Bearcats","Clemson Tigers","Coastal Carolina Chanticleers","Colorado Buffaloes","Colorado State Rams","Delaware Blue Hens","Duke Blue Devils","East Carolina Pirates","Eastern Michigan Eagles","FIU Panthers","Florida Gators","Florida Atlantic Owls","Florida State Seminoles","Fresno State Bulldogs","Georgia Bulldogs","Georgia Southern Eagles","Georgia State Panthers","Georgia Tech Yellow Jackets","Hawaii Rainbow Warriors","Houston Cougars","Illinois Fighting Illini","Indiana Hoosiers","Iowa Hawkeyes","Iowa State Cyclones","Jacksonville State Gamecocks","James Madison Dukes","Kansas Jayhawks","Kansas State Wildcats","Kennesaw State Owls","Kent State Golden Flashes","Kentucky Wildcats","Liberty Flames","Louisiana Ragin' Cajuns","Louisiana Tech Bulldogs","Louisville Cardinals","LSU Tigers","Marshall Thundering Herd","Maryland Terrapins","Massachusetts Minutemen","Memphis Tigers","Miami Hurricanes","Miami (OH) RedHawks","Michigan Wolverines","Michigan State Spartans","Middle Tennessee Blue Raiders","Minnesota Golden Gophers","Mississippi State Bulldogs","Missouri Tigers","Missouri State Bears","Navy Midshipmen","NC State Wolfpack","Nebraska Cornhuskers","Nevada Wolf Pack","New Mexico Lobos","New Mexico State Aggies","North Carolina Tar Heels","North Dakota State Bison","North Texas Mean Green","Northern Illinois Huskies","Northwestern Wildcats","Notre Dame Fighting Irish","Ohio Bobcats","Ohio State Buckeyes","Oklahoma Sooners","Oklahoma State Cowboys","Old Dominion Monarchs","Ole Miss Rebels","Oregon Ducks","Oregon State Beavers","Penn State Nittany Lions","Pittsburgh Panthers","Purdue Boilermakers","Rice Owls","Rutgers Scarlet Knights","Sacramento State Hornets","Sam Houston Bearkats","San Diego State Aztecs","San Jose State Spartans","SMU Mustangs","South Alabama Jaguars","South Carolina Gamecocks","South Florida Bulls","Southern Miss Golden Eagles","Stanford Cardinal","Syracuse Orange","TCU Horned Frogs","Temple Owls","Tennessee Volunteers","Texas A&M Aggies","Texas Longhorns","Texas State Bobcats","Texas Tech Red Raiders","Toledo Rockets","Troy Trojans","Tulane Green Wave","Tulsa Golden Hurricane","UAB Blazers","UCF Knights","UCLA Bruins","UConn Huskies","UL Monroe Warhawks","UNLV Rebels","USC Trojans","Utah State Aggies","Utah Utes","UTEP Miners","UTSA Roadrunners","Vanderbilt Commodores","Virginia Cavaliers","Virginia Tech Hokies","Wake Forest Demon Deacons","Washington Huskies","Washington State Cougars","West Virginia Mountaineers","Western Kentucky Hilltoppers","Western Michigan Broncos","Wisconsin Badgers","Wyoming Cowboys"],
}
# Automatisch: Spitzname -> alle Teams mit diesem Spitznamen (z.B. Panthers -> 3 Teams)
def _build_nickname_map():
    m={}
    for lg, lst in TEAMS.items():
        for full in lst:
            # Spitzname = letztes Wort (Steelers, Panthers...) bzw. letzte 2 Woerter bei "Crimson Tide" etc.
            parts = full.split()
            nick = parts[-1]
            # Sonderfaelle: 2-Wort-Spitznamen
            for two in ["Crimson Tide","Fighting Irish","Golden Knights","Blue Jays","White Sox","Red Sox","Red Wings","Maple Leafs","Blue Jackets","Golden State","Trail Blazers"]:
                if full.endswith(two): nick = two
            key = nick.lower()
            m.setdefault(key, [])
            if f"{full} ({lg})" not in m[key]:
                m[key].append(f"{full} ({lg})")
    return m
NICKNAME_MAP = _build_nickname_map()
# Automatisch: Stadt / Bundesstaat -> Teams (z.B. Texas -> alle Texas-Teams, New York -> alle NY-Teams)
def _find_by_city_or_state(q):
    q=q.lower()
    res=[]
    for lg, lst in TEAMS.items():
        for full in lst:
            fl = full.lower()
            # Stadt = alle Woerter ausser Spitzname
            city_part = " ".join(fl.split()[:-1])
            if q in fl or q in city_part or (q=="texas" and ("texas" in fl or "houston" in fl or "dallas" in fl or "austin" in fl)) or (q=="new york" and "new york" in fl) or (q=="los angeles" and "los angeles" in fl):
                res.append(f"{full} ({lg})")
    # Deduplizieren, Reihenfolge behalten
    seen=set(); out=[]
    for r in res:
        if r not in seen: seen.add(r); out.append(r)
    return out

# --- Favoriten: dauerhaft in Upstash Redis (bleibt auch nach Render-Neustart), sonst lokale Datei als Fallback ---
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
def _redis_get(key):
    if not UPSTASH_URL or not UPSTASH_TOKEN: return None
    try:
        r = requests.get(f"{UPSTASH_URL}/get/{key}", headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}, timeout=8)
        j = r.json()
        v = j.get("result")
        return json.loads(v) if v else None
    except Exception as e:
        logger.warning(f"Redis get fail: {e}"); return None
def _redis_set(key, val):
    if not UPSTASH_URL or not UPSTASH_TOKEN: return False
    try:
        r = requests.post(f"{UPSTASH_URL}/set/{key}", data=json.dumps(val), headers={"Authorization": f"Bearer {UPSTASH_TOKEN}", "Content-Type": "application/json"}, timeout=8)
        return r.status_code==200
    except Exception as e:
        logger.warning(f"Redis set fail: {e}"); return False


def load_favs():
    # Versuche Redis zuerst
    d = _redis_get("favs_all")
    if isinstance(d, dict): return d
    try:
        with open(FAV_FILE, encoding="utf-8") as f: return json.load(f)
    except: return {}
def save_favs(d):
    # In Redis speichern (dauerhaft) + lokal als Backup
    _redis_set("favs_all", d)
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)
    except: pass

def favs_for(user_id): return load_favs().get(str(user_id), [])
# V67: Einstellungen pro User (Reminder-Zeit) - in Redis, wie Favoriten!
def load_settings():
    d = _redis_get("settings_all")
    if isinstance(d, dict): return d
    try:
        with open("settings.json", encoding="utf-8") as f: return json.load(f)
    except: return {}
def save_settings(d):
    _redis_set("settings_all", d)
    try:
        with open("settings.json", "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)
    except: pass
def get_reminder_minutes(user_id):
    # None = aus, sonst 180/120/60/30. Default: 60 (wie bisher 1h)!
    try:
        v = load_settings().get(str(user_id), {}).get("reminder_minutes", 60)
        return v
    except: return 60
def set_reminder_minutes(user_id, minutes):
    s = load_settings(); s.setdefault(str(user_id), {})["reminder_minutes"] = minutes; save_settings(s)
def get_autoclose(uid):
    # V248: Alte Fenster auto-schliessen? Default AN (User-Wunsch)! Aus in Einstellungen!
    try: return bool(load_settings().get(str(uid), {}).get("autoclose", True))
    except: return True
def set_autoclose(uid, val):
    s = load_settings(); s.setdefault(str(uid), {})["autoclose"] = bool(val); save_settings(s)
def fmt_reminder(minutes):
    if minutes is None: return "Aus"
    if minutes>=60: return f"{minutes//60}h vorher" if minutes%60==0 else f"{minutes} Min vorher"
    return f"{minutes} Min vorher"

# --- V203: Nicht-Stoeren-Modus (DND) + Spoiler-Schutz + "Waehrend du weg warst" ---
def get_dnd(uid):
    try: d = (load_settings().get(str(uid), {}) or {}).get("dnd", {}) or {}
    except: d = {}
    try: _s = int(d.get("start", 22))
    except: _s = 22
    try: _e = int(d.get("end", 8))
    except: _e = 8
    return {"on": bool(d.get("on", True)), "start": max(0, min(23, _s)), "end": max(0, min(23, _e)), "spoiler": bool(d.get("spoiler", True))}
def set_dnd(uid, **kw):
    s = load_settings(); s.setdefault(str(uid), {}); s[str(uid)].setdefault("dnd", {})
    for _k, _v in kw.items(): s[str(uid)]["dnd"][_k] = _v
    save_settings(s)
def dnd_active(uid, now=None):
    try:
        d = get_dnd(uid)
        if not d["on"]: return False
        h = (now or datetime.now(BERLIN)).hour
        if d["start"] == d["end"]: return False
        if d["start"] > d["end"]: return h >= d["start"] or h < d["end"]
        return d["start"] <= h < d["end"]
    except: return False
def get_pending(uid):
    try:
        v = _redis_get(f"dnd_pending_{uid}")
        if isinstance(v, list): return v
    except: pass
    return []
def add_pending(uid, eid, lg, name):
    try:
        lst = get_pending(uid)
        if any(str(x.get("eid")) == str(eid) for x in lst): return
        lst.append({"eid": str(eid), "lg": lg, "name": name})
        _redis_set(f"dnd_pending_{uid}", lst)
    except: pass
def clear_pending(uid):
    try: _redis_set(f"dnd_pending_{uid}", [])
    except: pass
async def _live_send_dnd(context, uid, eid, lg, name, text):
    # V203: DND an? -> NIX schicken, nur auf den Zettel schreiben! Sonst normal schicken!
    try:
        if dnd_active(uid):
            add_pending(uid, eid, lg, name)
            return None
    except: pass
    return await _live_send(context, uid, eid, text)
def _dnd_final_text(lg, eid, name):
    # V203: Endergebnis + Torschuetzen aus ESPN-Summary (nix erfunden - was ESPN nicht liefert, steht nicht da!)
    try:
        key = LEAGUES[lg]["espn"]
        sport = 'hockey' if lg=='NHL' else 'basketball' if lg=='NBA' else 'football' if lg in ('NFL','NCAAF') else 'baseball'
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{key}/summary", params={"event": eid}, timeout=10)
        j = r.json()
        comp = ((j.get("header", {}) or {}).get("competitions", [{}]) or [{}])[0]
        comps = comp.get("competitors", []) or []
        state = ((comp.get("status", {}) or {}).get("type", {}) or {}).get("state", "")
        parts = []
        for c in comps:
            tm = ((c.get("team", {}) or {}).get("shortDisplayName") or (c.get("team", {}) or {}).get("displayName", ""))
            parts.append(f"{tm} {c.get('score', '?')}")
        score = " - ".join(parts) if len(parts) == 2 else name
        label = "\U0001f3c1 Endstand" if state == "post" else ("\U0001f534 Live" if state == "in" else "\u23f0")
        scorers = []
        for d in (comp.get("details", []) or []):
            try:
                ath = d.get("athletesInvolved", []) or []
                nm = [a.get("displayName") for a in ath if a.get("displayName")]
                tm2 = ((d.get("team", {}) or {}).get("shortDisplayName") or "")
                if nm: scorers.append(f"{nm[0]} ({tm2})" if tm2 else nm[0])
            except: pass
        txt = f"{label}: {score}"
        if scorers: txt += "\n\u26bd Torschuetzen: " + ", ".join(scorers[-6:])
        return txt
    except: return None
def _dnd_game_state(lg, eid):
    # V222: Frischer Status + Matchup OHNE Score fuer die Spoiler-Ansicht!
    # Gibt (state, matchup) zurueck: state = "in" / "post" / "pre" / "", matchup = "Away @ Home" (ohne Score!)
    # Vorher: Zettel zeigte den gespeicherten Namen (bei One-Off inkl. Score!) + kein Status -> Spoiler-Leak!
    try:
        key = LEAGUES[lg]["espn"]
        sport = 'hockey' if lg=='NHL' else 'basketball' if lg=='NBA' else 'football' if lg in ('NFL','NCAAF') else 'baseball'
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{key}/summary", params={"event": eid}, timeout=10)
        j = r.json()
        comp = ((j.get("header", {}) or {}).get("competitions", [{}]) or [{}])[0]
        comps = comp.get("competitors", []) or []
        state = ((comp.get("status", {}) or {}).get("type", {}) or {}).get("state", "")
        away = ""; home = ""
        for c in comps:
            nm = ((c.get("team", {}) or {}).get("shortDisplayName") or (c.get("team", {}) or {}).get("displayName", ""))
            ha = (c.get("homeAway") or "").lower()
            if ha == "away": away = nm
            elif ha == "home": home = nm
        matchup = f"{away} @ {home}" if away and home else ""
        return state, matchup
    except:
        return "", ""
def _dnd_summary_build(uid, pend, spoiler):
    lines = ["\U0001f305 Waehrend du weg warst\n"]
    rows = []
    if not pend:
        lines.append("Nix verpasst - kein Spiel deiner Favoriten in der Zeit! \U0001f60a")
    elif spoiler:
        lines.append(f"{len(pend)} Spiel(e) lief(en), waehrend Nicht-Stoeren an war - Ergebnisse versteckt, damit du erst Highlights gucken kannst! \U0001f92b\n")
        _any_live = False
        for q in pend:
            # V222: Frisch von ESPN + Matchup OHNE Score! Kein gespeicherter Name mehr (da konnte Score drinstehen)!
            _st, _match = _dnd_game_state(q["lg"], q["eid"])
            _name = _match or q["name"]
            if _st == "in":
                _any_live = True
                lines.append(f"\U0001f92b {_name} • \U0001f534 LIVE")
                rows.append([InlineKeyboardButton(f"\U0001f440 Spielstand: {_name}", callback_data=f"dnd_reveal:{q['eid']}:{q['lg']}")])
            else:
                _status = " • \U0001f3c1 Endstand" if _st == "post" else ""
                lines.append(f"\U0001f92b {_name}{_status}")
                rows.append([InlineKeyboardButton(f"\U0001f440 Ergebnis: {_name}", callback_data=f"dnd_reveal:{q['eid']}:{q['lg']}")])
        rows.append([InlineKeyboardButton("\U0001f440 Alle Spielstände zeigen" if _any_live else "\U0001f440 Alle Ergebnisse zeigen", callback_data="dnd_reveal_all")])
    else:
        lines.append(f"{len(pend)} Spiel(e) lief(en), waehrend Nicht-Stoeren an war:\n")
        for q in pend:
            ft = _dnd_final_text(q["lg"], q["eid"], q["name"])
            lines.append(f"\u2022 {ft or q['name']}")
    rows.append([InlineKeyboardButton("\u2705 Alles gesehen", callback_data="dnd_done")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)

# --- V89: Live-Scores Benachrichtigungen - nur Favoriten, pro Team individuell! ---
def _live_cfg(uid):
    try:
        return load_settings().get(str(uid), {}).get("live", {})
    except: return {}
def get_live_master(uid):
    return bool(_live_cfg(uid).get("master", False))
def set_live_master(uid, val):
    s = load_settings(); s.setdefault(str(uid), {}); s[str(uid)].setdefault("live", {})["master"] = bool(val); save_settings(s)
def get_live_team(uid, team_full):
    d = _live_cfg(uid).get("teams", {}).get(team_full, {})
    return {"score": bool(d.get("score", False)), "period": bool(d.get("period", False)), "final": bool(d.get("final", False)), "crunch": bool(d.get("crunch", False)), "start": bool(d.get("start", False)), "breaking": bool(d.get("breaking", False))}
def set_live_team_toggle(uid, team_full, kind):
    s = load_settings(); s.setdefault(str(uid), {}); s[str(uid)].setdefault("live", {}).setdefault("teams", {}).setdefault(team_full, {})
    cur = bool(s[str(uid)]["live"]["teams"][team_full].get(kind, False))
    s[str(uid)]["live"]["teams"][team_full][kind] = not cur; save_settings(s); return not cur
def live_period_label(league, period):
    try: per = int(period)
    except: return f"Abschnitt {period}"
    if league in ("NFL","NCAAF","NBA"): return f"{per}. Quarter" if per<=4 else "Overtime"
    if league=="NHL": return f"{per}. Drittel" if per<=3 else "Overtime"
    if league=="MLB": return f"{per}. Inning"
    return f"Abschnitt {per}"

# V124: Warme Benachrichtigungen - kurz + Score in Mitte + Custom!
def _short_team(full):
    # "New England Patriots" -> "Patriots", "Detroit Lions" -> "Lions", "Texas Longhorns" -> "Texas"
    # Kurz-Namen: letztes Wort, außer Texas Tech / Ohio State etc - da 2 Wörter!
    try:
        s=(full or "").strip()
        if "Texas Tech" in s: return "Texas Tech"
        if "Ohio State" in s: return "Ohio State"
        if "Notre Dame" in s: return "Notre Dame"
        if "Florida State" in s: return "Florida State"
        if "North Carolina" in s: return "North Carolina"
        parts=s.split()
        return parts[-1] if parts else s
    except: return full or ""
def _score_line_short(ev, lg):
    # V124: "Patriots 3 : 21 Lions" - kurz, Score in Mitte, wie Anzeigetafel!
    try:
        teams,_=event_teams(ev)
        home_t=next((x for x in teams if (x[1] or "").lower()=="home"), None)
        away_t=next((x for x in teams if (x[1] or "").lower()=="away"), None)
        if not home_t or not away_t:
            away_t,home_t=teams[0],teams[1]
        return f"{_short_team(away_t[0])} {away_t[2] or ''} : {home_t[2] or ''} {_short_team(home_t[0])}"
    except:
        try: return _score_only(ev)
        except: return ""
def _has_game_next_week(team_full, lg):
    # V124: Bye Week Check! Hat Team in nächsten 7 Tagen (ab morgen) ein Spiel?
    try:
        from datetime import date as _d
        today=_d.today()
        for off in range(1,8):
            d=today+timedelta(days=off)
            for ev in espn_scoreboard(lg, dates=d.strftime("%Y%m%d")):
                teams,_=event_teams(ev)
                txt=" ".join([x[0] for x in teams]).lower()
                if team_full.lower() in txt: return True
        return False
    except: return True
def _breaking_seen_key(uid,eid,title): return (uid,eid,title)
_BREAKING_SEEN=set()

def game_start_label(league):
    # V118: Spielstart pro Liga anders! Nicht überall "Anpfiff"!
    # NFL/NCAAF: Kickoff, NBA: Tip-Off, NHL: Puck Drop, MLB: First Pitch
    if league in ("NFL","NCAAF"): return "🏈 Kickoff!"
    if league=="NBA": return "🏀 Tip-Off!"
    if league=="NHL": return "🏒 Puck Drop!"
    if league=="MLB": return "⚾ First Pitch!"
    return "🚨 Spielstart!"

def period_word(league):
    # V117: Pro Liga das richtige Wort! Nicht überall "Perioden"!
    # NFL/NCAAF: Quarter, NBA: Viertel, NHL: Drittel, MLB: Inning
    if league in ("NFL","NCAAF"): return "Quarter"
    if league=="NBA": return "Viertel"
    if league=="NHL": return "Drittel"
    if league=="MLB": return "Inning"
    return "Abschnitt"
def period_toggle_label(league):
    # V119: V124: Spielstart + Quarter-Wechsel! Wechsel = Ende + Beginn in 1 Wort! Nicht zu kurz, nicht Roman! Spielstart gehört zum Perioden-Schalter! Wer Quarter-Ende + Beginn will, will auch Spielstart wissen!
    # "Spielstart + Quarter-Ende + Quarter-Beginn" - 1 Schalter, alles drin!
    w = period_word(league)
    return f"Spielstart + {w}-Wechsel"


def fmt_dt(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z","+00:00")).astimezone(BERLIN)
        return dt.strftime("%d.%m. %H:%M"), dt
    except: return iso, None

# V114: Caching - Scoreboard 30 Sek merken, damit alles flüssiger geht!
_SCORE_CACHE = {}

# V247 CACHE: News, Tabellen, Verletzungen, Spiel-Details - Scoreboard (V114) gab es schon, das hier ist neu!
_V247_NEWS_CACHE = {}
_V247_STAND_CACHE = {}
_V247_INJ_CACHE = {}
_V247_SUMMARY_CACHE = {}

def _scoreboard_dates(league):
    # V221: Live-Ansichten duerfen sich NICHT auf ESPNs No-Dates-Standard-Slate verlassen!
    # Der hat Navy @ Memphis (live, 7-7 Q1!) rausgeworfen -> Bot sagte "kein Favorit live".
    # Explizite Berlin-Daten: gestern + heute + morgen, dedup per Event-ID - genau wie der V204-Fix bei Next Games!
    try:
        _seen=set(); _out=[]
        for _off in (-1, 0, 1):
            _d = datetime.now(BERLIN).date() + timedelta(days=_off)
            for _ev in espn_scoreboard(league, dates=_d.strftime("%Y%m%d")):
                _eid=str(_ev.get("id",""))
                if _eid in _seen: continue
                _seen.add(_eid); _out.append(_ev)
        if _out: return _out
    except Exception:
        pass
    # Sicherheitsnetz: falls alle drei Daten leer sind -> alter Abruf (nie schlechter als vorher!)
    try: return espn_scoreboard(league)
    except Exception: return []

def espn_scoreboard(league, days=7, dates=None):
    import time as _time2
    _ck = (league, dates)
    try:
        if _ck in _SCORE_CACHE:
            _ts, _data = _SCORE_CACHE[_ck]
            if (_time2.time() - _ts) < 30:
                return _data
    except: pass
    key = LEAGUES[league]["espn"]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{'football' if league in ('NFL','NCAAF') else 'baseball' if league=='MLB' else 'hockey' if league=='NHL' else 'basketball'}/{key}/scoreboard"
    try:
        params={"limit": 100}
        if dates: params["dates"]=dates
        r = requests.get(url, params=params, timeout=12)
        _evs = r.json().get("events", [])
        try: _SCORE_CACHE[_ck] = (_time2.time(), _evs)
        except: pass
        return _evs
    except Exception as e:
        logger.warning(f"ESPN langsam / Fehler bei {league}: {e}"); return _SCORE_CACHE.get(_ck, (0, []))[1] if _ck in _SCORE_CACHE else []

def _espn_injuries_uncached(league):
    if league == "NCAAF": return []
    _sport = "football" if league in ("NFL",) else "baseball" if league == "MLB" else "hockey" if league == "NHL" else "basketball"
    _key = LEAGUES[league]["espn"]
    try:
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{_sport}/{_key}/injuries", timeout=12)
        j = r.json()
        return j.get("injuries", []) or []
    except Exception:
        return []

def espn_injuries(league):
    # V247 CACHE: Verletzungen aendern sich langsam -> 5 Min cachen! Team-Fenster oeffnen sich sofort!
    import time as _time2
    _ck = ("inj", league)
    try:
        if _ck in _V247_INJ_CACHE:
            _ts, _data = _V247_INJ_CACHE[_ck]
            if (_time2.time() - _ts) < 300:
                return _data
    except: pass
    _res = _espn_injuries_uncached(league)
    try: _V247_INJ_CACHE[_ck] = (_time2.time(), _res)
    except: pass
    return _res
def _team_injuries(league, team_full):
    if league == "NCAAF": return []
    try:
        _tl = (team_full or "").lower()
        out = []
        for _entry in espn_injuries(league):
            _team = ((_entry.get("team", {}) or {}).get("displayName", "") or "").lower()
            if not _team or _tl not in _team and _team not in _tl:
                _nick = _tl.split()[-1] if _tl else ""
                if not _nick or _nick not in _team: continue
            for _inj in (_entry.get("injuries", []) or [])[:6]:
                _ath = _inj.get("athlete", {}) or {}
                _name = _ath.get("displayName", "") or _ath.get("fullName", "") or ""
                _pos = (_ath.get("position", {}) or {}).get("abbreviation", "") or ""
                _status = _inj.get("status", "") or _inj.get("type", "") or ""
                _det = ((_inj.get("details", {}) or {}).get("type", "") or _inj.get("details", "") or "")
                if isinstance(_det, dict): _det = _det.get("type", "") or ""
                _label = _name
                if _pos: _label += f" ({_pos})"
                if _det: _label += f" - {_det}"
                if _status: _label += f" — {_status}"
                out.append(_label)
            if out: break
        return out[:6]
    except Exception:
        return []
NFL_ABBR = {"Arizona Cardinals":"ARI","Atlanta Falcons":"ATL","Baltimore Ravens":"BAL","Buffalo Bills":"BUF","Carolina Panthers":"CAR","Chicago Bears":"CHI","Cincinnati Bengals":"CIN","Cleveland Browns":"CLE","Dallas Cowboys":"DAL","Denver Broncos":"DEN","Detroit Lions":"DET","Green Bay Packers":"GB","Houston Texans":"HOU","Indianapolis Colts":"IND","Jacksonville Jaguars":"JAX","Kansas City Chiefs":"KC","Las Vegas Raiders":"LV","Los Angeles Chargers":"LAC","Los Angeles Rams":"LAR","Miami Dolphins":"MIA","Minnesota Vikings":"MIN","New England Patriots":"NE","New Orleans Saints":"NO","New York Giants":"NYG","New York Jets":"NYJ","Philadelphia Eagles":"PHI","Pittsburgh Steelers":"PIT","San Francisco 49ers":"SF","Seattle Seahawks":"SEA","Tampa Bay Buccaneers":"TB","Tennessee Titans":"TEN","Washington Commanders":"WAS"}
_SLEEPER_CACHE = {"ts": 0, "data": None}
def _sleeper_players():
    # V89: Sleeper NFL-Spielerliste, nur noch 15 Min cachen (war 60 Min)!
    # Damit Harmon-Aktivierung & Co. max. 15 Min spaeter im Bot sind!
    import time as _time
    try:
        if _SLEEPER_CACHE["data"] is not None and (_time.time() - _SLEEPER_CACHE["ts"]) < 900:
            return _SLEEPER_CACHE["data"]
        r = requests.get("https://api.sleeper.app/v1/players/nfl", timeout=20)
        d = r.json()
        _SLEEPER_CACHE["data"] = d; _SLEEPER_CACHE["ts"] = _time.time()
        return d
    except Exception:
        return _SLEEPER_CACHE.get("data") or {}
LEAGUE_SEASON = {"NFL": (9, 2), "NBA": (10, 6), "NHL": (10, 6), "MLB": (3, 10), "NCAAF": (8, 1)}
LEAGUE_NEXT = {"NFL": "Preseason ab August!", "NBA": "Nächste Saison ab Oktober!", "NHL": "Nächste Saison ab Oktober!", "MLB": "Spring Training ab Februar!", "NCAAF": "Nächste Saison ab August!"}
def _league_in_season(league):
    from datetime import date as _d
    _m = _d.today().month; _s, _e = LEAGUE_SEASON.get(league, (1, 12))
    if _s <= _e: return _s <= _m <= _e
    return _m >= _s or _m <= _e
def _sleeper_team_injuries(team_full):
    # V86: (Liste, hat_Daten) - Sleeper liefert injury_status + body_part!
    try:
        _abbr = NFL_ABBR.get((team_full or "").strip(), "")
        if not _abbr: return [], False
        _players = _sleeper_players()
        if not _players: return [], False
        out = []
        for _p in _players.values():
            if not isinstance(_p, dict): continue
            if (_p.get("team") or "") != _abbr: continue
            _st = (_p.get("injury_status") or "").strip()
            if not _st or _st in ("Healthy", "NA", "N/A"): continue
            if _st not in ("Questionable", "Doubtful", "Out", "IR", "PUP", "DNP", "Suspended"): continue
            _name = _p.get("full_name") or ((_p.get("first_name","")+" "+_p.get("last_name","")).strip())
            _pos = _p.get("position") or ""
            _body = _p.get("injury_body_part") or ""
            _label = _name
            if _pos: _label += f" ({_pos})"
            if _body: _label += f" - {_body}"
            _label += f" — {_st}"
            out.append(_label)
        # Sortieren: Out/IR zuerst, dann Doubtful, dann Questionable!
        _order = {"Out": 0, "IR": 0, "PUP": 1, "Doubtful": 2, "Questionable": 3}
        out.sort(key=lambda x: _order.get(x.split(" — ")[-1].strip(), 9))
        return out[:8], True
    except Exception:
        return [], False
def _sleeper_split(team_full):
    try:
        _abbr = NFL_ABBR.get((team_full or "").strip(), "")
        if not _abbr: return [], [], False
        _players = _sleeper_players()
        if not _players: return [], [], False
        _game, _ir, _seen = [], [], set()
        for _p in _players.values():
            if not isinstance(_p, dict): continue
            _tm = (_p.get("team") or "")
            _meta_tm = ((_p.get("metadata") or {}).get("team") or _tm)
            if _tm != _abbr or (_meta_tm and _meta_tm != _abbr): continue
            if _p.get("active") is False: continue
            _st = (_p.get("injury_status") or "").strip()
            if not _st or _st in ("Healthy", "NA", "N/A"): continue
            _name = _p.get("full_name") or ((_p.get("first_name","")+" "+_p.get("last_name","")).strip())
            if not _name or _name in _seen: continue
            _seen.add(_name)
            _pos = _p.get("position") or ""; _body = _p.get("injury_body_part") or ""
            _label = _name
            if _pos: _label += f" ({_pos})"
            if _body: _label += f" - {_body}"
            _label += f" — {_st}"
            if _st in ("Questionable", "Doubtful", "Out"): _game.append(_label)
            elif _st in ("IR", "PUP"): _ir.append(_label)
        _order = {"Out": 0, "Doubtful": 1, "Questionable": 2}
        _game.sort(key=lambda x: _order.get(x.split(" — ")[-1].strip(), 9))
        return _game[:8], _ir, True
    except Exception:
        return [], [], False
def _team_injuries_with_status(league, team_full):
    # V86: (Liste, hat_Daten) - NFL=Sleeper, Rest=ESPN!
    if league == "NCAAF": return [], True
    if league == "NFL":
        _g, _ir, _has = _sleeper_split(team_full)
        return _g, _has
    try:
        _inj = _team_injuries(league, team_full)
        # ESPN: Wenn espn_injuries leer ist, wissen wir nicht ob "keine Verletzten" oder "keine Daten"!
        # Deswegen: ESPN-Rohdaten checken - wenn komplett leer, dann keine Daten!
        _raw = espn_injuries(league)
        if not _raw: return [], False
        return _inj, True
    except Exception:
        return [], False
def event_teams(ev):
    comps = ev.get("competitions", [{}])[0]
    out=[]
    for c in comps.get("competitors", []):
        out.append((c.get("team",{}).get("displayName",""), c.get("homeAway",""), c.get("score")))
    return out, comps

def is_prime_time(dt):
    if not dt: return False
    # US Prime Time: Sunday/Monday/Thursday Night in den USA!
    # Berlin 01:00-05:00 (Mo 02:20 = So 20:20 ET = Sunday Night Football!) ist US Primetime!
    # Berlin 19-23 ist auch gut (US Nachmittag, aber bei uns beste Zeit).
    # Also: Berlin 01-05 Uhr (US Abend) ODER Berlin 19-23 Uhr (DE Abend) = Primetime
    hour = dt.hour
    # US Night Games: Berlin 01-05 Uhr, egal welcher Wochentag (Mo 02:20 = So Night, Di 02:20 = Mo Night, Fr 02:20 = Do Night)
    if 1 <= hour <= 5:
        return True
    # DE Abend: 19-23 Uhr
    if 19 <= hour <= 23:
        return True
    return False

def _team_winpct(competitor):
    # Holt die Siegquote (W-L) aus den ESPN-Records, z.B. "8-2" -> 0.8. Kein Record da = None (kein Raten, kein Erfinden!)
    try:
        recs = competitor.get("records") or []
        summ = None
        for r in recs:
            s = (r.get("summary") or "").strip()
            if (r.get("type") or "") == "total" and "-" in s:
                summ = s; break
        if summ is None:
            for r in recs:
                s = (r.get("summary") or "").strip()
                if "-" in s:
                    summ = s; break
        if not summ: return None
        parts = summ.replace(" ", "").split("-")
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit(): return None
        w, l = int(parts[0]), int(parts[1])
        if w + l == 0: return None
        return w / (w + l)
    except Exception:
        return None

def rank_game(ev, league):
    teams, comp = event_teams(ev)
    # V219: EHRLICHES Ranking! Exakte Vollnamen statt Teilwoerter!
    # Vorher: "Georgia State Panthers" hat "georgia"+"panthers" getriggert und Punkte fuer die Georgia Bulldogs gekriegt!
    # Jetzt: Nur der ECHTE Teamname zaehlt - "georgia bulldogs" == "Georgia Bulldogs", sonst nix!
    names = [x[0].lower().strip() for x in teams]
    famous = {
        # NFL
        "pittsburgh steelers","philadelphia eagles","kansas city chiefs","dallas cowboys",
        "new england patriots","green bay packers","baltimore ravens","san francisco 49ers",
        "buffalo bills","detroit lions","houston texans","cincinnati bengals","cleveland browns",
        "minnesota vikings","seattle seahawks","los angeles rams","miami dolphins","new york jets",
        # MLB
        "los angeles dodgers","new york yankees","pittsburgh pirates",
        # NBA
        "los angeles lakers","boston celtics",
        # NHL
        "florida panthers","pittsburgh penguins",
        # College
        "georgia bulldogs","alabama crimson tide","ohio state buckeyes","michigan wolverines",
        "notre dame fighting irish","texas longhorns","oregon ducks",
    }
    big_count = sum(1 for n in names if n in famous)
    tabelle = 2.0 + min(1.5, big_count*0.7)
    # Rivalitaeten als exakte Vollnamen-Paare! Vorher: "Texas A&M" hat "texas" getriggert und die Texas-Oklahoma-Rivalitaet geklaut!
    # V219 NEU: Texas-Arkansas dazu (SWC-Klassiker seit 1894, jetzt wieder SEC!) + Texas A&M-Oklahoma (echte Big-12-Rivalitaet)!
    rival_pairs = [
        # NFL - AFC North (die härteste Division!)
        ("pittsburgh steelers","baltimore ravens"),("pittsburgh steelers","cincinnati bengals"),("pittsburgh steelers","cleveland browns"),
        ("cincinnati bengals","baltimore ravens"),("cincinnati bengals","cleveland browns"),("baltimore ravens","cleveland browns"),
        # NFL - NFC North / East / West
        ("dallas cowboys","san francisco 49ers"),("dallas cowboys","philadelphia eagles"),("dallas cowboys","new york giants"),("philadelphia eagles","new york giants"),
        # V220: Battle of Pennsylvania! Steelers-Eagles seit 1933, In-State-Rivalitaet!
        ("pittsburgh steelers","philadelphia eagles"),
        ("green bay packers","chicago bears"),("green bay packers","minnesota vikings"),("chicago bears","minnesota vikings"),("detroit lions","green bay packers"),
        ("kansas city chiefs","buffalo bills"),("kansas city chiefs","las vegas raiders"),("kansas city chiefs","denver broncos"),("kansas city chiefs","los angeles chargers"),
        ("new england patriots","buffalo bills"),("new england patriots","new york jets"),("new england patriots","miami dolphins"),
        ("san francisco 49ers","seattle seahawks"),("san francisco 49ers","los angeles rams"),("los angeles rams","seattle seahawks"),
        ("new orleans saints","atlanta falcons"),("new orleans saints","tampa bay buccaneers"),("indianapolis colts","tennessee titans"),("houston texans","indianapolis colts"),
        # NBA / MLB / NHL
        ("los angeles lakers","boston celtics"),("los angeles lakers","los angeles clippers"),("new york knicks","boston celtics"),("chicago bulls","detroit pistons"),
        ("new york yankees","boston red sox"),("los angeles dodgers","san francisco giants"),("los angeles dodgers","san diego padres"),("chicago cubs","st. louis cardinals"),
        ("pittsburgh penguins","washington capitals"),("pittsburgh penguins","philadelphia flyers"),("new york rangers","new york islanders"),("boston bruins","montreal canadiens"),("chicago blackhawks","detroit red wings"),
        # College
        ("michigan wolverines","ohio state buckeyes"),("alabama crimson tide","auburn tigers"),("georgia bulldogs","florida gators"),("texas longhorns","oklahoma sooners"),("notre dame fighting irish","usc trojans"),
        ("texas longhorns","texas a&m aggies"),("army black knights","navy midshipmen"),("florida gators","florida state seminoles"),("ohio state buckeyes","penn state nittany lions"),
        ("texas longhorns","arkansas razorbacks"),("texas a&m aggies","oklahoma sooners"),
    ]
    name_set = set(names)
    rival = 0.5
    for a,b in rival_pairs:
        if a in name_set and b in name_set: rival = 2.8; break
    else:
        if big_count>=2: rival = 1.5
    stars = 1.0 + min(1.8, big_count*0.6)
    _, dt = fmt_dt(ev.get("date",""))
    # Primetime: US Night Game (Berlin 01-05) ist das wichtigste! Sunday Night Football = +1.8!
    # Sender-Check: Wenn NBC/ESPN/Amazon Prime und Nacht, dann sicher Primetime!
    bc_name = broadcast_line(ev).lower()
    is_us_night = dt and 1 <= dt.hour <= 5
    is_night_broadcast = any(x in bc_name for x in ["nbc", "espn", "amazon", "prime video", "netflix"])
    if is_us_night and is_night_broadcast:
        prime = 1.8
    elif dt and is_prime_time(dt):
        prime = 1.2
    else:
        prime = 0.3
    if dt and dt.weekday()>=5: prime += 0.3
    # V219 NEU: Tabellenstand-Bonus aus den echten ESPN-Records (W-L)! Kein Record = kein Bonus (kein Raten)!
    # Beide Teams Winning Record (>= .600) = +1.0, beide um .500 = +0.5 - das Playoff-Rennen zaehlt endlich!
    stand = 0.0
    try:
        comps = comp.get("competitors", []) if isinstance(comp, dict) else []
        pcts = [_team_winpct(c) for c in comps[:2]]
        if len(pcts) >= 2 and pcts[0] is not None and pcts[1] is not None:
            if pcts[0] >= 0.6 and pcts[1] >= 0.6: stand = 1.0
            elif pcts[0] >= 0.5 and pcts[1] >= 0.5: stand = 0.5
    except Exception:
        stand = 0.0
    # V219: Zufalls-Jitter RAUS! Vorher hat ein Zufallswert bei Gleichstand entschieden (Texas = Platz 11 trotz 6,7 = Platz 10)!
    # Jetzt: nur echte Kriterien. Gleichstand loest die Sortierung (Anstosszeit) in top10_league_cmd!
    total = round(min(9.9, max(3.0, tabelle + rival + stars + prime + stand)), 1)
    breakdown = {"tabelle": round(tabelle,1), "rival": round(rival,1), "stars": round(stars,1), "prime": round(prime,1), "stand": round(stand,1), "total": total}
    return total, breakdown

def live_clock(ev, league):
    # Holt die aktuelle Spielzeit aus ESPN, z.B. "17:04 P3" bei NHL, "08:12 Q4" bei NBA/NFL, "Top 7th" bei MLB
    st = ev.get("status", {}) or {}
    clock = st.get("displayClock") or ""
    period = st.get("period")
    detail = st.get("type", {}).get("detail", "") or st.get("type", {}).get("shortDetail", "") or ""
    # ESPN gibt manchmal schon "17:04 - 3rd Period" als detail - dann direkt nehmen
    if detail and ("Period" in detail or "Quarter" in detail or "Inning" in detail):
        # "17:04 - 3rd Period" -> "17:04 P3"
        try:
            c = detail.split(" - ")[0].strip()
            if "3rd Period" in detail: return f"{c} P3"
            if "2nd Period" in detail: return f"{c} P2"
            if "1st Period" in detail: return f"{c} P1"
            if "OT" in detail: return f"{c} OT"
            if "4th Quarter" in detail: return f"{c} Q4"
            if "3rd Quarter" in detail: return f"{c} Q3"
            if "2nd Quarter" in detail: return f"{c} Q2"
            if "1st Quarter" in detail: return f"{c} Q1"
            return detail
        except: pass
    if clock and period:
        if league=="NHL":
            if period==4: return f"{clock} OT"
            if period==5: return f"{clock} SO"
            return f"{clock} P{period}"
        if league=="MLB":
            return detail or clock
        # NFL / NBA / NCAAF
        if period==5: return f"{clock} OT"
        return f"{clock} Q{period}"
    if clock: return clock
    if detail: return detail
    return ""

def _v226_scorer_label(dtype, league):
    # V226: Scorer-Zeile zeigt die ECHTE Score-Art! Nicht mehr "Letzter Touchdown", sondern "Pick Six", "Safety", "Field Goal", "Return TD" usw.!
    try:
        t = (dtype or "").lower()
        if "pick six" in t: return "Pick Six"
        if "interception" in t and "touchdown" in t: return "Pick Six"
        if "fumble" in t and "touchdown" in t: return "Fumble Return TD"
        if "blocked" in t and "touchdown" in t: return "Blocked Kick TD"
        if "punt return" in t or "kickoff return" in t or "kick return" in t or "return touchdown" in t or "return td" in t: return "Return TD"
        if "safety" in t: return "Safety"
        if "field goal" in t: return "Field Goal"
        if "two point" in t or "2-point" in t: return "2-Point Conversion"
        if "extra point" in t: return "Extra Point"
        if "touchdown" in t: return "Touchdown"
        if league == "NHL": return "Tor"
        if "home run" in t: return "Home Run"
        if "triple" in t: return "Triple"
        if "double" in t: return "Double"
        if "single" in t: return "Single"
        if "three point" in t: return "Dreier"
        if "dunk" in t: return "Dunk"
        if "layup" in t: return "Layup"
        if league == "NBA": return "Korb"
        if league == "MLB": return "Score"
        return "Score"
    except: return "Score"

def last_scorer(ev, league):
    # Holt den letzten Torschützen / Scorer aus den ESPN-Spieldetails
    # ESPN legt in competitions[0].details die Scoring-Plays ab, z.B. Goal, Touchdown, Home Run
    try:
        comp = ev.get("competitions", [{}])[0]
        details = comp.get("details", []) or []
        # Nur Scoring-Plays, letztes zuerst
        for d in reversed(details):
            _rt = d.get("type", "") or ""
            dtype = _rt if isinstance(_rt, str) else (_rt.get("text", "") or _rt.get("shortText", "") or "")
            # NHL: Goal, NFL: Touchdown / Field Goal, NBA: 3PT / Dunk / Layup, MLB: Home Run / Single
            if any(k in dtype for k in ["Goal", "Touchdown", "Field Goal", "Home Run", "Three Point", "Two Point", "Dunk", "Layup", "Single", "Double", "Triple", "Safety", "Return Touchdown", "Return TD", "Pick Six"]):  # V226: Safety + Return-TDs sind auch Scoring-Plays!
                # Spielername aus participants / athletes
                scorer = ""
                for p in d.get("participants", []) or d.get("athletesInvolved", []) or []:
                    ath = p.get("athlete", {}) or p
                    if ath.get("displayName"):
                        scorer = ath.get("displayName"); break
                if not scorer:
                    # Fallback: im Text steht oft "Sidney Crosby Goal"
                    txt = d.get("text", "") or dtype
                    scorer = txt
                team = (d.get("team", {}) or {}).get("shortDisplayName", "") or (d.get("team", {}) or {}).get("displayName", "")
                clock = (d.get("clock", {}) or {}).get("displayValue", "") or ""
                period = d.get("period", "")
                # Emoji je nach Liga
                emo = "🏒" if league=="NHL" else "🏈" if league in ("NFL","NCAAF") else "⚾" if league=="MLB" else "🏀"
                label = _v226_scorer_label(dtype, league)  # V226: Echte Score-Art (Pick Six, Safety, Field Goal...) statt "Letzter Touchdown"!
                extra = f" • {clock} P{period}" if league=="NHL" and clock else ""
                if scorer:
                    return f"   {emo} {label}: {scorer} ({team}){extra}" if team else f"   {emo} {label}: {scorer}{extra}"
        return ""
    except Exception:
        return ""


def _espn_summary_details_uncached(ev, league):
    # Holt die Play-by-Play Details aus der ESPN Summary-API, wenn das Scoreboard keine SO-Versuche hat
    # Scoreboard hat oft keine einzelnen SO-Versuche, Summary schon: "Ben Kindel Goal", "Ivar Stenberg Miss"
    try:
        eid = ev.get("id")
        if not eid: return []
        key = LEAGUES[league]["espn"]
        sport = 'hockey' if league=='NHL' else 'basketball' if league in ('NBA',) else 'football' if league in ('NFL','NCAAF') else 'baseball'
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{key}/summary"
        r = requests.get(url, params={"event": eid}, timeout=10)
        try:
            data = r.json()
        except:
            data = {}
        # V105: Wenn Summary keine Details hat, PlayByPlay probieren (da stehen die Scoring-Plays auch drin!)
        if not data.get("details") and not data.get("keyEvents"):
            try:
                _pb_url = url.replace("/summary", "/playbyplay")
                _r2 = requests.get(_pb_url, params={"event": eid}, timeout=10)
                _d2 = _r2.json()
                # PlayByPlay: plays -> scoring plays
                for _p in _d2.get("plays", []) or []:
                    if _p.get("scoringPlay"):
                        dets.append(_p)
                if dets:
                    return dets
            except: pass
        # Details stecken in details oder keyEvents
        dets = []
        for k in ["details", "keyEvents"]:
            if k in data and isinstance(data[k], list): dets.extend(data[k])
        # V104: Summary-Details stecken bei NCAAF/NFL oft in header.competitions[0].details!
        try:
            _hdr = data.get("header", {}) or {}
            for _comp in _hdr.get("competitions", []) or []:
                dets.extend(_comp.get("details", []) or [])
        except: pass
        # Auch in gameInfo / competitors?
        if not dets:
            for comp in data.get("gameInfo", {}).get("competitions", []) if isinstance(data.get("gameInfo"), dict) else []:
                dets.extend(comp.get("details", []) or [])
        return dets
    except Exception:
        return []

def espn_summary_details(ev, league):
    # V247 CACHE: Spiel-Details 60 Sek cachen! Detailansicht beim 2. Oeffnen sofort da, Live bleibt frisch (60 Sek, wie Scoreboard 30 Sek)!
    import time as _time2
    try: _eid = ev.get("id") if isinstance(ev, dict) else None
    except: _eid = None
    _ck = ("sum", _eid, league)
    try:
        if _eid and _ck in _V247_SUMMARY_CACHE:
            _ts, _data = _V247_SUMMARY_CACHE[_ck]
            if (_time2.time() - _ts) < 60:
                return _data
    except: pass
    _res = _espn_summary_details_uncached(ev, league)
    try:
        if _eid: _V247_SUMMARY_CACHE[_ck] = (_time2.time(), _res)
    except: pass
    return _res
def shootout_lines(ev, league):
    # Nur NHL Shootout: zeigt jeden Versuch mit ✅ / ❌, wie bei ESPN: "Ben Kindel ✅, Ivar Stenberg ❌"
    if league!="NHL": return []
    try:
        comp = ev.get("competitions", [{}])[0]
        details = list(comp.get("details", []) or [])
        # Wenn im Scoreboard keine SO-Details, Summary nachladen
        has_so = any((d.get("period")==5 or "Shootout" in str(d.get("type",{})) or "SO" in str(d.get("type",{}))) for d in details)
        if not has_so:
            details = espn_summary_details(ev, league) or details
        so_plays=[]
        for d in details:
            per = d.get("period")
            dtype = (d.get("type",{}) or {}).get("text","") or (d.get("type",{}) or {}).get("shortText","") or d.get("text","") or ""
            txt_all = (dtype + " " + (d.get("text","") or "")).lower()
            # Shootout-Versuche: period 5 oder "shootout" im Text oder "SO" als Perioden-Label
            is_so = (per==5 or "shootout" in txt_all or d.get("periodType")=="shootout" or "so -" in txt_all)
            if not is_so: continue
            # Spielername
            scorer=""
            for p in d.get("participants", []) or d.get("athletesInvolved", []) or []:
                ath = p.get("athlete",{}) or p
                if ath.get("displayName"): scorer=ath.get("displayName"); break
            if not scorer:
                # Text wie "Ben Kindel Goal Wrist Shot" -> Name ist alles vor "Goal"/"Shot"/"Miss"
                raw = d.get("text","") or dtype
                for cut in [" Goal", " Miss", " Shot", " Save"]:
                    if cut in raw: scorer=raw.split(cut)[0].strip(); break
                if not scorer: scorer=raw
            team = (d.get("team",{}) or {}).get("shortDisplayName","") or (d.get("team",{}) or {}).get("displayName","") or ""
            is_goal = ("goal" in txt_all and "above" not in txt_all and "wide" not in txt_all and "miss" not in txt_all and "save" not in txt_all and "crossbar" not in txt_all and "post" not in txt_all)
            mark = "✅" if is_goal else "❌"
            so_plays.append(f"{scorer} {mark} ({team})" if team else f"{scorer} {mark}")
        if not so_plays: return []
        # Shootout-Stand aus ✅ zählen: z.B. PIT 1-0 SJS
        out=[]
        out.append(f"   🥅 Shootout:")
        for p in so_plays:
            out.append(f"      {p}")
        return out
    except Exception:
        return []

def venue_line(ev):
    # Holt Stadion + Ort aus ESPN: z.B. "🏟️ PPG Paints Arena, Pittsburgh" oder "🏟️ Acrisure Stadium, Pittsburgh"
    try:
        comp = ev.get("competitions", [{}])[0]
        v = comp.get("venue", {}) or {}
        name = v.get("fullName", "") or v.get("name", "")
        addr = v.get("address", {}) or {}
        city = addr.get("city", "") or ""
        state = addr.get("state", "") or ""
        if name and city:
            return f"   🏟️ {name}, {city}" + (f", {state}" if state else "")
        if name: return f"   🏟️ {name}"
        if city: return f"   🏟️ {city}"
        return ""
    except Exception:
        return ""
def is_neutral_or_international(ev, home_name):
    # NUR echtes International: Stadion liegt außerhalb der USA!
    # Stadt-Vergleich geht NICHT: Giants spielen in East Rutherford (nicht NYC), Pacers in Indianapolis (nicht "Indiana"),
    # Vegas Golden Knights -> "Vegas Golden" vs "Las Vegas" - alles normale US-Spiele, kein International!
    # Deswegen: Nur wenn Land != USA oder Stadt in [London, Berlin, München, Madrid, Dublin, Sao Paulo, Mexico City]!
    try:
        comp = ev.get("competitions", [{}])[0]
        v = comp.get("venue", {}) or {}
        addr = v.get("address", {}) or {}
        vcity = (addr.get("city","") or "").strip()
        vcity_low = vcity.lower()
        country = (addr.get("country","") or v.get("country","") or "").strip().lower()
        # 1) Land-Check: Wenn ESPN ein Land liefert und es nicht USA ist -> International
        if country and country not in ("us", "usa", "united states", "united states of america"):
            # Aber Kanada ist bei NHL/NBA normal (Toronto, Montreal, Vancouver) - kein International!
            if country not in ("ca", "canada"):
                vname = v.get("fullName","") or v.get("name","")
                label = f"📍 {vname}, {vcity}" if vname and vcity else f"📍 {vcity or vname}"
                return True, label
            return False, ""
        # 2) Stadt-Check: Nur echte International-Städte, egal was im Teamnamen steht
        intl_cities = ["london", "berlin", "munich", "münchen", "madrid", "dublin", "sao paulo", "são paulo", "mexico city", "mexiko", "paris", "tokyo", "rio de janeiro"]
        if vcity_low in intl_cities:
            vname = v.get("fullName","") or v.get("name","")
            label = f"📍 {vname}, {vcity}" if vname and vcity else f"📍 {vcity or vname}"
            return True, label
        # 3) Stadion-Name-Check: Wembley, Tottenham, Allianz Arena, Aviva, Bernabeu etc. = International
        vname_low = (v.get("fullName","") or v.get("name","") or "").lower()
        intl_stadiums = ["wembley", "tottenham", "allianz arena", "olympiastadion berlin", "aviva", "croke park", "bernabeu", "santiago bernabeu", "azteca", "corinthians", "allianz parque", "maracana"]
        if any(s in vname_low for s in intl_stadiums):
            vname = v.get("fullName","") or v.get("name","")
            label = f"📍 {vname}, {vcity}" if vname and vcity else f"📍 {vcity or vname}"
            return True, label
        return False, ""
    except Exception:
        return False, ""
def broadcast_line(ev):
    # Holt den Original-Sender aus ESPN: z.B. "CBS", "FOX", "SportsNet Pittsburgh", "ESPN+", "TNT"
    try:
        comp = ev.get("competitions", [{}])[0]
        bcs = comp.get("broadcasts", []) or []
        if not bcs: return ""
        for b in bcs:
            names = b.get("names") or []
            name = names[0] if names else b.get("name","") or b.get("shortName","")
            if not name and isinstance(b.get("media"), dict):
                name = b.get("media",{}).get("shortName","")
            if name and str(name).strip():
                return str(name).strip()
        return ""
    except Exception:
        return ""
def game_line(ev, league, show_venue=False, compact_home_first=True, show_broadcast=False):
    teams, comp = event_teams(ev)
    date_s, dt = fmt_dt(ev.get("date",""))
    state = ev.get("status",{}).get("type",{}).get("state","")
    # Status-Label: Live / Final / Anpfiff - damit fertige Spiele nicht mehr als Live aussehen
    if state=="in":
        clock = live_clock(ev, league)
        label = f"🔴 LIVE • {clock}" if clock else "🔴 LIVE"
    elif state=="post":
        # NHL/NBA/NFL: War es OT oder SO? z.B. "✅ Final/SO" wie bei ESPN "FINAL/SO"
        per = ev.get("status",{}).get("period") or 0
        det = (ev.get("status",{}).get("type",{}) or {}).get("detail","") or ""
        if league=="NHL":
            if per==5 or "/SO" in det or "Shootout" in det: label = "✅ Final/SO"
            elif per==4 or "/OT" in det or "Overtime" in det: label = "✅ Final/OT"
            else: label = "✅ Final"
        elif league in ("NBA","NFL","NCAAF"):
            if per and per>4 or "/OT" in det or "Overtime" in det: label = "✅ Final/OT"
            else: label = "✅ Final"
        elif league=="MLB":
            if per and per>9: label = f"✅ Final/{per} Inn."
            else: label = "✅ Final"
        else: label = "✅ Final"
        # V189 LIVE-BEDEUTUNG: Nach Abpfiff steht direkt dabei, was der Sieg bedeutet! (CFP ist 15 Min gecacht, also schnell!)
        if league=="NCAAF":
            try:
                _scores=_live_scores_of(ev)
                if len(_scores)>=2:
                    _winner=max(_scores, key=lambda _k: _scores[_k])
                    _loser=min(_scores, key=lambda _k: _scores[_k])
                    _cfp_rows,_=_espn_cfp_top25()
                    _rank_map={_d.lower():_i for _i,(_d,_s,_r) in enumerate(_cfp_rows,1)}
                    _w_rank=None; _l_rank=None
                    for _cd,_ri in _rank_map.items():
                        if _is_fav_team(_cd, [_winner], "NCAAF"): _w_rank=_ri
                        if _is_fav_team(_cd, [_loser], "NCAAF"): _l_rank=_ri
                    _w_short=_cfp_short(_winner, "")
                    if _w_rank and _w_rank<=12: label+=f" • {_w_short} bleibt in Top 12!"
                    elif _w_rank and _w_rank<=25: label+=f" • {_w_short} noch im Rennen!"
                    elif _l_rank and _l_rank<=12: label+=f" • {_w_short} schmeißt #{_l_rank} raus?!"
            except: pass
    else:
        label = f"⏰ {date_s} Uhr"
    if len(teams)>=2:
        # V69-FIX: Heim/Gast via homeAway-Feld, nicht via ESPN-Reihenfolge!
        home_t = next((x for x in teams if (x[1] or "").lower()=="home"), None)
        away_t = next((x for x in teams if (x[1] or "").lower()=="away"), None)
        if home_t is None or away_t is None:
            away_t, home_t = teams[0], teams[1]
        # V70-FIX: Bei kommenden Spielen KEIN Score! ESPN liefert vor Anpfiff "0" -> "Penguins 0 @ Senators 0" verwirrt!
        # Nur bei Live (in) und Final (post) Score zeigen, sonst nur Team-Namen!
        if state in ("in", "post"):
            a = f"{away_t[0]} {away_t[2] or '' }".strip()
            h = f"{home_t[0]} {home_t[2] or '' }".strip()
        else:
            a = away_t[0].strip()
            h = home_t[0].strip()
        is_intl, intl_label = is_neutral_or_international(ev, home_t[0])
        # V115: Kompakt! 1 Zeile pro Spiel, keine 3 Zeilen mehr!
        # Kurz-Namen aus ESPN shortDisplayName (Patriots statt New England Patriots)!
        def _short(tm_full, idx_fallback):
            try:
                _comp2 = ev.get("competitions", [{}])[0]
                _cs = _comp2.get("competitors", [])
                for _c in _cs:
                    if (_c.get("team", {}) or {}).get("displayName","") == tm_full:
                        return (_c.get("team", {}) or {}).get("shortDisplayName","") or tm_full
                return tm_full
            except: return tm_full
        bc = broadcast_line(ev)
        bc_suf = f" • 📺 {bc}" if (show_broadcast and bc) else ""
        if state=="post":
            ven = f"\n   {intl_label}" if is_intl else ""
            return f"{a} @ {h}  •  {label} • {date_s}{ven}{bc_suf}"
        if state=="in":
            ven = f"\n   {intl_label}" if is_intl else ""
            return f"{a} @ {h}  •  {label}{ven}{bc_suf}"
        # Kommend: 1 Zeile! z.B. "Patriots @ Lions • 15:30 • Fox • München"
        _a_short = _short(away_t[0], 0); _h_short = _short(home_t[0], 1)
        _time_only = date_s.split(" ")[-1] if " " in date_s else date_s  # "15.11. 15:30" -> "15:30"
        # Datum nur wenn nicht heute? game_line kennt want nicht, also Uhrzeit + Datum kurz: "15.11. 15:30"
        _ven_short = " • München" if is_intl and "Munich" in (intl_label or "") else ""
        return f"{_a_short} @ {_h_short} • ⏰ {date_s} Uhr{bc_suf}{_ven_short}"
    return f"{ev.get('name','Spiel')}  •  {label}"

def _live_ticker_line(ev, league):
    # V244: Scoreboard-Ticker! "MIA 9 – 20 BUF • 5:58 Q3" - nur Kuerzel + Stand + Spielzeit!
    try:
        _comps = ev.get("competitions", [{}])[0]
        _cs = _comps.get("competitors", []) or []
        _home = next((c for c in _cs if (c.get("homeAway") or "").lower() == "home"), None)
        _away = next((c for c in _cs if (c.get("homeAway") or "").lower() == "away"), None)
        if _home is None or _away is None:
            if len(_cs) >= 2: _away, _home = _cs[0], _cs[1]
            else: return ""
        def _ab(c):
            _t = c.get("team", {}) or {}
            return _t.get("abbreviation") or _t.get("shortDisplayName") or _t.get("displayName") or "?"
        _a_ab = _ab(_away); _h_ab = _ab(_home)
        _a_sc = _away.get("score", ""); _h_sc = _home.get("score", "")
        _clock = live_clock(ev, league)
        if _clock:
            return f"{_a_ab} {_a_sc} – {_h_sc} {_h_ab} • {_clock}"
        return f"{_a_ab} {_a_sc} – {_h_sc} {_h_ab}"
    except Exception:
        return ""

def main_kb(with_close=True, uid=None):
    # V94: Hauptmenue = KEIN Fenster-schliessen (sonst muss man jedes Mal wieder /start tippen)! Ueberall sonst = mit Fenster-schliessen!
    # V134: 5 Reihen, logisch! Oben Inhalt, unten System! Einstellungen + Hilfe ganz unten!
    rows = [
        [InlineKeyboardButton("⭐ Meine Favoriten", callback_data="fav_list")],
        [InlineKeyboardButton("📅 Meine Woche", callback_data="myweek")],
        [InlineKeyboardButton("⏭️ Next Games", callback_data="next"),
         InlineKeyboardButton("🏆 Top 10", callback_data="top10")],
        [InlineKeyboardButton("🔴 Live", callback_data="live"),
         InlineKeyboardButton("📊 Tabellen", callback_data="tables")],
        [InlineKeyboardButton("📰 News", callback_data="news"),
         InlineKeyboardButton("✅ Ergebnisse", callback_data="results")],
        [InlineKeyboardButton("⚙️ Einstellungen", callback_data="settings"),
         InlineKeyboardButton("❓ Hilfe", callback_data="help")],
    ]
    # V242: Nerd-Modus - Lexikon: Regeln, Teams & Hall of Famers!
    rows.append([InlineKeyboardButton("🧠 Nerd-Modus", callback_data="nerd")])
    # V214: NFL Draft-Vorschau - NUR vor dem Draft! Nach dem Draft (01.05.2027) verschwindet der Knopf von allein!
    try:
        from datetime import date as _date214
        _t214 = _date214.today()
        if _t214 <= _date214(2027, 5, 1):
            _days214 = (_date214(2027, 4, 29) - _t214).days
            if _days214 <= 28:
                _lbl214 = "🏆 NFL Draft 2027"
            else:
                _lbl214 = f"🏆 NFL Draft-Vorschau ({_days214} Tage)"
            rows.append([InlineKeyboardButton(_lbl214, callback_data="draft_preview")])
    except: pass
    # V203: 'Waehrend du weg warst' NUR wenn was auf dem Zettel steht! Zettel leer = kein Knopf = Hauptmenue bleibt sauber!
    try: _pend203 = get_pending(uid) if uid else []
    except: _pend203 = []
    if _pend203: rows.append([InlineKeyboardButton(f"🌅 Während du weg warst ({len(_pend203)})", callback_data="dnd_summary")])
    # V167: Grossputz-Button NUR im Hauptmenue! Alle anderen Fenster haben nur Zurueck + Einzeln-Schliessen (V165)!
    rows.append([InlineKeyboardButton("🧹 Alle Fenster schließen", callback_data="close_all")])
    if with_close:
        rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
    return InlineKeyboardMarkup(rows)

def small_kb():
    # V167: Start-Menue NUR noch bei /start! Ueberall sonst nur Zurueck + Fenster schliessen!
    # Zurueck = Fenster loeschen, Hauptmenue nach /start bleibt oben (bestehender 'back'-Handler)!
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="back")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])

START_TEXT = """Willkommen beim USA Sport Radar 🇺🇸📡

Dein US-Sport Guide — nie wieder ein Spiel verpassen!
NFL, NCAAF, NBA, NHL, MLB — alles an einem Ort!

⭐ Favoriten anlegen, 🔴 Live dabei sein, 📰 News checken!
❓ Hilfe = alle Befehle + Infos, falls du mal nicht weiter weißt!

Einfach auf die Knöpfe drücken — los geht's!"""

HELP_TEXT = """❓ Hilfe - So liest du den Bot

**Gast @ Heim**
Erstes Team = Auswärtsteam, zweites Team = Heimteam!
Z.B. Vikings @ Packers = Vikings spielt bei den Packers in Green Bay!

**⭐ = Dein Team**
Das ist einer deiner Favoriten!

**📺 = US-Sender**
Auf dem Sender läuft das Spiel in den USA (CBS / FOX / ESPN ...).
Deutsche Sender zeigen wir nicht, weil die Rechte sich ständig ändern!

**📍 / 🏟️ = Stadion / Ort**
Wo das Spiel stattfindet! Im Top 10 Detail steht das Stadion immer dabei!

**🔴 LIVE / ✅ Final / ⏰ Uhrzeit**
Live = läuft gerade, Final = fertig, Uhrzeit = Anpfiff!

**🏆 Top 10**
Tippe eine Zahl (1-10) in den Chat für Rating + Warum so bewertet?
In der Übersicht steht kein Rating - nur Platz 1-10!
Das genaue Rating (z.B. ⭐ 9,9/10) steht nur im Detail!

**⭐ 9,9/10 = Rating**
So gut ist das Spiel bewertet - nur im Detail!

**📊 Tabellen - NHL**
W-L-OTL = Siege - Niederlagen - Overtime-Niederlagen
OT1 = Letztes Spiel in Overtime verloren (1 Punkt!)
Sieg = 2 Punkte, Overtime-Niederlage = 1 Punkt, Niederlage = 0 Punkte
Bei NHL-Tabellen steht unten immer eine kurze Legende + ein Button für die ausführliche Erklärung!

**🏥 Verletzungen - Wichtig!**
Daten von Sleeper (NFL) / ESPN (NBA, NHL, MLB).
Offizielle Team-Apps koennen bis zu 15 Min schneller sein als Sleeper - der Bot holt Sleeper alle 15 Min neu!

**🔔 Benachrichtigungen**
In ⚙️ Einstellungen -> 🔔 Benachrichtigungen: Reminder + Live-Scores!
Live-Scores nur fuer deine Favoriten, pro Team einzeln: Jeder Score / Perioden-Ende + Weiter / Endstand. Alles aus = kein Spam!

**⏰ Reminder**
In ⚙️ Einstellungen → 🔔 Benachrichtigungen → ⏰ Reminder stellst du ein, wann du erinnert werden willst (3h / 2h / 1h / 30 Min / Aus).
Spielen 2 deiner Favoriten gleichzeitig, kriegst du 1 Nachricht für beide - mit Sender!

🪟 Fenster
Auswahl = Fenster ändert sich! Detail = neues Fenster! ✖️ = Fenster weg!

🧹 Live
Nach Spielende: Fenster schließen reicht!

Einfach auf die Knöpfe drücken - kein @, kein Befehl nötig."""

NHL_HELP_TEXT = """❓ NHL-Tabelle erklärt

So liest du die Tabelle:
15-3-2 = 15 Siege - 3 Niederlagen - 2 Overtime-Niederlagen

Streak (in Klammern):
W3 = 3 Siege in Folge
L1 = 1 Niederlage in Folge (in 60 Minuten, 0 Punkte)
OT1 = 1 Spiel in Folge in Overtime / Shootout verloren (1 Punkt!)

Punkte (PTS):
Sieg = 2 Punkte
Overtime-Niederlage = 1 Punkt
Niederlage in 60 Minuten = 0 Punkte

Beispiel: Sabres 8-7-4 (OT1 • 20 PTS)
= 8 Siege, 7 Niederlagen, 4 Overtime-Niederlagen
= Letztes Spiel in Overtime verloren
= 8x2 + 4x1 = 20 Punkte!

Sortiert wird nach Punkten, nicht nach Siegen!"""

NHL_LEGEND_SHORT = "💡 W-L-OTL = Siege - Niederlagen - Overtime-Niederlagen • PTS = Punkte"
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try: ctx.user_data['last_section'] = 'main'
    except: pass
    await update.message.reply_text(START_TEXT, reply_markup=main_kb(with_close=False, uid=update.effective_user.id if update.effective_user else None))
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _hkb = _help_cats_kb()
    await update.message.reply_text("❓ Hilfe - Was willst du wissen?\n\nTippe eine Kategorie an - nur das Thema, kein Batzen Text!", reply_markup=_hkb)

async def fav_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    favs = favs_for(update.effective_user.id)
    txt = "⭐ Deine Favoriten:\n" + ("\n".join([f"• {f}" for f in favs]) if favs else "Noch keine Favoriten.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Favorit hinzufügen", callback_data="fav_add")],
        [InlineKeyboardButton("🗑️ Favorit entfernen", callback_data="fav_remove")],
        [InlineKeyboardButton("🗑️ Alle Favoriten löschen", callback_data="fav_clear")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await update.message.reply_text(txt + "\n\nBitte Teamnamen eingeben:", reply_markup=kb)
    ctx.user_data["awaiting_fav"] = True

async def top10_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏈 NFL", callback_data="top10_league:NFL"),
         InlineKeyboardButton("🎓 NCAAF", callback_data="top10_league:NCAAF")],
        [InlineKeyboardButton("🏒 NHL", callback_data="top10_league:NHL"),
         InlineKeyboardButton("🏀 NBA", callback_data="top10_league:NBA")],
        [InlineKeyboardButton("⚾ MLB", callback_data="top10_league:MLB"),
         InlineKeyboardButton("🌎 Alle Ligen", callback_data="top10_league:ALL")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "🏆 Top 10 Spiele der Woche\n\nWelche Liga?", kb)
async def top10_league_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str):
    target = update.message or update.callback_query.message
    _title_league = "Alle Ligen" if league=="ALL" else league
    _load = None
    try:
        _load = await target.reply_text(f"🏆 Ich suche die {_title_league} Top 10... einen Moment ⏳")
    except Exception:
        pass
    try:
        leagues = list(LEAGUES.keys()) if league=="ALL" else [league]
        from datetime import date as _date
        today = _date.today()
        # V218: Top 10 = nur Spiele DIESER Woche (heute -> Sonntag)! Vorher: heute + 7 Tage,
        # dadurch haben Spiele von NAECHSTER Woche (28.11.) die heutigen Spiele (z.B. Texas) rausgedraengt!
        _days_to_sun = (6 - today.weekday()) % 7  # Montag=0 ... Sonntag=6
        _win_days = _days_to_sun + 1  # heute + bis Sonntag
        _win_end = today + timedelta(days=_win_days - 1)
        all_games=[]; seen=set()
        for lg in leagues:
            for offset in range(0, _win_days):
                d = today + timedelta(days=offset)
                ds = d.strftime("%Y%m%d")
                try:
                    _evs = espn_scoreboard(lg, dates=ds)
                except Exception:
                    continue
                for ev in _evs or []:
                    try:
                        eid = ev.get("id")
                        if eid in seen: continue
                        seen.add(eid)
                        state = ev.get("status",{}).get("type",{}).get("state","")
                        if state=="post": continue
                        if _v135_is_finished(ev): continue
                        try:
                            score, bd = rank_game(ev, lg)
                        except Exception:
                            score, bd = 5.0, {}
                        all_games.append((score, lg, ev, bd))
                    except Exception:
                        continue
        # Fallback: wenn keine kommenden Spiele (z.B. API liefert Woche anders), nimm letzte Finals der letzten 7 Tage
        if not all_games:
            for lg in leagues:
                for offset in range(0, 8):
                    d = today - timedelta(days=offset)
                    ds = d.strftime("%Y%m%d")
                    try: _evs = espn_scoreboard(lg, dates=ds)
                    except Exception: continue
                    for ev in _evs or []:
                        try:
                            eid = ev.get("id")
                            if eid in seen: continue
                            seen.add(eid)
                            state = ev.get("status",{}).get("type",{}).get("state","")
                            if state!="post": continue
                            try: score, bd = rank_game(ev, lg)
                            except Exception: score, bd = 5.0, {}
                            all_games.append((score, lg, ev, bd))
                        except Exception: continue
        # V219: Gleichstand = fruehere Anstosszeit zuerst (deterministisch, kein Zufall)!
        all_games.sort(key=lambda x: (-x[0], x[2].get("date","")))
        top = all_games[:10]
        ctx.user_data["top10_list"] = [(s, lg, ev, bd) for s, lg, ev, bd in top]; ctx.user_data["await_live_stats_pick"] = False  # V246: Live-Flag aus! Diese Liste gewinnt jetzt!
        title = "Alle Ligen" if league=="ALL" else league
        lines=[f"🏆 Top 10 - {title}\n💡 Zahl tippen für Rating + Details!\n📅 Diese Woche: {today.strftime('%d.%m.')} – {_win_end.strftime('%d.%m.')}\n"]
        if not top:
            lines.append("Keine Spiele in den nächsten 7 Tagen gefunden.")
            _live_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔴 Meine Live-Spiele", callback_data="my_live_games")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
            try:
                if _load: await ctx.bot.delete_message(chat_id=update.effective_user.id, message_id=_load.message_id)
            except Exception: pass
            _m201 = await target.reply_text("\n".join(lines), reply_markup=_live_kb)
            try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
            except: pass
            return
        for rank, (score, lg, ev, bd) in enumerate(top, 1):
            try:
                teams,_ = event_teams(ev)
                def _short_by_homeaway(want):
                    try:
                        comp = ev.get("competitions", [{}])[0]
                        for c in comp.get("competitors", []):
                            if (c.get("homeAway","") or "").lower()==want:
                                tm = c.get("team", {}) or {}
                                return tm.get("shortDisplayName","") or tm.get("displayName","")
                        return ""
                    except: return ""
                a_name = _short_by_homeaway("away") or (teams[0][0] if teams else "")
                h_name = _short_by_homeaway("home") or (teams[1][0] if len(teams)>1 else "")
                date_s2, dt2 = fmt_dt(ev.get("date",""))
                time_s = dt2.strftime("%d.%m. %H:%M") if dt2 else date_s2
                try: bc = broadcast_line(ev)
                except Exception: bc = ""
                bc_suf = f" • 📺 {bc}" if bc else ""
                if league=="ALL":
                    lines.append(f"{rank}. {a_name} @ {h_name}\n   {LEAGUES[lg]['emoji']} {lg} • {time_s}{bc_suf}")
                else:
                    lines.append(f"{rank}. {a_name} @ {h_name}\n   {time_s}{bc_suf}")
            except Exception:
                continue
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 Andere Liga", callback_data="top10")],[InlineKeyboardButton("❓ Hilfe", callback_data="help")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")],])
        try:
            if _load: await ctx.bot.delete_message(chat_id=update.effective_user.id, message_id=_load.message_id)
        except Exception: pass
        _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
        try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        except: pass
    except Exception as e:
        try:
            if _load: await ctx.bot.delete_message(chat_id=update.effective_user.id, message_id=_load.message_id)
        except Exception: pass
        try: await target.reply_text(f"🏆 Top 10 - {_title_league}\n\nUps, ESPN war gerade langsam. Tippe nochmal auf Top 10 und wähle die Liga nochmal!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏆 Top 10", callback_data="top10")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]]))
        except Exception: pass
def _standings_row_for(lg, team_full):
    # Findet ein Team in espn_standings(lg): -> (div_short, rank_in_div, W, L, T, leader_row)
    try:
        divs = espn_standings(lg)
        if not divs: return None
        tl = (team_full or "").lower()
        for div, rows in divs.items():
            for i, (disp, short, abbr, W, L, T, streak) in enumerate(rows, 1):
                dl = disp.lower()
                if tl in dl or dl in tl or short.lower() in tl or tl in short.lower():
                    div_s = div.replace("American Football Conference", "AFC").replace("National Football Conference", "NFC").replace("American Football", "AFC").replace("National Football", "NFC").strip()
                    return (div_s, i, W, L, T, rows)
        return None
    except Exception:
        return None
def _playoff_mode(lg):
    # V75: Playoff-Logik nur SPAET in der Saison! Schaltet sich von alleine an!
    # NFL ab 12 Spielen (Woche 13+), NCAAF ab 10 Spielen, NHL/NBA ab 60 Spielen, MLB ab 140 Spielen!
    try:
        divs = espn_standings(lg)
        if not divs: return False
        max_games = 0
        for rows in divs.values():
            for (disp, short, abbr, W, L, T, streak) in rows:
                max_games = max(max_games, W + L + (T or 0))
        thr = {"NFL": 12, "NCAAF": 10, "NHL": 60, "NBA": 60, "MLB": 140}.get(lg, 999)
        return max_games >= thr
    except Exception:
        return False
def _slot_label(dt):
    if not dt: return "Slot"
    h = dt.hour
    if 18 <= h <= 20: return "Früh-Slot (19:00)"
    if 21 <= h <= 23: return "Spät-Slot (22:25)"
    if 0 <= h <= 5: return "Nacht-Slot (02:15)"
    if 12 <= h <= 17: return "Nachmittags-Slot"
    return "Slot"
async def top10_detail_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, idx: int):
    target = update.message or update.callback_query.message
    lst = ctx.user_data.get("top10_list", [])
    if not lst or idx<1 or idx>len(lst):
        await target.reply_text("Tippe erst auf 🏆 Top 10 und wähle eine Liga, dann die Zahl!", reply_markup=small_kb()); return
    score, lg, ev, bd = lst[idx-1]
    if _v135_is_finished(ev):
        await target.reply_text("🏁 Spiel vorbei — wird nicht mehr bewertet!\n\nSchau bei ✅ Ergebnisse für Final Stats!", reply_markup=small_kb()); return
    teams,_ = event_teams(ev)
    # V71: Detail auch Gast @ Heim via homeAway + Liga-Tag!
    def _short_hw(want):
        try:
            comp = ev.get("competitions", [{}])[0]
            for c in comp.get("competitors", []):
                if (c.get("homeAway","") or "").lower()==want:
                    tm = c.get("team", {}) or {}
                    return tm.get("shortDisplayName","") or tm.get("displayName","")
            return ""
        except: return ""
    a_name = _short_hw("away") or (teams[0][0] if teams else "")
    h_name = _short_hw("home") or (teams[1][0] if len(teams)>1 else "")
    date_s, dt = fmt_dt(ev.get("date",""))
    time_s = dt.strftime("%d.%m. %H:%M") if dt else date_s
    bc = broadcast_line(ev)
    bc_suf = f" • 📺 {bc}" if bc else ""
    # V75: Fazit NEU! Nicht mehr "Wenn du nur 1 Spiel guckst..." - doof, wenn um 19:00 4 Spiele laufen!
    # Jetzt: Nach Rating gestaffelt + Uhrzeit-Hinweis!
    if score>=9.5: fazit_base = "🔥 Absoluter Top-Kracher der Woche! Wenn du ein Spiel guckst, dann das hier!"
    elif score>=9.0: fazit_base = "Richtig starkes Spiel - lohnt sich auf jeden Fall reinzugucken!"
    elif score>=8.0: fazit_base = "Solides Spiel - vor allem für Fans der Teams interessant!"
    else: fazit_base = "Kein Kracher, aber für Fans der Teams interessant."
    # Uhrzeit-Hinweis: 19:00 okay, 22:25 spät, 02:15 Nachtschicht!
    _h = dt.hour if dt else 19
    if 18 <= _h <= 20: _time_hint = "Perfekte Zeit - direkt nach Feierabend!"
    elif 21 <= _h <= 23: _time_hint = "Spätspiel - eher was für Nachtschwärmer!"
    elif 0 <= _h <= 5: _time_hint = "Nachtschicht - nur für harte Nerds oder Aufnahme!"
    elif 12 <= _h <= 17: _time_hint = "Nachmittags-Spiel - gut für Sonntag Nachmittag!"
    else: _time_hint = ""
    fazit = f"{fazit_base} {_time_hint}".strip()
    _ven = venue_line(ev).strip()
    _ven_line = f"\n{_ven}" if _ven else ""
    # V75: Standings + Slot-Top + Playoff (einfach gedacht, kein Tiebreaker-Kram!)
    # Standings: Vollnamen aus event_teams (teams[0]/teams[1] sind Vollnamen!)
    _full_away = ""; _full_home = ""
    try:
        for _nm, _ha, _sc in teams:
            if (_ha or "").lower()=="away": _full_away = _nm
            if (_ha or "").lower()=="home": _full_home = _nm
        if not _full_away: _full_away = teams[0][0]
        if not _full_home: _full_home = teams[1][0] if len(teams)>1 else ""
    except Exception:
        _full_away, _full_home = a_name, h_name
    _row_a = _standings_row_for(lg, _full_away)
    _row_h = _standings_row_for(lg, _full_home)
    _stand_lines = []
    if _row_a and _row_h:
        _div_a, _rank_a, _wa, _la, _ta, _rows_a = _row_a
        _div_h, _rank_h, _wh, _lh, _th, _rows_h = _row_h
        _rec_a = f"{_wa}-{_la}" + (f"-{_ta}" if _ta else "")
        _rec_h = f"{_wh}-{_lh}" + (f"-{_th}" if _th else "")
        # V78: "Um nix mehr" NUR wenn's rechnerisch wirklich nicht mehr geht!
        # Nicht einfach "Platz 3+ = um nix mehr"! Wer Letzter ist, kann noch jedes Spiel gewinnen und hoch kommen!
        # Rechnung: Verbleibende Spiele = Gesamt - schon gespielt! Gesamt: NFL 17, NCAAF 12, NHL/NBA 82, MLB 162!
        # Wenn W + verbleibend < Siege von Platz 2 -> selbst mit nur Siegen nicht mehr auf Platz 2 zu holen -> DANN erst "um nix mehr"!
        _TOTAL_GAMES = {"NFL": 17, "NCAAF": 12, "NHL": 82, "NBA": 82, "MLB": 162}.get(lg, 17)
        def _can_still_top2(_rank, _w, _l, _t, _rows):
            if _rank <= 2: return True
            if len(_rows) < 2: return True
            _w2 = _rows[1][3]  # Siege von Platz 2 in der Division!
            _remaining = max(0, _TOTAL_GAMES - (_w + _l + (_t or 0)))
            # Selbst wenn alle verbleibenden Spiele gewonnen werden: W + verbleibend >= W2? Dann noch möglich!
            return (_w + _remaining) >= _w2
        _can_a = _can_still_top2(_rank_a, _wa, _la, _ta, _rows_a)
        _can_h = _can_still_top2(_rank_h, _wh, _lh, _th, _rows_h)
        _top_a = _rank_a <= 2
        _top_h = _rank_h <= 2
        if _can_a or _can_h:
            _stand_lines.append(f"\n📊 **Standings:**")
            _stand_lines.append(f"Die {a_name} sind Platz {_rank_a} in {_div_a} ({_rec_a})")
            _stand_lines.append(f"Die {h_name} sind Platz {_rank_h} in {_div_h} ({_rec_h})")
            if _top_a and _top_h and _div_a == _div_h:
                _stand_lines.append(f"Direktes Duell um Platz 1 in der {_div_a}! Der Sieger ist Platz 1!")
            elif _top_a and not _top_h:
                # Unten, aber noch möglich! Nicht "um nix mehr", sondern "Noch alles möglich!"
                _stand_lines.append(f"Die {a_name} wollen Platz {_rank_a} verteidigen, die {h_name} können noch hoch kommen - noch alles möglich, wenn die jetzt jedes Spiel gewinnen!")
            elif _top_h and not _top_a:
                _stand_lines.append(f"Die {h_name} wollen Platz {_rank_h} verteidigen, die {a_name} können noch hoch kommen - noch alles möglich, wenn die jetzt jedes Spiel gewinnen!")
            elif _div_a == _div_h:
                _stand_lines.append(f"Direktes Duell in der {_div_a}! Der Sieger bleibt oben dran, der Verlierer rutscht ab!")
            else:
                _stand_lines.append(f"Der Sieger bleibt oben dran, der Verlierer rutscht ab!")
        else:
            # BEIDE können Platz 2 rechnerisch nicht mehr holen -> DANN erst "um nix mehr"!
            _stand_lines.append(f"\n📊 **Standings:** Da geht's in der Tabelle um nix mehr - eher um Ehre! 😂")
    # Slot-Top: Ist das das beste Spiel im gleichen Slot (gleicher Tag + gleiche Slot-Zeit)?
    _slot = _slot_label(dt)
    _slot_line = ""
    try:
        _lst = ctx.user_data.get("top10_list", [])
        _same_slot = []
        for _s, _lg2, _ev2, _bd2 in _lst:
            _, _dt2 = fmt_dt(_ev2.get("date",""))
            if _dt2 and dt and _dt2.date()==dt.date() and _slot_label(_dt2)==_slot:
                _same_slot.append((_s, _ev2))
        if len(_same_slot) > 1:
            _best = max(_same_slot, key=lambda x: x[0])[0]
            if score >= _best - 0.01:
                _slot_line = f"\n🏆 **Top-Spiel für den {_slot}!**"
            else:
                _slot_line = f"\nEs laufen {len(_same_slot)} Spiele im {_slot} - das hier ist nicht das Top-Spiel im Slot, aber trotzdem stark!"
    except Exception:
        pass
    # Playoff: Nur SPAET in der Saison! Einfach gedacht: Beide im Rennen, kein Tiebreaker!
    _playoff_lines = []
    if _playoff_mode(lg):
        _playoff_lines.append(f"\n🔥 **Playoff-Rennen:**")
        _playoff_lines.append(f"Beide Teams sind im Playoff-Rennen! Mit Sieg: Bleiben oben dran! Mit Niederlage: Rutschen ab - da ist jedes Spiel wichtig!")
    lines=[f"🏆 {a_name} @ {h_name} • {LEAGUES[lg]['emoji']} {lg} • ⭐ {score:.1f}/10\n📅 {time_s}{bc_suf}{_ven_line}{_slot_line}\n\n**Warum {score:.1f}/10?**\n",
        f"🏅 **Top-Teams:** +{bd['tabelle']:.1f} - Bekannte Top-Teams dabei - grosses Spiel mit viel Gewicht.",
        f"🔥 **Rivalität:** +{bd['rival']:.1f} - " + ("Historische Rivalität! Die beiden haben sich schon oft in großen Spielen getroffen." if bd['rival']>=2.5 else "Division-Duell / zwei starke Teams - da ist Feuer drin." if bd['rival']>=1.5 else "Kein großes Rivalitäts-Spiel, aber beide wollen gewinnen."),
        f"⭐ **Stars:** +{bd['stars']:.1f} - Viele bekannte Stars auf dem Feld, die das Spiel entscheiden können.",
        f"📺 **Primetime:** +{bd['prime']:.1f} - " + ("Primetime-Spiel! Läuft zur besten Zeit, wo alle zugucken." if bd['prime']>=1.0 else "Kein Primetime-Spiel, läuft neben anderen Spielen."),
        f"📊 **Tabellenstand:** +{bd.get('stand',0):.1f} - " + ("Beide Teams haben eine Winning Record - das Spiel zählt für die Tabelle." if bd.get('stand',0)>=1.0 else ("Beide Teams stehen um .500 - noch alles drin." if bd.get('stand',0)>=0.5 else "Tabellenstand gibt hier keine Extrapunkte - ein Team steht unter .500.")),
        f"\n**Fazit:** {fazit}"]
    # Standings + Playoff nach den Warum-Zeilen, vor Fazit? Nein: Nach Warum, vor Fazit ist unübersichtlich - wir hängen sie vor Fazit an!
    # Einfach: Wir fügen sie als eigene Zeilen nach der Warum-Liste ein, Fazit bleibt letzte Zeile!
    # Dafür: Fazit-Zeile rausnehmen, Standings+Playoff einfügen, Fazit wieder dran!
    if _stand_lines or _playoff_lines:
        _fazit_line = lines.pop()
        lines.extend(_stand_lines)
        lines.extend(_playoff_lines)
        lines.append(_fazit_line)
    # V53: Keine Zahlen-Buttons mehr, nur Zahl in den Chat schreiben!
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 Top 10", callback_data="top10")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    lines.append("\n💡 Schreib eine andere Zahl (z.B. 5) in den Chat für ein anderes Spiel!")
    _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
# --- Tabellen / Standings via ESPN ---
STANDINGS_URL = {
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/standings",
    "NCAAF": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/standings",
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/standings",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/standings",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/standings",
}
_STANDINGS_DEBUG = {"last_keys": "", "last_status": 0, "last_url": ""}
def _season_year(league):
    # V63-FIX: Saison war fest auf 2025 -> im Nov 2026 zeigte der Bot letzte Saison (Steelers 10-7)!
    # Jetzt dynamisch: NFL/NCAAF ab Sept = aktuelles Jahr, NBA/NHL ab Okt = aktuelles Jahr, MLB = aktuelles Jahr
    from datetime import datetime as _dt
    now=_dt.now(); y=now.year; m=now.month
    if league in ("NFL","NCAAF"):
        return y if m>=8 else y-1
    if league in ("NBA","NHL"):
        # V64-FIX: NBA/NHL zählen Saison nach END-Jahr! 2026 = Saison 2025-26 (alt)!
        # Aktuelle Saison 2026-27 heisst bei ESPN 2027! Ab Okt = aktuelles Jahr +1, sonst aktuelles Jahr
        return y+1 if m>=10 else y
    if league=="MLB":
        return y
    return y
def _espn_standings_raw(league):
    # ESPN Tabellen, None-sicher! V60-Fehler war: children=None -> 'NoneType' not subscriptable -> jetzt or []
    urls=[]
    if league=="NFL":
        sy=_season_year("NFL"); urls=[f"https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season={sy}&seasontype=2&type=0&level=4", f"https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season={sy}"]
    elif league=="NBA":
        sy=_season_year("NBA"); urls=[f"https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season={sy}"]
    elif league=="NHL":
        sy=_season_year("NHL"); urls=[f"https://site.api.espn.com/apis/v2/sports/hockey/nhl/standings?season={sy}"]
    elif league=="MLB":
        sy=_season_year("MLB"); urls=[f"https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings?season={sy}"]
    elif league=="NCAAF":
        sy=_season_year("NCAAF"); urls=[f"https://site.api.espn.com/apis/v2/sports/football/college-football/standings?season={sy}"]
    for u in urls:
        try:
            r=requests.get(u, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
            _STANDINGS_DEBUG["last_url"]=u; _STANDINGS_DEBUG["last_status"]=r.status_code
            if r.status_code!=200: continue
            j=r.json()
            out={}
            def walk(node, path):
                if isinstance(node, dict):
                    kids = node.get("children") or []
                    if kids:
                        nm = node.get("name","") or node.get("displayName","") or ""
                        for ch in kids: walk(ch, path+[nm] if nm else path)
                        return
                    st = node.get("standings") or {}
                    ents = st.get("entries") if isinstance(st, dict) else None
                    if isinstance(ents, list) and ents:
                        gname = node.get("name","") or node.get("displayName","") or " ".join(path) or "Tabelle"
                        rows=[]
                        for e in ents:
                            if not isinstance(e, dict): continue
                            tm=e.get("team", {}) or {}
                            disp=tm.get("displayName","") or tm.get("shortDisplayName","") or "?"
                            short=tm.get("shortDisplayName","") or disp
                            W=L=T=0; streak=""
                            # WICHTIG: ESPN hat mehrere Wins-Werte (z.B. Conference-Wins + Overall-Wins)!
                            # Wir nehmen OVERALL! Priorität: overallWins > wins, overallLosses > losses
                            vals={}
                            for s in e.get("stats", []) or []:
                                if not isinstance(s, dict): continue
                                n=(s.get("name","") or "").lower(); v=s.get("displayValue", s.get("value",""))
                                vals[n]=v
                            def _iv(*names):
                                for n in names:
                                    if n in vals:
                                        try: return int(float(str(vals[n])))
                                        except: pass
                                return 0
                            W=_iv("overallwins","wins")
                            L=_iv("overalllosses","losses")
                            T=_iv("overallties","ties")
                            streak=str(vals.get("streak","") or "")
                            rows.append((disp, short, tm.get("abbreviation",""), W, L, T, streak))
                        if rows and gname not in out: out[gname]=rows
                        return
                    for k,v in node.items():
                        if k=="standings": continue
                        walk(v, path)
                elif isinstance(node, list):
                    for it in node: walk(it, path)
            walk(j, [])
            if out:
                clean={}
                for k,v in out.items():
                    kk=k.replace("American Football Conference","AFC").replace("National Football Conference","NFC").replace("Eastern Conference","Eastern").replace("Western Conference","Western").strip()
                    clean[kk]=v
                return clean
        except Exception:
            continue
    return {}

def _ncaaf_records_from_scoreboard():
    # V144: Datums-Bereiche statt Week-Nummern! Week-Param ist bei NCAAF unzuverlässig (zählte nur 1-2 Spiele)!
    # Saison 29.08. - 15.11. in 30-Tage-Chunks, Scoreboard mit dates=YYYYMMDD-YYYYMMDD!
    rec={}
    try: sy=_season_year("NCAAF")
    except: sy=2026
    from datetime import date as _date, timedelta as _td
    _start=_date(sy,8,29); _end=_date(sy,11,16)
    _chunks=[]
    _cur=_start
    while _cur<=_end:
        _nxt=min(_cur+_td(days=29), _end)
        _chunks.append((_cur,_nxt)); _cur=_nxt+_td(days=1)
    for _s,_e in _chunks:
        try:
            rng=f"{_s.strftime('%Y%m%d')}-{_e.strftime('%Y%m%d')}"
            u=f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates={rng}&limit=500"
            r=requests.get(u, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code!=200: continue
            j=r.json()
            for ev in j.get("events", []) or []:
                _st=((ev.get("status") or {}).get("type") or {}).get("state","")
                _comp=((ev.get("status") or {}).get("type") or {}).get("completed", False)
                if _st!="post" and _comp is not True: continue
                comps=ev.get("competitions", []) or []
                if not comps: continue
                comp=comps[0]
                teams=comp.get("competitors", []) or []
                if len(teams)!=2: continue
                wteam=None
                for tm in teams:
                    if tm.get("winner") is True: wteam=tm
                if wteam is None:
                    try:
                        s0=int(float(str((teams[0].get("score") or "0")))); s1=int(float(str((teams[1].get("score") or "0"))))
                        wteam=teams[0] if s0>s1 else teams[1] if s1>s0 else None
                    except: wteam=None
                if wteam is None: continue
                for tm in teams:
                    tinfo=tm.get("team", {}) or {}
                    disp=tinfo.get("displayName","") or ""
                    _abbr=(tinfo.get("abbreviation","") or "").upper()
                    _short=tinfo.get("shortDisplayName","") or ""
                    if not disp: continue
                    for _k in [disp, _abbr, _short]:
                        if _k and _k not in rec: rec[_k]=[0,0]
                    _won = (tm.get("team", {}) or {}).get("id")== (wteam.get("team", {}) or {}).get("id")
                    for _k in [disp, _abbr, _short]:
                        if not _k: continue
                        if _won: rec[_k][0]+=1
                        else: rec[_k][1]+=1
        except Exception:
            continue
    return rec

def _nhl_standings():
    # V65: NHL über OFFIZIELLE NHL-API! ESPN spinnt bei NHL (nur Conferences, falsche Stände, doppelte Buttons)!
    # https://api-web.nhle.com/v1/standings/now -> standings[] mit divisionName, conferenceName, teamCommonName, wins, losses, otLosses, points, streakCode
    try:
        r=requests.get("https://api-web.nhle.com/v1/standings/now", timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code!=200: return {}
        j=r.json()
        out={}
        for s in j.get("standings", []) or []:
            div=s.get("divisionName","") or "NHL"
            team_name=(s.get("teamName", {}) or {}).get("default","") or ""
            short=(s.get("teamCommonName", {}) or {}).get("default","") or team_name
            abbr=s.get("teamAbbrev", {}).get("default","") if isinstance(s.get("teamAbbrev"), dict) else (s.get("teamAbbrev","") or "")
            W=int(s.get("wins",0) or 0); L=int(s.get("losses",0) or 0); OTL=int(s.get("otLosses",0) or 0)
            PTS=int(s.get("points",0) or 0)
            # V66-FIX: NHL-API trennt streakCode="W" und streakCount=2! Zusammen = "W2"! Vorher stand nur "W" ohne Zahl!
            _code=str(s.get("streakCode","") or "").strip()
            _cnt=s.get("streakCount","")
            try: _cnt=int(_cnt) if _cnt not in ("", None) else 0
            except: _cnt=0
            streak=f"{_code}{_cnt}" if _code and _cnt else _code
            # streak-Feld trägt bei NHL BEIDES: Streak + Punkte! Anzeige wird: "15-5-2 (W2 \u2022 32 PTS)"
            streak_disp=f"{streak} \u2022 {PTS} PTS" if streak else f"{PTS} PTS"
            out.setdefault(div, []).append((team_name, short, abbr, W, L, OTL, streak_disp))
        # Sortieren pro Division nach Punkten (NHL-Standard!), nicht nach Wins!
        for k in out: out[k].sort(key=lambda x: (int(str(x[6]).split("\u2022")[-1].replace("PTS","").strip() or 0) if "PTS" in str(x[6]) else 0, x[3]), reverse=True)
        return out
    except Exception:
        return {}

_CFBD_CACHE={"ts":0,"data":None}
def _cfbd_records():
    # V141: CollegeFootballData = echte Gesamt-Records für ALLE NCAAF-Teams!
    # https://api.collegefootballdata.com/records?year=2026 -> [{team, conference, total:{wins,losses}, conferenceGames:{wins,losses}}]
    # Key: CFBD_API_KEY auf Render (wie BOT_TOKEN). Ohne Key wird es trotzdem probiert!
    import time as _t
    try:
        if _CFBD_CACHE["data"] is not None and (_t.time()-_CFBD_CACHE["ts"])<21600:  # V145: 6h Cache! Free Tier 1000/Monat, Records ändern sich nur samstags!
            return _CFBD_CACHE["data"]
        try: sy=_season_year("NCAAF")
        except: sy=2026
        headers={"User-Agent":"USA-Sport-Radar/1.0"}
        _key=os.getenv("CFBD_API_KEY") or ""
        if _key: headers["Authorization"]=f"Bearer {_key}"
        r=requests.get("https://api.collegefootballdata.com/records",params={"year":sy},headers=headers,timeout=12)
        if r.status_code!=200:
            return {}
        d=r.json() or []
        out={}
        for e in d:
            team=str(e.get("team","") or "").strip()
            tot=e.get("total") or {}
            try: W=int(tot.get("wins",0) or 0); L=int(tot.get("losses",0) or 0)
            except: continue
            if not team or W+L==0: continue
            out[team.lower()]=(W,L)
            # V144: KEIN Wort-Splitting! "Texas" darf NICHT auf "Texas A&M" zeigen!
        _CFBD_CACHE["data"]=out; _CFBD_CACHE["ts"]=_t.time()
        return out
    except: return {}
def _cfbd_overall_for(team_full, cfbd=None):
    # V146: Schulname-Extraktion! ESPN "Texas Longhorns" -> Schule "Texas" -> CFBD "Texas"!
    # "North Carolina Tar Heels" -> "North Carolina", "Georgia Tech Yellow Jackets" -> "Georgia Tech", "Texas A&M Aggies" -> "Texas A&M"!
    try:
        if cfbd is None: cfbd=_cfbd_records()
        if not cfbd: return None
        low=(team_full or "").lower().strip()
        # Aliase: Pitt -> Pittsburgh, etc.
        _ALIAS={"pitt":"pittsburgh","texas longhorns":"texas","pittsburgh panthers":"pittsburgh","navy midshipmen":"navy"}
        low=_ALIAS.get(low, low)
        if low in cfbd: return cfbd[low]
        # Schulname-Kandidaten: Voll, ohne Maskottchen (letztes Wort weg), erste 2 Wörter, erstes Wort
        # "texas longhorns" -> ["texas longhorns","texas","texas"] ; "north carolina tar heels" -> ["north carolina tar heels","north carolina","north carolina"]
        # "georgia tech yellow jackets" -> ["georgia tech yellow jackets","georgia tech","georgia tech"]
        _words=low.split()
        _cands=[]
        if low: _cands.append(low)
        if len(_words)>=2:
            _cands.append(" ".join(_words[:-1]))  # ohne Maskottchen
            _cands.append(" ".join(_words[:2]))   # erste 2 Wörter (North Carolina, Georgia Tech, Texas A&M)
        if _words:
            _cands.append(_words[0])  # erstes Wort
        # 2-Wort-Schulen zuerst (North Carolina darf nicht auf North Texas zeigen!), dann 1-Wort
        _cands_sorted=sorted(set(_cands), key=lambda x: -len(x))
        for _c in _cands_sorted:
            if _c in cfbd: return cfbd[_c]
        # Letzter Fallback: CFBD-Key == Kandidat
        for _c in _cands_sorted:
            for k,v in cfbd.items():
                if k==_c: return v
        return None
    except: return None

def _espn_standings_uncached(league):
    # V65: NHL zuerst über offizielle NHL-API!
    if league=="NHL":
        nhl=_nhl_standings()
        if nhl: return nhl

    # V62: TheSportsDB RAUS! War veraltet (Steelers 10-7 = letzte Saison, NCAAF 0-0)!
    # NFL/NBA/NHL/MLB = ESPN direkt (aktuell + korrekt)
    # NCAAF = ESPN für Conference-Gruppierung + Record selbst aus Scoreboard gerechnet!
    raw=_espn_standings_raw(league)
    if league!="NCAAF" or not raw:
        return raw
    # V141: NCAAF = CFBD ZUERST (echte Gesamt-Records für ALLE!), dann Scoreboard, dann raw!
    try:
        cfbd=_cfbd_records()
        if cfbd:
            fixed={}
            for gname, rows in raw.items():
                nrows=[]
                for (disp, short, abbr, W, L, T, streak) in rows:
                    _hit=_cfbd_overall_for(disp, cfbd) or _cfbd_overall_for(short, cfbd) or _cfbd_overall_for(abbr, cfbd)
                    if _hit:
                        nrows.append((disp, short, abbr, _hit[0], _hit[1], T, streak))
                    else:
                        # V146: Kein CFBD-Hit -> NICHT raw (Conference-Müll wie SEC 5-0/0) behalten! Scoreboard-Fallback!
                        try:
                            _rec=_ncaaf_records_from_scoreboard()
                            _sb=None
                            for _k in [disp, short, abbr]:
                                if _k and _k in _rec and _rec[_k][0]+_rec[_k][1]>0:
                                    _sb=_rec[_k]; break
                            if _sb:
                                nrows.append((disp, short, abbr, _sb[0], _sb[1], T, streak))
                            else:
                                nrows.append((disp, short, abbr, W, L, T, streak))
                        except Exception:
                            nrows.append((disp, short, abbr, W, L, T, streak))
                def _pct2(x):
                    tot=x[3]+x[4]
                    return (x[3]/tot if tot else 0, x[3])
                nrows.sort(key=lambda x: _pct2(x), reverse=True)
                fixed[gname]=nrows
            return fixed
    except Exception:
        pass
    # Fallback: Scoreboard-Nachzählen
    try:
        rec=_ncaaf_records_from_scoreboard()
        if rec:
            fixed={}
            for gname, rows in raw.items():
                nrows=[]
                for (disp, short, abbr, W, L, T, streak) in rows:
                    _hit=None
                    for _k in [disp, short, abbr, (abbr or "").upper()]:
                        if _k and _k in rec and rec[_k][0]+rec[_k][1]>0:
                            _hit=rec[_k]; break
                    if _hit:
                        nrows.append((disp, short, abbr, _hit[0], _hit[1], T, streak))
                    else:
                        nrows.append((disp, short, abbr, W, L, T, streak))
                def _pct2b(x):
                    tot=x[3]+x[4]
                    return (x[3]/tot if tot else 0, x[3])
                nrows.sort(key=lambda x: _pct2b(x), reverse=True)
                fixed[gname]=nrows
            return fixed
    except Exception:
        pass
    return raw
    # Raw ist nur Conference -> Scoreboard-Overall drüber!
    try:
        rec=_ncaaf_records_from_scoreboard()
        if rec:
            fixed={}
            for gname, rows in raw.items():
                nrows=[]
                for (disp, short, abbr, W, L, T, streak) in rows:
                    _hit=None
                    for _k in [disp, short, abbr, (abbr or "").upper()]:
                        if _k and _k in rec and rec[_k][0]+rec[_k][1]>0:
                            _hit=rec[_k]; break
                    if _hit:
                        nrows.append((disp, short, abbr, _hit[0], _hit[1], T, streak))
                    else:
                        nrows.append((disp, short, abbr, W, L, T, streak))
                # Sortieren nach Gesamt-Record (Siegquote, dann Wins) - nicht nach Conference!
                def _pct2(x):
                    tot=x[3]+x[4]
                    return (x[3]/tot if tot else 0, x[3])
                nrows.sort(key=lambda x: _pct2(x), reverse=True)
                fixed[gname]=nrows
            return fixed
    except Exception:
        pass
    return raw

def espn_standings(league):
    # V247 CACHE: Tabellen aendern sich selten -> 5 Min cachen! Tabellen-Fenster sofort da!
    import time as _time2
    _ck = ("stand", league)
    try:
        if _ck in _V247_STAND_CACHE:
            _ts, _data = _V247_STAND_CACHE[_ck]
            if (_time2.time() - _ts) < 300:
                return _data
    except: pass
    _res = _espn_standings_uncached(league)
    try: _V247_STAND_CACHE[_ck] = (_time2.time(), _res)
    except: pass
    return _res
def standings_conferences(league, divs):
    # Für NBA/NHL: Eastern/Western als Sammel-Liste (sortiert nach Wins)
    # Division -> Conference Mapping
    conf_map = {
        "MLB": {"American": ["American"], "National": ["National"]},
        "NBA": {"Eastern": ["Atlantic","Central","Southeast"], "Western": ["Northwest","Pacific","Southwest"]},
        "NHL": {"Eastern": ["Atlantic","Metropolitan"], "Western": ["Central","Pacific"]},
    }
    m = conf_map.get(league, {})
    res={}
    for conf, div_names in m.items():
        rows=[]
        for dn in div_names:
            # divs keys können "Atlantic" oder "Eastern Atlantic" sein - flexibel matchen
            for k,v in divs.items():
                if dn.lower() in k.lower():
                    rows.extend(v)
        # Sortieren: NHL nach Punkten, Rest nach Wins!
        if league=="NHL":
            def _pts(x):
                try:
                    s=str(x[6] or "")
                    # "W2 • 32 PTS" -> 32
                    if "PTS" in s: return int(s.split("\u2022")[-1].replace("PTS","").strip())
                except: pass
                return 0
            rows.sort(key=lambda x: (_pts(x), x[3]), reverse=True)
        else:
            rows.sort(key=lambda x: (x[3], -x[4]), reverse=True)
        res[conf]=rows
    return res
async def tables_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Alle Ligen", callback_data="tables_all")],
        [InlineKeyboardButton("⭐ Nur meine Favoriten", callback_data="tables_mine")],
        [InlineKeyboardButton("🏆 Playoffs", callback_data="playoffs")],
        [InlineKeyboardButton("❓ Hilfe", callback_data="help")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "📊 Tabellen\n\nWas willst du sehen?\n📊 Alle Ligen = alle Tabellen, auch ohne Favoriten!\n⭐ Nur meine Favoriten = nur deine Teams, über alle Ligen!\n🏆 Playoffs = Wer ist schon sicher in den Playoffs, wer ist raus, wer ist noch im Rennen?", kb)
def _bowl_name(ev):
    # V83: Bowl-Name aus ESPN Notes! Z.B. "Pop-Tarts Bowl", "Rose Bowl"!
    # Steht in ev["notes"] oder in competitions[0]["notes"] als headline!
    for _src in [ev.get("notes", []) or []]:
        for _n in _src:
            _h = (_n.get("headline", "") or "").strip()
            if _h: return _h
    for _comp in (ev.get("competitions", []) or []):
        for _n in (_comp.get("notes", []) or []):
            _h = (_n.get("headline", "") or "").strip()
            if _h: return _h
    return ""
async def playoffs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    # V79: Buttons GANZ NORMAL benannt! Kein Schloss, kein "Saison vorbei" auf dem Button!
    # Erst wenn man drauf drückt, kommt: "Noch nix fest!" / "Saison vorbei + Champion!" / Playoff-Übersicht!
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏈 NFL", callback_data="playoffs_league:NFL"),
         InlineKeyboardButton("🎓 NCAAF", callback_data="playoffs_league:NCAAF")],
        [InlineKeyboardButton("🏒 NHL", callback_data="playoffs_league:NHL"),
         InlineKeyboardButton("🏀 NBA", callback_data="playoffs_league:NBA")],
        [InlineKeyboardButton("⚾ MLB", callback_data="playoffs_league:MLB")],
        [InlineKeyboardButton("❓ Hilfe", callback_data="help")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await target.reply_text("🏆 Playoffs\n\nWelche Liga?", reply_markup=kb)
async def playoffs_bowls_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str):
    target = update.message or update.callback_query.message
    from datetime import date as _date
    today = _date.today()
    # Bowl-Fenster: Dez bis Jan! Wenn heute Nov ist -> Dez dieses Jahr bis Jan nächstes Jahr! Wenn Jan/Feb -> Dez letztes Jahr bis Jan dieses Jahr!
    if today.month <= 2:
        _start, _end = _date(today.year-1, 12, 1), _date(today.year, 1, 31)
    else:
        _start, _end = _date(today.year, 12, 1), _date(today.year+1, 1, 31)
    _bowls = []
    for ev in espn_scoreboard(league, dates=f"{_start.strftime('%Y%m%d')}-{_end.strftime('%Y%m%d')}"):
        _sn = ((ev.get("season", {}) or {}).get("type", {}) or {}).get("name","").lower() + " " + ((ev.get("season", {}) or {}).get("type", {}) or {}).get("slug","").lower()
        _bn = _bowl_name(ev)
        # Bowl = Season-Type enthält "bowl" ODER Bowl-Name enthält "Bowl"! CFP-Spiele (playoff) raus, ausser sie sind auch ein Bowl als CFP-Viertelfinale - die bleiben in CFP!
        if "bowl" in _sn or "bowl" in _bn.lower():
            # Reine CFP-Spiele (Playoff ohne Bowl-Name) raus! Bowls mit Bowl-Namen rein!
            if "playoff" in _sn and "bowl" not in _sn and "bowl" not in _bn.lower():
                continue
            # CFP-Viertelfinale/Halbfinale in Bowls (z.B. Rose Bowl als CFP) -> raus, die sind in CFP!
            if "playoff" in _sn and ("quarterfinal" in _sn or "semifinal" in _sn):
                continue
            _, _dt = fmt_dt(ev.get("date",""))
            _bowls.append((_dt or datetime.now(BERLIN), _bn, ev))
    if not _bowls:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 CFP Playoffs", callback_data="playoffs_cfp:NCAAF")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        await target.reply_text("🥣 Bowl Games - 🎓🏈 NCAAF\n\nBowl Games starten erst im Dezember! 😅\nDie Matchups werden am Selection Sunday Anfang Dezember festgelegt!\nSchau dann nochmal vorbei!", reply_markup=kb); return
    _bowls.sort(key=lambda x: x[0])
    lines = ["🥣 Bowl Games - 🎓🏈 NCAAF\n"]
    _last_day = ""
    for _dt, _bn, ev in _bowls:
        _day = _dt.strftime("%d.%m.")
        if _day != _last_day:
            lines.append(f"\n📅 {_day}")
            _last_day = _day
        _bn_txt = f" — {_bn}" if _bn else " — Bowl Game"
        lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league, show_broadcast=True)}{_bn_txt}")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 CFP Playoffs", callback_data="playoffs_cfp:NCAAF")], [InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
    _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
async def playoffs_league_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str, force_cfp: bool = False):
    target = update.message or update.callback_query.message
    # V83: NCAAF -> erst Auswahl! CFP Playoffs vs. Bowl Games! Bowls sind keine Playoffs!
    if league == "NCAAF" and not force_cfp:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏆 CFP Playoffs", callback_data="playoffs_cfp:NCAAF")],
            [InlineKeyboardButton("🏆 CFP Top 25", callback_data="cfp_top25:NCAAF")],
            [InlineKeyboardButton("🥣 Bowl Games", callback_data="playoffs_bowls:NCAAF")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        await target.reply_text("🏆 Playoffs - 🎓🏈 NCAAF\n\nWas willst du sehen?\n🏆 CFP Playoffs = Wer ist in den Top 12, wer ist sicher, wer ist raus!\n🏆 CFP Top 25 = Offizielles Committee-Ranking, ⭐ = Dein Favorit!\n🥣 Bowl Games = Alle Bowl Games mit Bowl-Namen!", reply_markup=kb); return
    _load_pl = await _loading_start(target, "⏳ Ich hole den Playoff-Stand... einen Moment")
    _uid_pl = update.effective_user.id if update.effective_user else 0
    from datetime import date as _date
    today = _date.today()
    # --- Phase 2 Check: Laufen schon Playoffs? Postseason-Spiele in den letzten 30 + nächsten 30 Tagen? ---
    _post = []  # (dt, round_label, ev)
    # V179: CFP laeuft nur Dez/Jan! Im Nov kein Scoreboard-Check noetig - spart 2 Calls, gleiche Werte!
    _skip_phase2 = (league=="NCAAF" and force_cfp and today.month not in (12,1))
    for _rng in ([] if _skip_phase2 else [f"{(today - timedelta(days=30)).strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}", f"{today.strftime('%Y%m%d')}-{(today + timedelta(days=30)).strftime('%Y%m%d')}"]):
        for ev in espn_scoreboard(league, dates=_rng):
            _season = (ev.get("season", {}) or {}).get("type", {}) or {}
            _sname = ((_season.get("name","") or "") + " " + (_season.get("slug","") or "")).lower()
            _detail = ((ev.get("status", {}) or {}).get("type", {}) or {}).get("detail","") or ""
            if any(k in _sname for k in ["post", "playoff", "wild", "divisional", "conference", "championship", "final", "world series", "super bowl"]) or any(k in _detail.lower() for k in ["wild card", "divisional", "conference", "championship"]):
                _, _dt = fmt_dt(ev.get("date",""))
                _round = _season.get("name","") or "Playoffs"
                _post.append((_dt or datetime.now(BERLIN), _round, ev))
    # V83: NCAAF CFP -> Bowls raus! Nur Spiele, deren Season-Type "playoff" enthält, keine reinen Bowls!
    if league == "NCAAF" and force_cfp:
        _filtered = []
        for _dt, _round, ev in _post:
            _sn = ((ev.get("season", {}) or {}).get("type", {}) or {}).get("name","").lower() + " " + ((ev.get("season", {}) or {}).get("type", {}) or {}).get("slug","").lower()
            if "playoff" in _sn or "championship" in _sn or "quarterfinal" in _sn or "semifinal" in _sn:
                _filtered.append((_dt, _round, ev))
        _post = _filtered
        if not _post:
            # Noch keine CFP-Spiele in den nächsten 30 Tagen -> weiter zu Phase 1 (Sicher/Raus/Top 12)!
            pass
        else:
            _post.sort(key=lambda x: x[0])
            lines = [f"🏆 CFP Playoffs - {LEAGUES[league]['emoji']} {league}\n"]
            _last_round = ""
            for _dt, _round, ev in _post:
                if _round != _last_round:
                    lines.append(f"\n**{_round}**")
                    _last_round = _round
                _bn = _bowl_name(ev)
                _bn_txt = f" — {_bn}" if _bn else ""
                lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league, show_broadcast=True)}{_bn_txt}")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🥣 Bowl Games", callback_data="playoffs_bowls:NCAAF")], [InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
            await _loading_done(ctx, _uid_pl, _load_pl)
            _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
            try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
            except: pass
            return
    if _post:
        _post.sort(key=lambda x: x[0])
        lines = [f"🏆 Playoffs - {LEAGUES[league]['emoji']} {league}\n"]
        _last_round = ""
        for _dt, _round, ev in _post:
            if _round != _last_round:
                lines.append(f"\n**{_round}**")
                _last_round = _round
            lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league, show_broadcast=True)}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        await _loading_done(ctx, _uid_pl, _load_pl)
        _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
        try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        except: pass
        return
    # --- Saison vorbei? Keine Spiele in den nächsten 30 Tagen + keine in den letzten 7 Tagen + Champion bekannt? ---
    _future = []
    for _off in range(0, 31):
        _d = today + timedelta(days=_off)
        _future.extend(espn_scoreboard(league, dates=_d.strftime("%Y%m%d")))
    _recent = []
    for _off in range(0, 8):
        _d = today - timedelta(days=_off)
        _recent.extend(espn_scoreboard(league, dates=_d.strftime("%Y%m%d")))
    if not _future and not _recent and league in CHAMPIONS:
        ch = CHAMPIONS[league]
        _ch_label = {"NFL": "Super Bowl Champion", "NCAAF": "National Champion", "MLB": "World Series Champion", "NHL": "Stanley Cup Champion", "NBA": "NBA Champion"}.get(league, "Champion")
        _note = f"\n💡 {ch['note']}" if ch.get("note") else ""
        lines = [f"🏆 Playoffs - {LEAGUES[league]['emoji']} {league}\nSaison vorbei! {LEAGUES[league]['emoji']}\n\n🏆 **{_ch_label}:**\n{ch['team']} ({ch['year']})\n{ch['result']}{_note}"]
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
        try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        except: pass
        return
    # --- Phase 1: Vor den Playoffs ---
    if not _playoff_mode(league):
        lines = [f"🏆 Playoffs - {LEAGUES[league]['emoji']} {league}\n\nNoch nix fest! 😅\nNoch kein Team ist sicher in den Playoffs oder raus!\nSchau später nochmal vorbei!"]
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
        try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        except: pass
        return
    # Spät in der Saison: Sicher / Rennen / Raus - einfach gedacht, kein Tiebreaker!
    # Conference-Listen aus Divisionen bauen!
    divs = espn_standings(league) or {}
    _TOTAL = {"NFL": 17, "NCAAF": 12, "NHL": 82, "NBA": 82, "MLB": 162}.get(league, 17)
    _CUTOFF = {"NFL": 7, "NCAAF": 12, "NHL": 8, "NBA": 8, "MLB": 6}.get(league, 7)
    # Conference-Mapping: Key enthält Conference-Name oder Division gehört zu Conference!
    _conf_map = {
        "NFL": {"AFC": ["AFC"], "NFC": ["NFC"]},
        "MLB": {"AL": ["American", "AL "], "NL": ["National", "NL "]},
        "NHL": {"Eastern": ["Atlantic", "Metropolitan"], "Western": ["Central", "Pacific"]},
        "NBA": {"Eastern": ["Atlantic", "Central", "Southeast"], "Western": ["Northwest", "Pacific", "Southwest"]},
        "NCAAF": {"Alle": [""]},
    }.get(league, {"Alle": [""]})
    _sicher, _rennen, _raus = [], [], []
    for _conf, _keys in _conf_map.items():
        _rows = []
        for _dk, _rv in divs.items():
            if any(_k.lower() in _dk.lower() for _k in _keys) or _keys == [""]:
                for (disp, short, abbr, W, L, T, streak) in _rv:
                    _rows.append((disp, W, L, T))
        if not _rows: continue
        _rows.sort(key=lambda x: (x[1], -x[2]), reverse=True)
        _cut = _CUTOFF if len(_rows) > _CUTOFF else len(_rows)
        _cut_wins = _rows[_cut-1][1] if _cut > 0 else 0
        _next_wins = _rows[_cut][1] if len(_rows) > _cut else 0
        _next_rem = max(0, _TOTAL - (_rows[_cut][1] + _rows[_cut][2])) if len(_rows) > _cut else 0
        for _rank, (disp, W, L, T) in enumerate(_rows, 1):
            _rem = max(0, _TOTAL - (W + L + (T or 0)))
            _short = disp.split()[-1] if disp else disp
            _label = f"{disp} ({W}-{L})"
            if _rank <= _cut and W > (_next_wins + _next_rem):
                _sicher.append(_label)
            elif (_rank > _cut) and (W + _rem) < _cut_wins:
                _raus.append(_label)
            else:
                _rennen.append(_label)
    lines = [f"🏆 Playoffs - {LEAGUES[league]['emoji']} {league}\n📅 Stand: {today.strftime('%d.%m.')}\n"]
    # V80-FIX: Wenn nix sicher UND nix raus -> NUR "Noch nix fest!", KEINE Rennen-Liste!
    # Sonst: NCAAF zeigt "Noch im Rennen: 12 + 126 weitere!" + "Noch nix fest!" gleichzeitig - doppelt + sinnlos!
    # NCAAF hat 134 Teams, da ist "Noch im Rennen" ohne Sicher/Raus einfach nur eine Tabelle, kein Playoff-Bild!
    if not _sicher and not _raus:
        lines.append("\nNoch nix fest! 😅\nNoch kein Team ist sicher in den Playoffs oder raus!\nSchau später nochmal vorbei!")
    else:
        if _sicher:
            lines.append("\n✅ **Sicher in den Playoffs:**")
            lines.extend([f"• {_s}" for _s in _sicher])
        # V179: NCAAF Top 12 = ECHTE CFP Top 12 (gleiche Quelle wie CFP Top 25)! Kein Wins-Sort mehr - das hat Georgia/Alabama falsch einsortiert!
        if league == "NCAAF":
            _cfp_rows, _cfp_lbl = _espn_cfp_top25()
            if _cfp_rows:
                _u12 = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
                _favs12 = favs_for(_u12.id) if _u12 else []
                lines.append("\n🔝 **Aktuell Top 12 (CFP):**")
                for _i, (_disp, _short, _rec) in enumerate(_cfp_rows[:12], 1):
                    _show = _cfp_short(_disp, _short)  # V185: Kurz-Name wie in CFP Top 25! Texas=Longhorns!
                    _rec_txt = f" {_rec}" if _rec else ""
                    _star12 = " ⭐" if _is_fav_team(_disp, _favs12, "NCAAF") else ""
                    lines.append(f"{_i}. {_show}{_rec_txt}{_star12}")
            else:
                # Fallback: nur wenn CFP-API down ist - Wins-Sort!
                _all_sorted = []
                for _dk, _rv in divs.items():
                    for (disp, short, abbr, W, L, T, streak) in _rv:
                        _all_sorted.append((disp, W, L))
                _all_sorted.sort(key=lambda x: (x[1], -x[2]), reverse=True)
                lines.append("\n🔝 **Aktuell Top 12:**")
                for _i, (disp, W, L) in enumerate(_all_sorted[:12], 1):
                    lines.append(f"{_i}. {disp} ({W}-{L})")
        elif _rennen:
            lines.append("\n🔥 **Noch im Rennen:**")
            lines.extend([f"• {_s}" for _s in _rennen[:12]])
            if len(_rennen) > 12: lines.append(f"... und {len(_rennen)-12} weitere!")
        if _raus:
            # V179: Raus NIE alle auflisten! Nur Zahl + Favoriten, die raus sind! Vorher: 70 Teams = endloser Roman!
            lines.append(f"\n❌ **Raus:** {len(_raus)} Teams")
            try:
                _u = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
                _favs_r = favs_for(_u.id) if _u else []
                # V181: NCAAF Raus-Favoriten aus GESAMT-Bilanz (CFBD) + CFP Top 25!
                # Conference-Tabelle hat nur Conference-W/L - Pitt 2-4 ACC sah aus wie "noch drin", obwohl 3-7 gesamt raus!
                # Regel: Favorit raus, wenn NICHT in CFP Top 25 UND 3+ Niederlagen gesamt!
                if league=="NCAAF":
                    _cfp_rows_r, _ = _espn_cfp_top25()
                    _cfp_disps=[_d for (_d,_s,_r) in _cfp_rows_r]
                    _cfbd_r=_cfbd_records()
                    _fav_raus=[]
                    for _f in _favs_r:
                        _flg_f=_f.split(" (")[-1].replace(")","").strip() if " (" in _f else ""
                        if _flg_f and _flg_f!=league: continue
                        _fname=_f.split(" (")[0].strip()
                        # In CFP Top 25? Dann NICHT raus!
                        if any(_is_fav_team(_cd, [_f], "NCAAF") for _cd in _cfp_disps): continue
                        _ov=_cfbd_overall_for(_fname, _cfbd_r)
                        if _ov and _ov[1]>=3:
                            _fav_raus.append(f"{_fname} ({_ov[0]}-{_ov[1]})")
                        elif not _ov:
                            # Fallback: alte _raus-Liste, wenn CFBD down ist!
                            for _r in _raus:
                                if _is_fav_team(_r, [_f], league): _fav_raus.append(_r); break
                else:
                    _fav_raus = [_r for _r in _raus if _is_fav_team(_r, _favs_r, league)]
                # V184: GELÖSCHT! Stand schon im Favoriten-Block unten doppelt!
            except: pass
    # V182: ⭐ Deine Favoriten - Was brauchen sie noch?
    try:
        _u2 = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
        _favs2 = favs_for(_u2.id) if _u2 else []
        if _favs2:
            _f_lines=["\n⭐ **Deine Favoriten - Playoff-Stand:**"]
            if league=="NCAAF":
                _cfp_r2,_=_espn_cfp_top25()
                _rank_map={_d.lower():_i for _i,(_d,_s,_r) in enumerate(_cfp_r2,1)}
                _cfbd2=_cfbd_records()
                for _f in _favs2:
                    _flg2=_f.split(" (")[-1].replace(")","").strip() if " (" in _f else ""
                    if _flg2 and _flg2!=league: continue
                    _fname2=_f.split(" (")[0].strip()
                    _rank2=None
                    for _cd,_ri in _rank_map.items():
                        if _is_fav_team(_cd, [_f], "NCAAF"): _rank2=_ri; break
                    _ov2=_cfbd_overall_for(_fname2, _cfbd2)
                    if _rank2 and _rank2<=12:
                        _rem2=max(0,12-((_ov2[0]+_ov2[1]) if _ov2 else 10))
                        _f_lines.append(f"• {_cfp_short(_fname2, '')} - Top 12 (#{_rank2}) - drin! {_rem2} Spiele noch")
                    elif _rank2 and _rank2<=25:
                        _f_lines.append(f"• {_cfp_short(_fname2, '')} - CFP #{_rank2} - noch im Rennen, braucht Siege + Hilfe!")
                    elif _ov2 and _ov2[1]>=3:
                        _f_lines.append(f"• {_cfp_short(_fname2, '')} ({_ov2[0]}-{_ov2[1]}) - raus 😔")
                    else:
                        _f_lines.append(f"• {_cfp_short(_fname2, '')} - noch im Rennen!")
            else:
                for _f in _favs2:
                    _flg2=_f.split(" (")[-1].replace(")","").strip() if " (" in _f else ""
                    if _flg2 and _flg2!=league: continue
                    _fname2=_f.split(" (")[0].strip()
                    _st="noch im Rennen!"
                    if any(_is_fav_team(_s, [_f], league) for _s in _sicher): _st="sicher in den Playoffs! ✅"
                    elif any(_is_fav_team(_s, [_f], league) for _s in _raus): _st="raus 😔"
                    _f_lines.append(f"• {_fname2} - {_st}")
            lines.extend(_f_lines)
    except: pass
    # V83: NCAAF CFP -> Bowl-Button dazu!
    if league == "NCAAF" and force_cfp:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🥣 Bowl Games", callback_data="playoffs_bowls:NCAAF")], [InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        await _loading_done(ctx, _uid_pl, _load_pl)
        _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
        try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        except: pass
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
    await _loading_done(ctx, _uid_pl, _load_pl)
    _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
async def tables_all_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏈 NFL", callback_data="tables_league:NFL"),
         InlineKeyboardButton("🎓 NCAAF", callback_data="tables_league:NCAAF")],
        [InlineKeyboardButton("🏒 NHL", callback_data="tables_league:NHL"),
         InlineKeyboardButton("🏀 NBA", callback_data="tables_league:NBA")],
        [InlineKeyboardButton("⚾ MLB", callback_data="tables_league:MLB")],
        [InlineKeyboardButton("⭐ Nur meine Favoriten", callback_data="tables_mine")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "📊 Tabellen - Alle Ligen\n\nWelche Liga?", kb)
async def tables_league_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str):
    target = update.message or update.callback_query.message
    _load = None
    try: _load = await target.reply_text(f"📊 Ich hole die {league} Tabelle... einen Moment ⏳")
    except Exception: pass
    divs = espn_standings(league)
    try:
        if _load: await ctx.bot.delete_message(chat_id=update.effective_user.id, message_id=_load.message_id)
    except Exception: pass
    if not divs:
        dbg = _STANDINGS_DEBUG
        await target.reply_text(f"Keine Tabelle gefunden - versuch es später nochmal.\n\nDebug: Status {dbg.get('last_status')} | Keys: {dbg.get('last_keys')} | URL: {dbg.get('last_url')}", reply_markup=small_kb()); return
    ctx.user_data["tables_divs_"+league]=divs
    # NCAAF: nur Top 25, keine Division-Auswahl
    if league=="NCAAF":
        await tables_top25_cmd(update, ctx, league, divs); return
    # Division / Conference Buttons: 2 pro Reihe
    rows=[]
    # NBA/NHL: Conference-Buttons nur wenn divs wirklich Divisionen sind (Atlantic, Metropolitan, ...), NICHT wenn divs schon Eastern/Western sind!
    # Sonst: Doppelte Buttons (Eastern Conference + Eastern) und "Conference nicht gefunden"!
    _has_conf_keys = any(k.lower() in ("eastern","western","eastern conference","western conference") for k in divs.keys())
    if league in ("NBA","NHL") and not _has_conf_keys:
        rows.append([InlineKeyboardButton("Eastern Conference", callback_data=f"tables_conf:{league}:Eastern"),
                     InlineKeyboardButton("Western Conference", callback_data=f"tables_conf:{league}:Western")])
    keys = sorted(divs.keys())
    def _short_div(k):
        # "American Football Conference" -> "AFC", "National Football Conference" -> "NFC"
        # "AFC East" bleibt, "American Football Conference East" -> "AFC East"
        kk = k.replace("American Football Conference", "AFC").replace("National Football Conference", "NFC")
        kk = kk.replace("American Football", "AFC").replace("National Football", "NFC")
        kk = kk.replace("Eastern Conference", "East").replace("Western Conference", "West")
        return kk.strip()
    for i in range(0, len(keys), 2):
        row=[]
        for k in keys[i:i+2]:
            row.append(InlineKeyboardButton(f"{_short_div(k)}", callback_data=f"tables_div:{league}:{k}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")])
    rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
    kb = InlineKeyboardMarkup(rows)
    await target.reply_text(f"📊 Tabelle - {LEAGUES[league]['emoji']} {league}\n\nWelche Division / Conference?\nNur 1 Division = übersichtlich, 4-8 Teams!", reply_markup=kb)
async def tables_div_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str, div: str):
    target = update.message or update.callback_query.message
    divs = ctx.user_data.get("tables_divs_"+league)
    if not divs:
        divs = espn_standings(league)
        ctx.user_data["tables_divs_"+league]=divs
    rows = list(divs.get(div, []))
    if not rows:
        await target.reply_text("Division nicht gefunden.", reply_markup=small_kb()); return
    # V134: Sortieren! MLB/NFL/NBA nach Wins, NHL nach Punkten - sonst steht Brewers 103-59 auf Platz 15!
    if league=="NHL":
        def _pts2(x):
            try:
                s=str(x[6] or "")
                return int(s.split("•")[-1].replace("PTS","").strip()) if "PTS" in s else 0
            except: return 0
        rows.sort(key=lambda x: (_pts2(x), x[3]), reverse=True)
    else:
        rows.sort(key=lambda x: (x[3], -x[4]), reverse=True)
    favs = favs_for(update.effective_user.id) if update.effective_user else []
    fav_names = [f.split(" (")[0].strip().lower() for f in favs]
    div_short = div.replace("American Football Conference", "AFC").replace("National Football Conference", "NFC").replace("American Football", "AFC").replace("National Football", "NFC").strip()
    _conf_note=" (Gesamt-Record)" if league=="NCAAF" else ""
    lines=[f"📊 Tabelle - {LEAGUES[league]['emoji']} {league} - {div_short}{_conf_note}\n"]
    for i,(disp, short, abbrev, W, L, T, streak) in enumerate(rows,1):
        rec = f"{W}-{L}" + (f"-{T}" if T else "")
        is_fav = any(fn in disp.lower() or disp.lower() in fn for fn in fav_names)
        star = " ⭐" if is_fav else ""
        streak_s = f" ({streak})" if streak and streak not in ("-", "0") else ""
        # Kurz: "1. Steelers 7-2 ⭐ (W3)" - 1 Zeile pro Team!
        lines.append(f"{i}. {short} {rec}{star}{streak_s}")
    if league=="NHL":
        lines.append("")
        lines.append(NHL_LEGEND_SHORT)
    # V214: Zahl tippen = Team-Fenster! Liste merken (sortiert, wie angezeigt)!
    lines.append("")
    lines.append("💡 Zahl tippen = Team-Fenster! (z.B. 1 für Platz 1)")
    try: ctx.user_data["tables_team_list"] = {"league": league, "div": div, "rows": list(rows), "back": f"tables_div:{league}:{div}"}; ctx.user_data["await_live_stats_pick"] = False  # V246: Live-Flag aus! Diese Liste gewinnt jetzt!
    except: pass
    _kb_rows = [[InlineKeyboardButton("📊 Andere Division", callback_data=f"tables_league:{league}")], [InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]]
    if league=="NHL":
        _kb_rows.append([InlineKeyboardButton("❓ Was bedeutet W-L-OTL / OT1?", callback_data="nhl_help")])
    _kb_rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    kb = InlineKeyboardMarkup(_kb_rows)
    _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
async def tables_conf_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str, conf: str):
    target = update.message or update.callback_query.message
    divs = ctx.user_data.get("tables_divs_"+league)
    if not divs:
        divs = espn_standings(league)
        ctx.user_data["tables_divs_"+league]=divs
    confs = standings_conferences(league, divs)
    rows = list(confs.get(conf, []))
    # V134: MLB Conference (NL/AL) muss auch sortiert werden!
    if league=="MLB":
        rows.sort(key=lambda x: (x[3], -x[4]), reverse=True)
    if not rows:
        await target.reply_text("Conference nicht gefunden.", reply_markup=small_kb()); return
    favs = favs_for(update.effective_user.id) if update.effective_user else []
    fav_names = [f.split(" (")[0].strip().lower() for f in favs]
    lines=[f"📊 Tabelle - {LEAGUES[league]['emoji']} {league} - {conf} Conference\n"]
    for i,(disp, short, abbrev, W, L, T, streak) in enumerate(rows,1):
        rec = f"{W}-{L}" + (f"-{T}" if T else "")
        is_fav = any(fn in disp.lower() or disp.lower() in fn for fn in fav_names)
        star = " ⭐" if is_fav else ""
        # V66-FIX: Auch in Conference-Ansicht Streak/Punkte zeigen! Vorher fehlten PTS komplett!
        streak_s = f" ({streak})" if streak and streak not in ("-", "0") else ""
        # Playoff-Strich bei NBA/NHL: Top 8 = Playoffs, 9-10 = Play-In (NBA) / Top 8 Playoffs (NHL)
        marker = ""
        if league=="NBA" and i==8: marker=" — Playoff-Platz"
        if league=="NBA" and i==10: marker=" — Play-In"
        if league=="NHL" and i==8: marker=" — Playoff-Platz"
        lines.append(f"{i}. {short} {rec}{star}{streak_s}{marker}")
    if league=="NHL":
        lines.append("")
        lines.append(NHL_LEGEND_SHORT)
    # V214: Zahl tippen = Team-Fenster!
    lines.append("")
    lines.append("💡 Zahl tippen = Team-Fenster! (z.B. 1 für Platz 1)")
    try: ctx.user_data["tables_team_list"] = {"league": league, "div": conf, "rows": list(rows), "back": f"tables_conf:{league}:{conf}"}; ctx.user_data["await_live_stats_pick"] = False  # V246: Live-Flag aus! Diese Liste gewinnt jetzt!
    except: pass
    _kb_rows2 = [[InlineKeyboardButton("📊 Andere Division", callback_data=f"tables_league:{league}")], [InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]]
    if league=="NHL":
        _kb_rows2.append([InlineKeyboardButton("❓ Was bedeutet W-L-OTL / OT1?", callback_data="nhl_help")])
    _kb_rows2.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    kb = InlineKeyboardMarkup(_kb_rows2)
    _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
async def tables_top25_cmd(update, ctx, league: str, divs):
    target = update.message or update.callback_query.message
    top = _espn_ap_top25()
    _official = bool(top)
    if not top:
        all_rows=[]
        for k,v in (divs or {}).items(): all_rows.extend(v)
        def _pct(x):
            W,L=x[3],x[4]; tot=W+L
            return (W/tot if tot else 0, W)
        all_rows.sort(key=lambda x: _pct(x), reverse=True)
        top = all_rows[:25]
    favs = favs_for(update.effective_user.id) if update.effective_user else []
    fav_names = [f.split(" (")[0].strip().lower() for f in favs]
    _tag = "AP Top 25 (offiziell)" if _official else "Top 25"
    lines=[f"📊 Tabelle - 🎓 NCAAF - {_tag}\n"]
    for i,(disp, short, abbrev, W, L, T, streak) in enumerate(top,1):
        rec = f"{W}-{L}" + (f"-{T}" if T else "")
        dl=(disp or "").lower()
        is_fav = bool(dl) and any(fn and (fn in dl or dl in fn) for fn in fav_names)
        star = " ⭐" if is_fav else ""
        _show = short or disp
        lines.append(f"{i}. {_show} {rec}{star}")
    # V214: Zahl tippen = Team-Fenster!
    lines.append("")
    lines.append("💡 Zahl tippen = Team-Fenster! (z.B. 1 für Platz 1)")
    try: ctx.user_data["tables_team_list"] = {"league": league, "div": "Top 25", "rows": list(top), "back": "tables_league:NCAAF"}; ctx.user_data["await_live_stats_pick"] = False  # V246: Live-Flag aus! Diese Liste gewinnt jetzt!
    except: pass
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")],[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")],])
    _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
def _ncaaf_team_overall(team_full):
    # V141: CFBD zuerst (Navy 8-2, nicht 0-1 / 3-6!), dann Scoreboard, nie Schedule!
    try:
        _c=_cfbd_overall_for(team_full)
        if _c: return _c
        rec=_ncaaf_records_from_scoreboard()
        if rec:
            low=(team_full or "").lower()
            for k,v in rec.items():
                if low in k.lower() or k.lower() in low:
                    if v[0]+v[1]>0: return (v[0],v[1])
        return None
    except: return None
async def tables_mine_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs = favs_for(user.id) if user else []
    if not favs:
        await target.reply_text("Du hast noch keine Favoriten. Füge erst ein Team hinzu, dann zeige ich dir hier deine Tabellen!", reply_markup=small_kb()); return
    _load2=None
    try: _load2 = await target.reply_text("📊 Ich hole deine Tabellen... einen Moment ⏳")
    except Exception: pass
    lines=["📊 Deine Teams - Tabellen\n⭐ = Dein Team\n"]
    # V144: Wenn CFBD-Key fehlt, zeigt ESPN bei NCAAF nur Conference! Warnung anzeigen!
    try:
        import os as _os
        if not _os.getenv("CFBD_API_KEY") and not _cfbd_records():
            lines.append("⚠️ NCAAF: Ohne CFBD-Key zeigt ESPN nur Conference! Key in Render als CFBD_API_KEY eintragen!\n")
    except Exception: pass
    # Für jeden Favorit: seine Division finden und zeigen
    for f in favs:
        name = f.split(" (")[0].strip()
        lg = f.split(" (")[-1].replace(")", "").strip() if " (" in f else None
        if not lg or lg not in LEAGUES: continue
        divs = espn_standings(lg)
        if not divs: continue
        # Division finden, wo das Team drin ist
        found=None
        for div, rows in divs.items():
            for (disp, short, abbrev, W, L, T, streak) in rows:
                if name.lower() in disp.lower() or disp.lower() in name.lower():
                    found=(div, rows); break
            if found: break
        if not found: continue
        div, rows = found
        div_s = div.replace("American Football Conference", "AFC").replace("National Football Conference", "NFC").replace("American Football", "AFC").replace("National Football", "NFC").strip()
        # V138: NCAAF Meine Favoriten = Gesamt-Record für dein Team! Rest = Conference-Record!
        _overall_note=""
        if lg=="NCAAF":
            _ov=_ncaaf_team_overall(name)
            if _ov:
                _new_rows=[]
                for _r in rows:
                    if name.lower() in _r[0].lower() or _r[0].lower() in name.lower():
                        _new_rows.append((_r[0],_r[1],_r[2],_ov[0],_ov[1],_r[5],_r[6]))
                    else: _new_rows.append(_r)
                rows=_new_rows
                _overall_note=" (Alle = Gesamt-Record)"
        # V216: Reihen in "Meine Teams" richtig SORTIEREN! Vorher: ESPN-Reihenfolge (MLB: Brewers 103-59 ganz unten!)!
        # Sort: NHL nach Punkten (aus Streak "W2 \u2022 32 PTS"), Rest nach Siegquote, dann Wins!
        try:
            if lg == "NHL":
                def _v216_pts(_r):
                    try:
                        _s = str(_r[6] or "")
                        if "PTS" in _s: return int(_s.split("\u2022")[-1].replace("PTS", "").strip())
                    except: pass
                    return 0
                rows = sorted(rows, key=lambda _r: (_v216_pts(_r), _r[3]), reverse=True)
            else:
                def _v216_pct(_r):
                    _tot = _r[3] + _r[4] + _r[5]
                    return ((_r[3] / _tot) if _tot else 0, _r[3], -_r[4])
                rows = sorted(rows, key=_v216_pct, reverse=True)
        except: pass
        lines.append(f"\n{LEAGUES[lg]['emoji']} {lg} - {div_s}{_overall_note}")
        for i,(disp, short, abbrev, W, L, T, streak) in enumerate(rows,1):
            rec = f"{W}-{L}" + (f"-{T}" if T else "")
            is_fav = name.lower() in disp.lower() or disp.lower() in name.lower()
            star = " ⭐" if is_fav else ""
            streak_s = f" ({streak})" if streak and streak not in ("-", "0") else ""
            lines.append(f"{i}. {short} {rec}{star}{streak_s}")
    if len(lines)<=2:
        lines.append("Keine Tabellen für deine Favoriten gefunden.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Alle Tabellen", callback_data="tables")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")],
    ])
    try:
        if _load2: await ctx.bot.delete_message(chat_id=update.effective_user.id, message_id=_load2.message_id)
    except Exception: pass
    _m201 = await target.reply_text("\n".join(lines), reply_markup=kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
async def next_hub_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Heute", callback_data="next_today")],  # V210: Liga wird danach gewaehlt!
        [InlineKeyboardButton("📅 Morgen", callback_data="next_tomorrow")],
        [InlineKeyboardButton("⭐ Nur meine Favoriten", callback_data="next_mine")],
        [InlineKeyboardButton("❓ Hilfe", callback_data="help")],  # V227: "Live für ein Spiel"-Button RAUS! Geht jetzt über Heute/Morgen + Zahl!
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "⏭️ Next Games\n\nWas willst du sehen?\n📅 Heute / Morgen = alle Spiele, auch ohne Favoriten!\n⭐ Nur meine Favoriten = wann spielen DEINE Teams als Nächstes?\n✍️ In Heute/Morgen: Zahl vom Spiel schreiben = Details + Benachrichtigungen!", kb)  # V227: Zahlen-Weg!
async def next_mine_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs = favs_for(user.id) if user else []
    lines=["⏭️ Next Games - Deine Favoriten\n"]
    grouped = {}  # V69: Datum -> [(dt, league, ev, disp)]
    if not favs:
        lines.append("Du hast noch keine Favoriten. Füge erst ein Team hinzu, dann zeige ich dir hier das nächste Spiel pro Team.")
        await target.reply_text("\n".join(lines), reply_markup=small_kb()); return
    # Favoriten-Namen ohne "(NFL)" hinten dran + Liga dazu!
    # WICHTIG: Nur Vollname in der richtigen Liga matchen! "Pirates" allein würde sonst auch
    # East Carolina Pirates (NCAAF) als Pittsburgh Pirates (MLB) verkaufen! Spitzname nur als Fallback mit Vollname-Check.
    fav_list=[]  # [(anzeige, liga, [suchbegriffe], vollname)]
    for f in favs:
        name = f.split(" (")[0].strip()
        lg = f.split(" (")[-1].replace(")", "").strip() if " (" in f else None
        terms=[name.lower()]
        fav_list.append((f, lg, terms, name.lower()))
    # Nächste 14 Tage durchsuchen - nicht nur heute! Samstag Longhorns, Sonntag Steelers etc.
    from datetime import date as _date
    today=_date.today()
    all_events=[]  # (datum, league, ev, fav_anzeige)
    seen_ids=set()
    # V143: AUCH GESTERN suchen! SNF 02:20 DE-Zeit = 15.11. USA-Zeit! Bot ab 16.11. DE hätte Bengals sonst verpasst!
    # Nur Spiele, die wirklich noch nicht angefangen / noch nicht fertig sind (dt >= jetzt - 3h, sonst alte Finals von gestern)!
    from datetime import datetime as _dt_now
    _now_berlin=_dt_now.now(BERLIN)
    for league in LEAGUES:
        for offset in range(-1, 15):
            d = today + timedelta(days=offset)
            ds = d.strftime("%Y%m%d")
            for ev in espn_scoreboard(league, dates=ds):
                eid = ev.get("id")
                if eid in seen_ids: continue
                seen_ids.add(eid)
                # Nur zukünftige / heutige Spiele, keine fertigen
                state = ev.get("status",{}).get("type",{}).get("state","")
                if state=="post": continue
                # V143: Gestern-Spiele nur, wenn Anpfiff noch nicht 3h+ her ist (sonst alte Spiele von gestern)!
                try:
                    _, _dt_ev = fmt_dt(ev.get("date",""))
                    if _dt_ev and _dt_ev < _now_berlin - timedelta(hours=3) and state!="in":
                        continue
                except Exception:
                    pass
                teams,_ = event_teams(ev)
                team_text = " ".join([x[0] for x in teams]).lower()
                for disp, lg, terms, fullname in fav_list:
                    # Nur in der gleichen Liga! Pittsburgh Pirates (MLB) darf nicht East Carolina Pirates (NCAAF) matchen!
                    if lg and lg != league: continue
                    if any(tm in team_text for tm in terms):
                        # Extra-Sicherheit: Bei gleichem Spitznamen (Pirates, Panthers, etc.) muss der VOLLE Name drin stehen,
                        # nicht nur der Spitzname! "east carolina pirates" enthält nicht "pittsburgh pirates" -> kein Match!
                        # Ausnahme: Wenn der Vollname aus nur 2 Wörtern besteht und das Team genau so heißt, reicht Vollname.
                        # Hier: Wir verlangen Vollname-Match, wenn der Vollname in einer anderen Liga auch vorkommt.
                        if fullname not in team_text:
                            # Vollname nicht drin -> nur Spitzname-Match, das ist zu unsicher bei Pirates/Panthers/etc.
                            # Wir erlauben Spitzname-Match nur, wenn kein anderes Team in dieser Liga den gleichen Spitznamen hat.
                            # Einfachste sichere Regel: Nur Vollname zählt!
                            continue
                        _, dt = fmt_dt(ev.get("date",""))
                        all_events.append((dt or datetime.now(BERLIN), league, ev, disp))
                        break
    # Sortiert nach Datum, pro Favorit nur das nächste Spiel
    all_events.sort(key=lambda x: x[0])
    shown=set()
    for dt, league, ev, disp in all_events:
        if disp in shown: continue
        shown.add(disp)
        # V69: Kein doppelter Team-Name mehr! Nach Tag gruppieren!
        day_key = dt.date() if dt else None
        grouped.setdefault(day_key, []).append((dt, league, ev, disp))
    # --- Off-Season / Preseason: Wenn ein Favorit in 14 Tagen kein Spiel hat, weiter suchen bis 180 Tage ---
    # z.B. Pirates: Spring Training im Feb schon bekannt -> direkt anzeigen statt nur Meister!
    missing = [(disp, terms) for disp, lg, terms, fullname in fav_list if disp not in shown]
    if missing:
        # Pro Liga einmalig in 30-Tage-Blöcken bis 180 Tage suchen (ESPN Range: YYYYMMDD-YYYYMMDD)
        for disp, terms in missing:
            # Liga aus "Team (LIGA)" holen
            lg = disp.split(" (")[-1].replace(")", "").strip() if " (" in disp else None
            if lg not in LEAGUES: continue
            found_pre=None
            for chunk_start in [14, 44, 74, 104, 134, 164]:
                s = today + timedelta(days=chunk_start)
                e = today + timedelta(days=chunk_start+29)
                rng = f"{s.strftime('%Y%m%d')}-{e.strftime('%Y%m%d')}"
                for ev in espn_scoreboard(lg, dates=rng):
                    state = ev.get("status",{}).get("type",{}).get("state","")
                    if state=="post": continue
                    teams,_ = event_teams(ev)
                    team_text = " ".join([x[0] for x in teams]).lower()
                    if any(tm in team_text for tm in terms):
                        _, dt = fmt_dt(ev.get("date",""))
                        # Preseason-Label aus ESPN season type, z.B. "Pre-Season" / "Spring Training"
                        season_name = (ev.get("season",{}) or {}).get("type",{}).get("name","") or (ev.get("season",{}) or {}).get("slug","") or ""
                        is_pre = any(k in season_name.lower() for k in ["pre", "spring", "exhibition"]) or chunk_start>=14 and dt and (dt - datetime.now(BERLIN)).days>21 and lg=="MLB"
                        found_pre=(dt, lg, ev, disp, is_pre, season_name)
                        break
                if found_pre: break
            if found_pre:
                dt, lg2, ev, disp2, is_pre, season_name = found_pre
                shown.add(disp2)
                weekday = ["Mo","Di","Mi","Do","Fr","Sa","So"][dt.weekday()] if dt else ""
                # Label: 🌱 Spring Training bei MLB, sonst 🏋️ Preseason
                if lg2=="MLB" and is_pre: pre_label = "🌱 Spring Training"
                elif is_pre: pre_label = "🏋️ Preseason"
                else: pre_label = "⏭️ Nächstes Spiel"
                day_key2 = dt.date() if dt else None
                grouped.setdefault(day_key2, []).append((dt, lg2, ev, disp2))
    # V69: Gruppierte Anzeige: Nach Tag! ⭐ = Dein Team!
    for day_key in sorted([k for k in grouped.keys() if k is not None]):
        items = sorted(grouped[day_key], key=lambda x: x[0] or datetime.now(BERLIN))
        dt0 = items[0][0]
        wd = ["Mo","Di","Mi","Do","Fr","Sa","So"][dt0.weekday()] if dt0 else ""
        lines.append(f"\n**{wd} {day_key.strftime('%d.%m.')}**")
        for dt, league, ev, disp in items:
            # V142: ⭐ MUSS vor DEINEM Team stehen, nicht immer vor Auswärtsteam!
            # Blues @ Penguins -> Penguins ist Favorit -> "Blues @ ⭐ Penguins" (vorher falsch: "⭐ Blues @ Penguins")!
            _line=game_line(ev, league, show_broadcast=True)
            try:
                _fav_name=disp.split(" (")[0].strip().lower()
                _teams2,_c2=event_teams(ev)
                _away_full=""; _home_full=""
                for _t in _teams2:
                    _nm=str(_t[0] or "")
                    _ha=str(_t[1] or "").lower() if len(_t)>1 else ""
                    if _ha=="home": _home_full=_nm.lower()
                    elif _ha=="away": _away_full=_nm.lower()
                if _fav_name and _fav_name in _home_full and " @ " in _line:
                    _a,_b=_line.split(" @ ",1)
                    _line=f"{_a} @ ⭐ {_b}"
                else:
                    _line=f"⭐ {_line}"
            except Exception:
                _line=f"⭐ {_line}"
            lines.append(_line)
    if not shown:
        lines.append("Keine kommenden Spiele für deine Favoriten gefunden - auch keine Preseason / Spring Training Daten bei ESPN.")
        lines.append("Aktueller Meister:")
        for lg,ch in CHAMPIONS.items():
            if any(lg in f for f in favs):
                lines.append(f"{LEAGUES[lg]['emoji']} {lg}: {ch['team']} ({ch['year']}) - {ch['result']}")
    _kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏥 Verletzungen meiner Teams", callback_data="injuries_mine")], [InlineKeyboardButton("ℹ️ Mehr Infos zu den Spielen", callback_data="game_info_leagues")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
    _m201 = await target.reply_text("\n".join(lines), reply_markup=_kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
async def injuries_mine_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs = favs_for(user.id) if user else []
    _now = datetime.now(BERLIN)
    lines = [f"🏥 Verletzungen — Meine Teams\n📅 Stand: {_now.strftime('%d.%m. %H:%M')}\nℹ️ Bis zu 15 Min verzögert!"]
    if not favs:
        lines.append("Du hast noch keine Favoriten.")
        await target.reply_text("\n".join(lines), reply_markup=small_kb()); return
    _has_ncaaf = False; _ir_buttons = []
    lines.append("Quelle: Sleeper (NFL) / ESPN (NBA, NHL, MLB)")
    for f in favs:
        _name = f.split(" (")[0].strip()
        _lg = f.split(" (")[-1].replace(")", "").strip() if " (" in f else None
        if _lg not in LEAGUES: continue
        lines.append(f"\n**{LEAGUES[_lg]['emoji']} {_name}:**")
        if _lg == "NCAAF":
            _has_ncaaf = True; lines.append("• Keine Verletzungsliste!"); continue
        if not _league_in_season(_lg):
            lines.append(f"• Saison vorbei! 🏖️\n• Nächste Saison: {LEAGUE_NEXT.get(_lg, '')}"); continue
        _inj, _has_data = _team_injuries_with_status(_lg, _name)
        if not _has_data: lines.append("• Keine Daten gefunden!")
        elif not _inj: lines.append("• Keine Verletzten! 🎉")
        else:
            for _x in _inj: lines.append(f"• {_x}")
        if _lg == "NFL":
            _g2, _ir2, _h2 = _sleeper_split(_name)
            if _ir2:
                lines.append(f"ℹ️ + {len(_ir2)} auf IR (Langzeit)")
                _ir_buttons.append([InlineKeyboardButton(f"🏥 IR-Liste {_name} ({len(_ir2)})", callback_data=f"injuries_ir:NFL:{_name}")])
    if _has_ncaaf: lines.append("\nℹ️ NCAAF: Keine Liste! Für College gibt's keinen offiziellen Injury Report, deswegen listen wir da nix auf!")
    _kb_rows = _ir_buttons + [[InlineKeyboardButton("⏭️ Nächste Spiele", callback_data="next_mine")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]]
    _m201 = await target.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(_kb_rows))
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
async def injuries_ir_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str, team_full: str):
    target = update.message or update.callback_query.message
    _g, _ir, _has = _sleeper_split(team_full) if league == "NFL" else ([], [], False)
    if not _has or not _ir:
        await target.reply_text(f"🏥 IR-Liste — {team_full}\n\nKeine IR-Spieler gefunden.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Verletzungen", callback_data="injuries_mine")]])); return
    lines = [f"🏥 IR-Liste — {team_full} ({len(_ir)})\n"]
    for _x in _ir: lines.append(f"• {_x}")
    await target.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Verletzungen", callback_data="injuries_mine")]]))
def _fav_next_games(user_id):
    _favs = favs_for(user_id); _out=[]; _seen=set()
    from datetime import date as _date
    _today=_date.today()
    for _lg in LEAGUES:
        for _off in range(0,15):
            _d=_today+timedelta(days=_off); _ds=_d.strftime("%Y%m%d")
            for _ev in espn_scoreboard(_lg, dates=_ds):
                _eid=_ev.get("id")
                if _eid in _seen: continue
                _seen.add(_eid)
                if _ev.get("status",{}).get("type",{}).get("state","")=="post": continue
                _teams,_=event_teams(_ev); _txt=" ".join([x[0] for x in _teams]).lower()
                for _f in _favs:
                    _nm=_f.split(" (")[0].strip(); _l2=_f.split(" (")[-1].replace(")","").strip() if " (" in _f else None
                    if _l2 and _l2!=_lg: continue
                    if _nm.lower() in _txt:
                        _,_dt=fmt_dt(_ev.get("date",""))
                        _out.append((_dt or datetime.now(BERLIN),_lg,_ev,_f)); break
    _out.sort(key=lambda x: x[0]); _seen_f=set(); _res=[]
    for _x in _out:
        if _x[3] in _seen_f: continue
        _seen_f.add(_x[3]); _res.append(_x)
    return _res
async def game_info_leagues_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target=update.message or update.callback_query.message
    user=update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    _games=_fav_next_games(user.id) if user else []
    if not _games:
        await target.reply_text("ℹ️ Mehr Infos — Keine kommenden Spiele deiner Favoriten gefunden.", reply_markup=small_kb()); return
    ctx.user_data["game_info_events"]={str(_ev.get("id")): _ev for _,_lg,_ev,_f in _games}
    ctx.user_data["game_info_league"]={str(_ev.get("id")): _lg for _,_lg,_ev,_f in _games}
    _by={}
    for _dt,_lg,_ev,_f in _games: _by.setdefault(_lg,[]).append(_ev)
    _rows=[[InlineKeyboardButton(f"{LEAGUES[_lg]['emoji']} {_lg} ({len(_v)})", callback_data=f"game_info_games:{_lg}")] for _lg,_v in _by.items()]
    _rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    await _cb_edit(update, "ℹ️ Mehr Infos zu den Spielen\n\nWelche Liga?", InlineKeyboardMarkup(_rows))
async def game_info_games_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str):
    target=update.message or update.callback_query.message
    _all=_fav_next_games(update.effective_user.id)
    _filt=[x for x in _all if x[1]==league]
    if not _filt:
        await target.reply_text("Keine Spiele in dieser Liga.", reply_markup=small_kb()); return
    _load = await _loading_start(target, "⏳ Ich hole die Spiele... einen Moment")
    _rows=[]
    for _dt,_lg,_ev,_f in _filt:
        _rows.append([InlineKeyboardButton(f"{game_line(_ev,_lg,show_broadcast=False)[:60]}", callback_data=f"game_info_detail:{_ev.get('id')}")])
    _rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="game_info_leagues")])
    try: await _loading_done(ctx, update.effective_user.id if update.effective_user else 0, _load)
    except: pass
    await _cb_edit(update, f"ℹ️ Mehr Infos — {LEAGUES[league]['emoji']} {league}\n\nWelches Spiel?", InlineKeyboardMarkup(_rows))
def _team_form(league, team_full):
    try:
        from datetime import date as _date
        _today=_date.today(); _res=[]
        for _off in range(1,31):
            _d=_today-timedelta(days=_off); _ds=_d.strftime("%Y%m%d")
            for _ev in espn_scoreboard(league, dates=_ds):
                if _ev.get("status",{}).get("type",{}).get("state","")!="post": continue
                _teams,_=event_teams(_ev); _txt=" ".join([x[0] for x in _teams]).lower()
                if team_full.lower() not in _txt: continue
                _sc={x[0]:(int(x[2]) if str(x[2]).isdigit() else 0) for x in _teams}
                _my=_sc.get(team_full,0); _opp=max([v for k,v in _sc.items() if k!=team_full] or [0])
                _res.append("W" if _my>_opp else "L")
                if len(_res)>=5: return "-".join(_res)
        return "-".join(_res) if _res else "Keine Daten"
    except Exception: return "Keine Daten"
async def game_info_detail_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, eid: str):
    target=update.message or update.callback_query.message
    _ev=(ctx.user_data.get("game_info_events",{}) or {}).get(str(eid))
    _lg=(ctx.user_data.get("game_info_league",{}) or {}).get(str(eid))
    if not _ev or not _lg:
        await target.reply_text("Spiel nicht mehr gefunden. Bitte nochmal über Next Games öffnen.", reply_markup=small_kb()); return
    _load = await _loading_start(target, "⏳ Ich hole die Spiel-Infos... einen Moment")
    _teams,_comp=event_teams(_ev)
    _home=next((x for x in _teams if (x[1] or "").lower()=="home"), _teams[1] if len(_teams)>1 else _teams[0])
    _away=next((x for x in _teams if (x[1] or "").lower()=="away"), _teams[0])
    _venue=((_comp.get("venue",{}) or {}).get("fullName","") or "")
    _date_s,_dt=fmt_dt(_ev.get("date",""))
    lines=[f"ℹ️ {_away[0]} @ {_home[0]} — {_date_s} Uhr\n"]
    if _venue: lines.append(f"📍 {_venue}")
    lines.append(f"{game_line(_ev,_lg,show_broadcast=True)}")
    lines.append("🌦️ Wetter: Keine Daten")
    lines.append("\n**Wer fehlt?**")
    for _tm in [_away[0],_home[0]]:
        _inj,_has=_team_injuries_with_status(_lg,_tm)
        if _lg=="NCAAF": lines.append(f"{_tm}: Keine Verletzungsliste (kein offizieller Report)")
        elif not _league_in_season(_lg): lines.append(f"{_tm}: Saison vorbei!")
        elif not _has: lines.append(f"{_tm}: Keine Daten gefunden!")
        elif not _inj: lines.append(f"{_tm}: Keine Verletzten! 🎉")
        else:
            for _x in _inj[:4]: lines.append(f"{_tm}: {_x}")
    lines.append("\n**Form (letzte Spiele):**")
    lines.append(f"{_away[0]}: {_team_form(_lg,_away[0])}")
    lines.append(f"{_home[0]}: {_team_form(_lg,_home[0])}")
    lines.append("\n**Letztes Duell:**")
    lines.append("Keine Daten — wird noch ausgebaut!")
    lines.append("\n**Was steht auf dem Spiel?**")
    lines.append("Playoffs kommen näher – jeder Sieg zählt! Keine Wetten, nur Sport! 😅")
    try: await _loading_done(ctx, update.effective_user.id if update.effective_user else 0, _load)
    except: pass
    await target.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu den Spielen", callback_data="game_info_leagues")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]]))
async def fav_remove_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target=update.message or update.callback_query.message
    _favs=favs_for(update.effective_user.id)
    if not _favs:
        await target.reply_text("Noch keine Favoriten.", reply_markup=small_kb()); return
    _rows=[[InlineKeyboardButton(f"❌ {_f}", callback_data=f"fav_del:{_i}")] for _i,_f in enumerate(_favs)]
    _rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    await target.reply_text("🗑️ Welchen Favorit willst du entfernen?", reply_markup=InlineKeyboardMarkup(_rows))
async def heute_morgen(update: Update, ctx: ContextTypes.DEFAULT_TYPE, morgen=False, lg_filter=None, edit=False):
    target = update.message or update.callback_query.message
    want = (datetime.now(BERLIN)+timedelta(days=1 if morgen else 0)).date()
    lines=[f"📅 {'Morgen' if morgen else 'Heute'} ({want.strftime('%d.%m.')})" + (f" – {lg_filter}" if lg_filter and lg_filter != "ALL" else "") + f" • Stand: {datetime.now(BERLIN).strftime('%H:%M')} Uhr\n"]  # V228: Stand-Zeit! Liste ist 'ne Momentaufnahme - jetzt sieht man, von wann die Zahlen sind!
    # V210: Kein 'Alle' mehr! Ohne Liga -> Liga-Auswahl zeigen (College-Wand am Wochenende war zu viel)!
    if not lg_filter or lg_filter == "ALL":
        _cb210 = "next_tomorrow" if morgen else "next_today"
        _kb210 = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏈 NFL", callback_data=f"{_cb210}:NFL"),
             InlineKeyboardButton("🏈 NCAAF", callback_data=f"{_cb210}:NCAAF")],
            [InlineKeyboardButton("🏀 NBA", callback_data=f"{_cb210}:NBA"),
             InlineKeyboardButton("🏒 NHL", callback_data=f"{_cb210}:NHL")],
            [InlineKeyboardButton("⚾ MLB", callback_data=f"{_cb210}:MLB")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
            [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")],
        ])
        _txt210 = f"📅 {'Morgen' if morgen else 'Heute'} ({want.strftime('%d.%m.')})\n\nWelche Liga?\nTipp oben auf eine Liga! 👆"
        if edit:
            await _cb_edit(update, _txt210, _kb210)
        else:
            await target.reply_text(_txt210, reply_markup=_kb210)
        return
    # Überall: "Gast @ Heim" - erstes Team ist Heimteam!

    live_lines=[]; _up_hm=[]  # V208: (dt, zeile) fuer Zeit-Gruppen! | V227: live_lines = (eid, liga, zeile), _up_hm = (dt, eid, liga, zeile) - fuer die Nummerierung!
    try: _favs_hm = favs_for(update.effective_user.id if update.effective_user else 0)
    except: _favs_hm = []
    # V204: Explizite Datums-Abfrage! Vorher: espn_scoreboard() OHNE Datum -> ESPN liefert nur den US-Heute-Slate -> Nacht-Spiele 00:00-03:00 DE-Zeit (US-Abend!) fielen raus (Iowa State 00:00, Clemson 01:30 usw. fehlten in Next Games)! Jetzt: -1 bis +2 Tage abfragen + Dedupe!
    _seen_hm=set()
    for league in LEAGUES:
        if lg_filter and lg_filter != "ALL" and league != lg_filter: continue  # V207: Liga-Fach!
        for _off_hm in (-1, 0, 1, 2):
            _d_hm = datetime.now(BERLIN).date() + timedelta(days=_off_hm)
            for ev in espn_scoreboard(league, dates=_d_hm.strftime("%Y%m%d")):
                _eid_hm = str(ev.get("id",""))
                if _eid_hm in _seen_hm: continue
                _seen_hm.add(_eid_hm)
                _, dt = fmt_dt(ev.get("date",""))
                if dt and dt.date()==want:
                    state = ev.get("status",{}).get("type",{}).get("state","")
                    # Heute: NUR Live + Noch heute! Finals kommen bei ✅ Ergebnisse rein, sonst ewige Liste!
                    if not morgen and state=="post":
                        continue
                    _line_hm = game_line(ev, league, show_broadcast=True)  # V210: Kein Liga-Emoji mehr vor dem Spiel -> passt in eine Zeile!
                    # V208: Kompakt! Datum steht schon oben in der Ueberschrift - nicht 50x wiederholen!
                    _line_hm = _line_hm.replace(f" {want.strftime('%d.%m.')} ", " ").replace("  ", " ")
                    # V209: ⭐ bei Favoriten-Spielen! Gleiches exaktes Matching wie Ergebnisse/Live!
                    try:
                        _is_fav_hm = False
                        _comp_hm = ev.get("competitions", [{}])[0]
                        for _c_hm in _comp_hm.get("competitors", []):
                            _tm_hm = _c_hm.get("team", {}) or {}
                            if _is_fav_team(_tm_hm.get("displayName",""), _favs_hm, league):
                                _is_fav_hm = True; break
                        if _is_fav_hm: _line_hm = "⭐ " + _line_hm
                    except: pass
                    # V231: Kuerzel sauber NEU AUFBAUEN! V230-Bug: ESPN-shortDisplayName ("San Diego St") ist nur ein PRAEFIX von "San Diego State Aztecs" -> Replace liess "ate" uebrig ("SDSUate")! Nie wieder Substring-Replace!
                    try:
                        _comp231 = ev.get("competitions", [{}])[0]
                        _away231 = _home231 = None
                        for _c231 in _comp231.get("competitors", []):
                            _tm231 = _c231.get("team", {}) or {}
                            # V234: Record aus ESPN (z.B. "7-4") - wie aufm Scoreboard! Kein Record da = leer, nix erfinden!
                            _rec234 = ""
                            try:
                                for _r234 in (_c231.get("records") or []):
                                    _s234 = (_r234.get("summary") or "").strip()
                                    if (_r234.get("type") or "") == "total" and "-" in _s234:
                                        _rec234 = _s234; break
                                if not _rec234:
                                    for _r234 in (_c231.get("records") or []):
                                        _s234 = (_r234.get("summary") or "").strip()
                                        if "-" in _s234:
                                            _rec234 = _s234; break
                            except: _rec234 = ""
                            _rec231 = ((_tm231.get("abbreviation", "") or "").upper(), _c231.get("score"), _rec234)
                            if _c231.get("homeAway", "") == "away": _away231 = _rec231
                            else: _home231 = _rec231
                        if _away231 and _home231:
                            _star231 = ""
                            _work231 = _line_hm
                            if _work231.startswith("⭐ "): _star231, _work231 = "⭐ ", _work231[2:]
                            _segs231 = _work231.split(" • ", 1)
                            _a231, _sa231, _ra231 = _away231
                            _h231, _sh231, _rh231 = _home231
                            # V233: Score NUR bei Live/Final! ESPN liefert fuer kommende Spiele Score "0" -> sonst steht da "MIA 0 @ BUF 0" obwohl noch gar nicht gespielt wurde!
                            if state in ("in", "post") and _sa231 is not None and _sh231 is not None:
                                _match231 = f"{_a231} {_sa231} @ {_h231} {_sh231}"
                            elif _ra231 and _rh231:
                                # V234: Kommende Spiele mit Record - wie aufm ESPN-Scoreboard! MIA (4-7) @ BUF (7-4)
                                _match231 = f"{_a231} ({_ra231}) @ {_h231} ({_rh231})"
                            else:
                                _match231 = f"{_a231} @ {_h231}"
                            _line_hm = _star231 + _match231 + (f" • {_segs231[1]}" if len(_segs231) > 1 else "")
                    except: pass
                    # V232: Sender RAUS aus der Liste! Steht jetzt in den Details - und 📺 + Sender waren die 2 Zeichen, die die Zeile immer noch umbrechen liessen!
                    try:
                        if " • 📺 " in _line_hm: _line_hm = _line_hm.split(" • 📺 ")[0]
                    except: pass
                    if state=="in":
                        # V229: Kein "LIVE" in jeder Zeile! Oben steht schon "🔴 Live:" als Ueberschrift - sonst doppelt gemoppelt!
                        _line_hm = _line_hm.replace(" • 🔴 LIVE", "").replace("🔴 LIVE • ", "").replace("🔴 LIVE", "")
                        live_lines.append((_eid_hm, league, _line_hm))  # V227: eid + Liga mitnehmen fuer Zahlen-Pick!
                    else:
                        # V209: Anstosszeit raus aus der Zeile - sie steht 1x als Gruppen-Ueberschrift!
                        if dt: _line_hm = _line_hm.replace(f" • ⏰ {dt.strftime('%H:%M')} Uhr", "")
                        _line_hm = _line_hm.replace("📺 ", "")
                        _up_hm.append((dt, _eid_hm, league, _line_hm))  # V227: eid + Liga mitnehmen fuer Zahlen-Pick!
    # V227: Spiele NUMMERIERT! Zahl schreiben -> Detail + Benachrichtigungen!
    _ng227 = []  # [(liga, eid)] in Anzeige-Reihenfolge!
    _n227 = 0
    if live_lines:
        lines.append("🔴 Live:")
        for _eid227, _lg227, _ln227 in live_lines:
            _n227 += 1; _ng227.append((_lg227, _eid227))
            lines.append(f"{_n227}. {_ln227}")
    if _up_hm:
        # V209: Nach Anstosszeit gruppiert! Uhrzeit steht nur 1x pro Slot - keine Wiederholung mehr!
        _groups_hm = [("🌙 Nacht", {}), ("☀️ Tag", {}), ("🌇 Abend", {})]
        for _dt_hm, _eid227b, _lg227b, _ln_hm in sorted(_up_hm, key=lambda x: x[0] or datetime.now(BERLIN)):
            _hh_hm = _dt_hm.hour if _dt_hm else 12
            _gi_hm = 0 if _hh_hm < 6 else 1 if _hh_hm < 18 else 2
            _slot_hm = _dt_hm.strftime("%H:%M") if _dt_hm else "??:??"
            _n227 += 1; _ng227.append((_lg227b, _eid227b))  # V227: Nummer in Anzeige-Reihenfolge!
            _groups_hm[_gi_hm][1].setdefault(_slot_hm, []).append(f"{_n227}. {_ln_hm}")
        for _gt_hm, _slots_hm in _groups_hm:
            if _slots_hm:
                lines.append(f"\n{_gt_hm}:")
                for _slot_hm, _items_hm in _slots_hm.items():
                    lines.append(f"⏰ {_slot_hm}")
                    lines.extend(_items_hm)
    if live_lines or _up_hm:
        lines.append("\n✍️ Zahl schreiben für Details + Benachrichtigungen! (z.B. 1 für Spiel 1)")
        try:
            ctx.user_data["next_games_list"] = _ng227; ctx.user_data["await_live_stats_pick"] = False  # V227: Zahlen-Liste merken! V246: Live-Flag aus!
            ctx.user_data["my_live_list"] = None  # V227: Andere Zahlen-Listen leeren - sonst frisst Meine-Live-Spiele die Zahl!
            ctx.user_data["next_live_list"] = None
            ctx.user_data["results_list"] = None
        except: pass
    if not live_lines and not _up_hm:
        if morgen:
            lines.append(f"Keine {lg_filter}-Spiele morgen. Tipp oben auf eine andere Liga!" if lg_filter and lg_filter != "ALL" else "Morgen keine Spiele in den Ligen. Schau mal bei /top10 oder /next vorbei.")
        else:
            lines.append("Heute kein Spiel mehr - alles schon vorbei! Schau mal bei ✅ Ergebnisse für die Endergebnisse von letzter Nacht.")
            lines.append("Oder bei ⏭️ Next Games für die nächsten Spiele deiner Favoriten.")
    # V207: Liga-Faecher oben dran + Sicherheits-Cap (Telegram-Limit 4096 Zeichen)!
    _cb_hm = "next_tomorrow" if morgen else "next_today"
    def _flbl_hm(_lg):
        return f"{'✅ ' if lg_filter == _lg else ''}{_lg}"  # V210: Kein Emoji im Knopf mehr -> nix abgeschnitten!
    _kb_hm = InlineKeyboardMarkup([
        [InlineKeyboardButton(_flbl_hm("NFL"), callback_data=f"{_cb_hm}:NFL"),
         InlineKeyboardButton(_flbl_hm("NCAAF"), callback_data=f"{_cb_hm}:NCAAF"),
         InlineKeyboardButton(_flbl_hm("NBA"), callback_data=f"{_cb_hm}:NBA")],
        [InlineKeyboardButton(_flbl_hm("NHL"), callback_data=f"{_cb_hm}:NHL"),
         InlineKeyboardButton(_flbl_hm("MLB"), callback_data=f"{_cb_hm}:MLB")],  # V210: 'Alle' RAUS!
        [InlineKeyboardButton("🔄 Aktualisieren", callback_data=f"{_cb_hm}:{lg_filter}")],  # V228: Liste neu laden! Selber Callback wie Liga-Knopf -> rendert neu (edit=True)!
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")],
    ])
    _txt_hm = "\n".join(lines)
    if len(_txt_hm) > 4000:
        _cut = []
        for _ln in lines:
            if sum(len(x) + 1 for x in _cut) + len(_ln) > 3900: break
            _cut.append(_ln)
        _cut.append("\n… zu viele Spiele! Tipp oben auf eine Liga, um zu filtern! 👆")
        # V227: Nur die wirklich angezeigten Spiele in der Zahlen-Liste behalten!
        try:
            _shown227 = sum(1 for _ln in _cut if _ln and _ln.split(". ", 1)[0].isdigit())
            ctx.user_data["next_games_list"] = _ng227[:_shown227]; ctx.user_data["await_live_stats_pick"] = False  # V246: Live-Flag aus! Diese Liste gewinnt jetzt!
            if _shown227 < len(_ng227):
                _cut.append("✍️ Zahl schreiben für Details + Benachrichtigungen!")
        except: pass
        _txt_hm = "\n".join(_cut)
    if edit:
        await _cb_edit(update, _txt_hm, _kb_hm)
    else:
        await target.reply_text(_txt_hm, reply_markup=_kb_hm)



# ===== V158: YouTube Highlights & Pressekonferenz + Ergebnisse Favoriten-Filter =====
# Kein API-Key noetig! Nur YouTube-Such-Links - gehen immer, gehen nie kaputt!
# User entscheidet selbst, ob er Highlights / Pressekonferenz sehen will!
def _yt_buttons_for_game(eid, lg, final_text=""):
    try:
        from urllib.parse import quote_plus
        away_full, home_full = "", ""
        # 1) Volle Teamnamen aus ESPN Summary (besser fuer YouTube-Suche als Kurzname!)
        try:
            _key = LEAGUES[lg]["espn"]
            _sport = 'hockey' if lg=='NHL' else 'basketball' if lg=='NBA' else 'football' if lg in ('NFL','NCAAF') else 'baseball'
            _r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{_sport}/{_key}/summary", params={"event": eid}, timeout=8)
            _d = _r.json()
            _hdr = _d.get("header", {}) or {}
            _comps = _hdr.get("competitions", []) or []
            if _comps:
                _competitors = _comps[0].get("competitors", []) or []
                _names = []
                for _c in _competitors:
                    _tm = _c.get("team", {}) or {}
                    _nm = _tm.get("displayName","") or _tm.get("shortDisplayName","") or ""
                    if _nm: _names.append(_nm)
                if len(_names) >= 2:
                    away_full, home_full = _names[0], _names[1]
        except: pass
        # 2) Fallback: Namen aus Final-Stats-Text parsen ("Steelers 18 @ Bengals 38" -> "Steelers" / "Bengals")
        if not away_full and final_text:
            try:
                _first = final_text.splitlines()[0] if final_text else ""
                if "Final Stats:" in _first:
                    _rest = _first.split("Final Stats:",1)[1].strip()
                    if " @ " in _rest:
                        _left, _right = _rest.split(" @ ",1)
                        def _strip_score(s):
                            _p = s.strip().split()
                            if _p and _p[-1].isdigit():
                                return " ".join(_p[:-1])
                            return s.strip()
                        away_full = _strip_score(_left)
                        home_full = _strip_score(_right)
            except: pass
        if away_full and home_full:
            _q_high = f"{away_full} at {home_full} Highlights"
            _q_press = f"{away_full} {home_full} Pressekonferenz"
        else:
            _q_high = f"{lg} Highlights"
            _q_press = f"{lg} Pressekonferenz"
        _hl_url = f"https://www.youtube.com/results?search_query={quote_plus(_q_high)}"
        _pr_url = f"https://www.youtube.com/results?search_query={quote_plus(_q_press)}"
        return [
            [InlineKeyboardButton("🎥 Highlights auf YouTube", url=_hl_url)],
            [InlineKeyboardButton("🎙️ Pressekonferenz auf YouTube", url=_pr_url)],
        ]
    except:
        try:
            from urllib.parse import quote_plus as _qp
            return [
                [InlineKeyboardButton("🎥 Highlights auf YouTube", url=f"https://www.youtube.com/results?search_query={_qp(lg + ' Highlights')}")],
                [InlineKeyboardButton("🎙️ Pressekonferenz auf YouTube", url=f"https://www.youtube.com/results?search_query={_qp(lg + ' Pressekonferenz')}")],
            ]
        except:
            return []

async def results_mine_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # V158: Nur Ergebnisse deiner Favoriten - alle Ligen, letzte 7 Tage!
    target = update.message or update.callback_query.message
    favs = favs_for(update.effective_user.id) if update.effective_user else []
    if not favs:
        _kb0 = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Favorit hinzufügen", callback_data="fav_add")],[InlineKeyboardButton("✅ Alle Ergebnisse", callback_data="results")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        try:
            await _cb_edit(update, "⭐ Nur meine Favoriten\n\nNoch keine Favoriten!\nFüg erst ein Team hinzu, dann siehst du hier nur deine Teams!", _kb0)
        except:
            await target.reply_text("⭐ Nur meine Favoriten\n\nNoch keine Favoriten!", reply_markup=_with_close(_kb0))
        return
    # Favoriten nach Liga aufsplitten: "Pittsburgh Steelers (NFL)" -> {"NFL": ["pittsburgh steelers"]}
    fav_by_league = {}
    for _f in favs:
        try:
            if " (" in _f and _f.endswith(")"):
                _name_part, _lg_part = _f.rsplit(" (", 1)
                _lg = _lg_part.replace(")", "").strip()
                if _lg in LEAGUES:
                    fav_by_league.setdefault(_lg, []).append(_name_part.strip().lower())
                else:
                    for _lg2 in LEAGUES: fav_by_league.setdefault(_lg2, []).append(_name_part.strip().lower())
            else:
                for _lg2 in LEAGUES: fav_by_league.setdefault(_lg2, []).append(_f.strip().lower())
        except: pass
    from datetime import date as _date
    today = _date.today()
    finals_all = []  # (dt, league, ev)
    for league in LEAGUES:
        _wanted = fav_by_league.get(league, [])
        if not _wanted: continue
        seen = set()
        for offset in range(0, 8):
            d = today - timedelta(days=offset)
            ds = d.strftime("%Y%m%d")
            for ev in espn_scoreboard(league, dates=ds):
                eid = ev.get("id")
                if eid in seen: continue
                seen.add(eid)
                state = ev.get("status",{}).get("type",{}).get("state","")
                if state != "post": continue
                # Ist ein Favorit dabei? Vollname oder Kurzname muss matchen!
                try:
                    _comp = ev.get("competitions", [{}])[0]
                    _is_fav_game = False
                    for _c in _comp.get("competitors", []):
                        _tm = _c.get("team", {}) or {}
                        _full = (_tm.get("displayName","") or "").lower()
                        # V201: Schule EXAKT pruefen, nicht nur Maskottchen! Vorher: 'panthers' in 'Georgia State Panthers' / 'FIU Panthers' -> beide falsch drin, obwohl nur Pittsburgh Panthers gemeint ist! _is_fav_team vergleicht die Schule (Pittsburgh != Georgia State != FIU) + Liga!
                        if _is_fav_team(_full, favs, league):
                            _is_fav_game = True
                            break
                        if _is_fav_game: break
                    if not _is_fav_game: continue
                except: continue
                _, dt = fmt_dt(ev.get("date",""))
                finals_all.append((dt or datetime.now(BERLIN), league, ev))
    finals_all.sort(key=lambda x: x[0], reverse=True)
    finals_all = finals_all[:15]
    lines = ["⭐ Ergebnisse - Nur meine Favoriten (letzte 7 Tage)\n"]
    if not finals_all:
        lines.append("Keine Endergebnisse deiner Favoriten in den letzten 7 Tagen gefunden.")
        lines.append("Vielleicht hatten deine Teams Bye Week oder spielen erst noch!")
    else:
        from collections import OrderedDict
        by_date = OrderedDict()
        for dt, lg, ev in finals_all:
            key = dt.strftime("%d.%m.") if dt else "?"
            by_date.setdefault(key, []).append((dt, lg, ev))
        _num = 0
        for date_s, items in by_date.items():
            lines.append(f"\n📅 {date_s}")
            for dt, lg, ev in items:
                _num += 1
                teams, _ = event_teams(ev)
                try:
                    _comp2 = ev.get("competitions", [{}])[0]
                    def _sn(idx):
                        try:
                            _tm2 = _comp2.get("competitors", [])[idx].get("team", {}) or {}
                            return _tm2.get("shortDisplayName","") or _tm2.get("displayName","") or teams[idx][0]
                        except: return teams[idx][0] if idx < len(teams) else ""
                    _h = _sn(0); _a = _sn(1)
                except:
                    _h = teams[0][0] if len(teams)>0 else ""; _a = teams[1][0] if len(teams)>1 else ""
                _hs = teams[0][2] if len(teams)>0 else ""
                _as = teams[1][2] if len(teams)>1 else ""
                _emoji = LEAGUES[lg].get("emoji","")
                lines.append(f"{_num}. {_emoji} {_h} {_hs} - {_as} {_a}")
    try: ctx.user_data["results_list"] = [(lg, str(_ev.get("id",""))) for _dt, lg, _ev in finals_all]
    except: pass
    try: ctx.user_data["next_live_list"] = None
    except: pass
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Alle Ergebnisse", callback_data="results")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    _rm = await target.reply_text("\n".join(lines) + "\n\n📊 Für Final Stats einfach die Zahl schicken! z.B. 1", reply_markup=_with_close(kb))
    try:
        _uid_r = update.effective_user.id if update.effective_user else 0
        _chain_add(_uid_r, _rm.message_id)
    except: pass

async def results_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Liga-Auswahl für Ergebnisse - nicht alle Ligen auf einmal, sonst ewige Liste!
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Nur meine Favoriten", callback_data="results_mine")],
        [InlineKeyboardButton("🏈 NFL", callback_data="results_league:NFL"),
         InlineKeyboardButton("🏒 NHL", callback_data="results_league:NHL")],
        [InlineKeyboardButton("⚾ MLB", callback_data="results_league:MLB"),
         InlineKeyboardButton("🏀 NBA", callback_data="results_league:NBA")],
        [InlineKeyboardButton("🏈 NCAAF", callback_data="results_league:NCAAF")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "✅ Ergebnisse\n\nWelche Liga?", kb)
async def results_league_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str):
    target = update.message or update.callback_query.message
    _load_resu = await _loading_start(target, "⏳ Ich hole die Ergebnisse... einen Moment")
    # Limit pro Liga: NCAAF hat am Wochenende 30+ Spiele, da sind 5 viel zu wenig!
    # NFL/NHL/NBA/MLB: 10 reichen (da sind pro Tag nur 8-15 Spiele). NCAAF: 20, sonst fehlen die Longhorns!
    LIMITS = {"NCAAF": 20, "NFL": 12, "NHL": 10, "NBA": 10, "MLB": 12}
    limit = LIMITS.get(league, 10)
    # Wir gucken die letzten 7 Tage durch, sammeln Finals, sortieren neueste zuerst, nehmen Limit
    from datetime import date as _date
    today = _date.today()
    finals=[]; seen=set()
    for offset in range(0, 8):
        d = today - timedelta(days=offset)
        ds = d.strftime("%Y%m%d")
        for ev in espn_scoreboard(league, dates=ds):
            eid = ev.get("id")
            if eid in seen: continue
            seen.add(eid)
            state = ev.get("status",{}).get("type",{}).get("state","")
            if state!="post": continue
            _, dt = fmt_dt(ev.get("date",""))
            finals.append((dt or datetime.now(BERLIN), ev))
    finals.sort(key=lambda x: x[0], reverse=True)
    finals = finals[:limit]
    _favs_r = favs_for(update.effective_user.id) if update.effective_user else []
    _fav_names_r = [f.split(" (")[0].strip().lower() for f in _favs_r if f.split(" (")[-1].replace(")","").strip()==league or " (" not in f]
    # V201 FIX 2: CFP-Rangliste EINMAL holen (nicht pro Spiel - sonst 20 Calls)! Für Live-Bedeutung in der Liste!
    _cfp_rank_map={}
    if league=="NCAAF":
        try:
            _cfp_rows2,_=_espn_cfp_top25()
            _cfp_rank_map={_d.lower():_i for _i,(_d,_s,_r) in enumerate(_cfp_rows2,1)}
        except: _cfp_rank_map={}
    lines=[f"✅ Ergebnisse - {LEAGUES[league]['emoji']} {league} (letzte {limit})\n⭐ = Dein Team\n"]
    if not finals:
        lines.append("Keine Endergebnisse in den letzten 7 Tagen gefunden.")
    else:
        # Übersichtlicher: Nach Datum gruppieren, kurze Teamnamen, 1 Zeile pro Spiel, kein Sender!
        # Vorher: "Ball State Cardinals 7 @ Buffalo Bulls 28 • ✅ Final • 12.11. 01:30 • 📺 ESPN2" (2 Zeilen, ewig lang)
        # Jetzt: "📅 12.11.\nBuffalo 28 - 7 Ball State ✅" (1 Zeile, kurz!)
        from collections import OrderedDict
        by_date = OrderedDict()
        for dt, ev in finals:
            key = dt.strftime("%d.%m.") if dt else "?"
            by_date.setdefault(key, []).append((dt, ev))
        for date_s, items in by_date.items():
            lines.append(f"\n📅 {date_s}")
            for dt, ev in items:
                teams, _ = event_teams(ev)
                # Kurze Namen: "Buffalo" statt "Buffalo Bulls", "Ball State" statt "Ball State Cardinals"
                def short_name(idx):
                    try:
                        comp = ev.get("competitions", [{}])[0]
                        c = comp.get("competitors", [])[idx]
                        tm = c.get("team", {}) or {}
                        return tm.get("shortDisplayName","") or tm.get("displayName","") or teams[idx][0]
                    except: return teams[idx][0] if idx < len(teams) else ""
                # teams[0] = Heim, teams[1] = Gast (ESPN-Reihenfolge) - wir zeigen Heim zuerst!
                h_name = short_name(0); a_name = short_name(1)
                h_score = teams[0][2] if len(teams)>0 else ""
                a_score = teams[1][2] if len(teams)>1 else ""
                # Suffix: Kein Haken mehr pro Spiel! Nur (OT)/(2OT)/(SO)/(10 Inn.) in Klammern
                # NFL: nur (OT) möglich. NCAAF/NBA: (OT),(2OT),(3OT)... NHL: (OT)/(SO). MLB: (10 Inn.)...
                st = ev.get("status",{}) or {}
                per = st.get("period") or 0
                det = (st.get("type",{}) or {}).get("detail","") or ""
                det_u = det.upper()
                suffix = ""
                if league=="MLB":
                    # Baseball: period = gespielte Innings. 9 = normal, >9 = Extra Innings
                    try: inn = int(per)
                    except: inn = 0
                    if inn>9: suffix = f" ({inn} Inn.)"
                    elif "/10" in det or "EXTRA" in det_u: suffix = " (10 Inn.)"
                elif league=="NHL":
                    if "SO" in det_u or "SHOOTOUT" in det_u: suffix = " (SO)"
                    elif per==5 or "/OT" in det or " OT" in det_u: suffix = " (OT)"
                elif league in ("NCAAF","NBA"):
                    # period 4=Regulation, 5=1OT, 6=2OT, 7=3OT...
                    ot_count = 0
                    if per and per>4: ot_count = int(per)-4
                    elif "OT" in det_u:
                        import re as _re
                        m=_re.search(r"(\d+)\s*OT", det_u)
                        ot_count = int(m.group(1)) if m else 1
                    if ot_count==1: suffix=" (OT)"
                    elif ot_count>1: suffix=f" ({ot_count}OT)"
                elif league=="NFL":
                    if (per and per>4) or "OT" in det_u: suffix=" (OT)"
                # V110: Nummer voran, damit du nur die Zahl schicken musst!
                _num = len([x for x in lines if x.startswith(tuple([str(i)+"." for i in range(1,99)]))]) + 1
                # V134: Favoriten mit ⭐ markieren - Vollname in gleicher Liga!
                def _is_fav_r(_nm):
                    try:
                        comp2 = ev.get("competitions", [{}])[0]
                        for c2 in comp2.get("competitors", []):
                            tm2=c2.get("team",{}) or {}
                            _full2=(tm2.get("displayName","") or "").lower()
                            _short2=(tm2.get("shortDisplayName","") or "").lower()
                            if _short2==_nm.lower() or _full2==_nm.lower():
                                return any(fn in _full2 or _full2 in fn for fn in _fav_names_r)
                        return False
                    except: return False
                _star_h = " ⭐" if _is_fav_r(h_name) else ""
                _star_a = " ⭐" if _is_fav_r(a_name) else ""
                lines.append(f"{_num}. {h_name}{_star_h} {h_score} - {a_score} {a_name}{_star_a}{suffix}")
                # V201 FIX 2: Live-Bedeutung DIREKT in der Liste, unter Favoriten-Spielen! Vorher nur in Detail-Ansicht!
                if league=="NCAAF" and (_star_h or _star_a) and _cfp_rank_map:
                    try:
                        _hs=int(h_score) if str(h_score).strip().lstrip("-").isdigit() else 0
                        _as=int(a_score) if str(a_score).strip().lstrip("-").isdigit() else 0
                        _w_full=teams[0][0] if _hs>=_as else teams[1][0]
                        _l_full=teams[1][0] if _hs>=_as else teams[0][0]
                        _wr=None; _lr=None
                        for _cd,_ri in _cfp_rank_map.items():
                            if _is_fav_team(_cd, [_w_full], "NCAAF"): _wr=_ri
                            if _is_fav_team(_cd, [_l_full], "NCAAF"): _lr=_ri
                        _ws=_cfp_short(_w_full, "")
                        if _wr and _wr<=12: lines.append(f"   • {_ws} bleibt in Top 12!")
                        elif _wr and _wr<=25: lines.append(f"   • {_ws} noch im Rennen!")
                        elif _lr and _lr<=12: lines.append(f"   • {_ws} schmeißt #{_lr} raus?!")
                    except: pass
    # V110: Keine Buttons mehr! Nur Zahl schicken wie bei Favoriten!
    # Liste speichern, damit on_text die Zahl zuordnen kann!
    try: ctx.user_data["results_list"] = [(league, str(_ev.get("id",""))) for _dt, _ev in finals]
    except: pass
    try: ctx.user_data["next_live_list"] = None
    except: pass
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Nur meine Favoriten", callback_data="results_mine")],
        [InlineKeyboardButton("✅ Andere Liga", callback_data="results")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    _rm =     await _loading_done(ctx, update.effective_user.id if update.effective_user else 0, _load_resu)
    _m201 = await target.reply_text("\n".join(lines) + "\n\n📊 Für Final Stats einfach die Zahl schicken! z.B. 1", reply_markup=_with_close(kb))
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
    try:
        _uid_r = update.effective_user.id if update.effective_user else 0
        _chain_add(_uid_r, _rm.message_id)
    except: pass

def _live_situation_line(lg, ev, _poss_override=""):
    # V149: ESPN-Stil! Genau wie auf dem Screenshot: „0:09 - 2nd • 1st & 10, PIT 22"!
    # ESPN: status.displayClock + status.period + situation.downDistanceText + situation.possessionText / yardLine!
    try:
        _comps=ev.get("competitions") or [{}]
        _comp=_comps[0] if _comps else {}
        _sit=_comp.get("situation") or {}
        _st=ev.get("status") or {}
        # --- NFL / NCAAF: ESPN-Stil ---
        if lg in ("NFL","NCAAF"):
            _clock=_st.get("displayClock") or ""
            _per=_st.get("period")
            # Quarter als „1st / 2nd / 3rd / 4th / OT"!
            _per_s=""
            try:
                _p=int(_per)
                _per_s={1:"1st",2:"2nd",3:"3rd",4:"4th",5:"OT"}.get(_p, f"Q{_p}")
            except Exception:
                _per_s=str(_per or "")
            _clock_part=""
            if _clock and _per_s: _clock_part=f"{_clock} - {_per_s}"
            elif _clock: _clock_part=_clock
            elif _per_s: _clock_part=_per_s
            # Down & Distance + Feldposition: ESPN liefert downDistanceText („1st & 10") + possessionText („PIT 22") / yardLine!
            _dd=str(_sit.get("downDistanceText") or _sit.get("shortDownDistanceText") or "").strip()
            if not _dd:
                try:
                    _d=_sit.get("down"); _dist=_sit.get("distance")
                    if _d is not None and _dist is not None:
                        _ord={1:"1st",2:"2nd",3:"3rd",4:"4th"}.get(int(_d), f"{_d}th")
                        _dd=f"{_ord} & {_dist}"
                except Exception: pass
            # Feldposition: possessionText („PIT 22") hat Vorrang, sonst aus possession + yardLine bauen!
            _pos=str(_sit.get("possessionText") or _sit.get("yardLineText") or "").strip()
            if not _pos:
                try:
                    _poss_abbr=""
                    _poss_id=str(_sit.get("possession") or _sit.get("possessionId") or "")
                    for _c in (_comp.get("competitors") or []):
                        _tid=str((_c.get("team") or {}).get("id") or "")
                        if _tid and _tid==_poss_id:
                            _poss_abbr=(_c.get("team") or {}).get("abbreviation") or ""
                            break
                    _yl=_sit.get("yardLine")
                    if _poss_abbr and isinstance(_yl,(int,float)):
                        _y=int(_yl)
                        # yardLine 0-50 = eigene Seite, 51-99 = gegnerische Seite (aus Sicht des Ballbesitzers)!
                        # ESPN: yardLine = Yards von eigener Endzone -> „PIT 22" = PIT an eigener 22!
                        if 0 <= _y <= 50: _pos=f"{_poss_abbr} {_y}"
                        elif 50 < _y < 100: _pos=f"{_poss_abbr} {100-_y}"
                    elif _poss_abbr and isinstance(_yl,str) and _yl.strip():
                        _pos=_yl.strip()
                except Exception: pass
            # V150-FIX: Feldposition fehlt bei 0:00 / Halbzeit (situation.yardLine = leer)! Fallback: status.detail parsen!
            # ESPN-Detail ist oft „1st & 10 at PIT 22" oder „1st & 10, PIT 22" oder „PIT 22"!
            if not _pos:
                try:
                    _det=str((_st.get("type") or {}).get("detail") or "") + " " + str((_st.get("type") or {}).get("shortDetail") or "")
                    # „at PIT 22" / „, PIT 22" / „PIT 22" suchen!
                    import re as _re2
                    _mm=_re2.search(r"(?:at|,)\s*([A-Z]{2,4}\s+\d{1,2})", _det)
                    if _mm: _pos=_mm.group(1).strip()
                    else:
                        _mm2=_re2.search(r"\b([A-Z]{2,4}\s+\d{1,2})\b", _det)
                        if _mm2 and _dd and _mm2.group(1) not in _dd: _pos=_mm2.group(1).strip()
                except Exception: pass
            # V151-FIX: Ballbesitz immer anzeigen + Duplikat weg!
            # „1st & 10 at CIN 22" enthält schon die Position -> kein „, CIN 22" nochmal dranhängen!
            # Und: „Ball: PIT" dazu, sonst weiß man nicht wer den Ball hat!
            # V152: Ballbesitz aus Summary-Drives (Override) hat Vorrang! Scoreboard-possession war falsch (PIT statt CIN)!
            _poss_abbr2=str(_poss_override or "").strip()
            if not _poss_abbr2:
                try:
                    _pid2=str(_sit.get("possession") or _sit.get("possessionId") or "")
                    for _cc in (_comp.get("competitors") or []):
                        if str((_cc.get("team") or {}).get("id") or "")==_pid2 and _pid2:
                            _poss_abbr2=(_cc.get("team") or {}).get("abbreviation") or ""
                            break
                except Exception: pass
            # Dedup: Wenn _dd schon die Position enthält (z.B. „1st & 10 at CIN 22"), _pos nicht nochmal!
            if _pos and _pos in _dd:
                _pos=""
            # Wenn _dd schon „at XXX" enthält, _pos auch nicht!
            if _pos and " at " in _dd:
                _pos=""
            _parts=[]
            if _clock_part: _parts.append(f"⏱️ {_clock_part}")
            if _poss_abbr2: _parts.append(f"🏈 Ball: {_poss_abbr2}")
            if _dd and _pos:
                # ESPN-Stil: „1st & 10 at CIN 22" (mit „at"), nicht „, CIN 22"!
                _parts.append(f"{_dd} at {_pos}" if " at " not in _dd else _dd)
            elif _dd: _parts.append(_dd)
            elif _pos: _parts.append(_pos)
            if _parts: return " • ".join(_parts)
            return ""
        # --- NBA: Ballbesitz ---
        if lg=="NBA":
            try:
                _poss_id=str(_sit.get("possession") or "")
                for _c in (_comp.get("competitors") or []):
                    if str((_c.get("team") or {}).get("id") or "")==_poss_id and _poss_id:
                        _ab=(_c.get("team") or {}).get("abbreviation") or ""
                        if _ab: return f"🏀 Ball: {_ab}"
            except Exception: pass
            return ""
        if lg=="NHL":
            try:
                if _sit.get("powerPlay"):
                    _poss_id=str(_sit.get("possession") or "")
                    _ab=""
                    for _c in (_comp.get("competitors") or []):
                        if str((_c.get("team") or {}).get("id") or "")==_poss_id and _poss_id:
                            _ab=(_c.get("team") or {}).get("abbreviation") or ""
                    return f"🏒 Power Play: {_ab or '—'}"
            except Exception: pass
            return ""
        if lg=="MLB":
            _outs=_sit.get("outs"); _balls=_sit.get("balls"); _strikes=_sit.get("strikes")
            _bases=[]
            if _sit.get("onFirst"): _bases.append("1st")
            if _sit.get("onSecond"): _bases.append("2nd")
            if _sit.get("onThird"): _bases.append("3rd")
            _p=[]
            if _outs is not None: _p.append(f"{_outs} Out{'s' if _outs!=1 else ''}")
            if _balls is not None and _strikes is not None: _p.append(f"Count {_balls}-{_strikes}")
            if _bases: _p.append("Runner auf " + " & ".join(_bases))
            if _p: return "⚾ " + " • ".join(_p)
            return ""
        return ""
    except Exception:
        return ""

async def live_stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # V147: Live-Stats Button aus Live-Ansicht!
    target=update.message or update.callback_query.message
    _live=ctx.user_data.get("live_events_v147") or []
    if not _live:
        await target.reply_text("Gerade kein Live-Spiel gefunden.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])); return
    if len(_live)==1:
        await live_stats_one_cmd(update, ctx, 0); return
    # Mehrere live: Zahlen-Liste + Buttons + „Tippe die Zahl ein"!
    lines=["📊 Live-Stats - Welches Spiel?\n"]
    rows=[]
    for i,(lg,eid,ev) in enumerate(_live,1):
        lines.append(f"{i}. {LEAGUES[lg]['emoji']} {_live_ticker_line(ev, lg) or game_line(ev, lg, show_broadcast=False)}")
        rows.append([InlineKeyboardButton(f"{i}. {_live_ticker_line(ev, lg)}", callback_data=f"live_stats_one:{i-1}")])
    lines.append("\nTippe die Zahl ein (z.B. 1) oder tippe auf das Spiel!")
    ctx.user_data["await_live_stats_pick"]=True
    rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
    # V148: Bei Button-Klick bearbeiten, nicht neue Nachricht!
    _kb_pick=InlineKeyboardMarkup(rows)
    _txt_pick="\n".join(lines)
    if update.callback_query:
        await _cb_edit(update, _txt_pick, _kb_pick)
    else:
        _m201 = await target.reply_text(_txt_pick, reply_markup=_kb_pick)
        try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        except: pass
async def live_stats_one_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, idx: int, num_mid=None):
    target=update.message or update.callback_query.message
    _live=ctx.user_data.get("live_events_v147") or []
    if not _live or not (0 <= idx < len(_live)):
        await target.reply_text("Spiel nicht mehr gefunden.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])); return
    lg,eid,ev=_live[idx]
    _txt=get_live_stats_text(eid, lg)
    _kb=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Aktualisieren", callback_data=f"live_stats_one:{idx}")],[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
    if not _txt:
        _msg=f"📊 Live-Stats - {game_line(ev, lg, show_broadcast=True)}\n\nGrade keine Live-Stats verfügbar - ESPN liefert sie erst nach dem nächsten Drive! Versuch's in 2 Min nochmal! ⏳"
        # V150: Bei Button-Klick NUR bearbeiten, nie neue Nachricht!
        if update.callback_query:
            try:
                await update.callback_query.message.edit_text(_msg, reply_markup=_kb)
            except Exception as _e2:
                if "not modified" not in str(_e2).lower():
                    pass
            try: await update.callback_query.answer()
            except Exception: pass
        else:
            _m245 = await target.reply_text(_msg, reply_markup=_kb)
            try: _chain_add(update.effective_user.id if update.effective_user else 0, _m245.message_id)
            except: pass
            # V245: Getippte Zahl zum Fenster mappen (auch im Keine-Stats-Fall)!
            try:
                if num_mid: _CLOSE_NUM_MAP[(int(update.effective_user.id if update.effective_user else 0), int(_m245.message_id))] = int(num_mid)
            except: pass
        return
    # V148: Frisches Event für Situation (Down & Distance, Feldposition) - gespeichertes ev ist alt!
    try:
        _fresh=None
        for _ev2 in _scoreboard_dates(lg):
            if str(_ev2.get("id",""))==str(eid):
                _fresh=_ev2; break
        if _fresh is not None: ev=_fresh
    except Exception: pass
    # V152: Ballbesitz aus Summary-Drives (wer hat wirklich den Ball?)!
    _poss_ov=""
    try:
        _key2=LEAGUES[lg]["espn"]
        _sport2='football' if lg in ('NFL','NCAAF') else 'basketball' if lg=='NBA' else 'hockey' if lg=='NHL' else 'baseball'
        _r2=requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{_sport2}/{_key2}/summary", params={"event": eid}, timeout=10)
        _d2=_r2.json() or {}
        _drives=_d2.get("drives") or {}
        _cur=_drives.get("current") or {}
        # current Drive: team.abbreviation = Ballbesitz!
        _tm2=_cur.get("team") or {}
        _poss_ov=_tm2.get("abbreviation") or _tm2.get("shortDisplayName") or ""
        # Fallback: letzter Drive in previous, wenn current leer!
        if not _poss_ov:
            _prev=_drives.get("previous") or []
            if _prev:
                _last=_prev[-1] or {}
                _tm3=_last.get("team") or {}
                _poss_ov=_tm3.get("abbreviation") or ""
    except Exception:
        _poss_ov=""
    # V244: Sender in die Detail-Ansicht! (In der Liste steht er nicht mehr!)
    try: _bc244 = broadcast_line(ev)
    except Exception: _bc244 = ""
    if _bc244:
        _p244 = _txt.split("\n", 1)
        if len(_p244) == 2: _txt = _p244[0] + "\n" + "📺 Sender: " + _bc244 + "\n" + _p244[1]
        else: _txt = _txt + "\n" + "📺 Sender: " + _bc244
    _sit_line=_live_situation_line(lg, ev, _poss_ov)
    if _sit_line:
        # Nach der ersten Zeile (Titel) einfügen: „Live-Stats: ...\nSituation\nRest"
        _parts=_txt.split("\n", 1)
        if len(_parts)==2: _txt=_parts[0] + "\n" + _sit_line + "\n" + _parts[1]
        else: _txt=_txt + "\n" + _sit_line
    # V150: Bei Button-Klick NUR bearbeiten! Nie neue Nachricht! Wenn Inhalt gleich (Telegram „not modified"), einfach nix tun!
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(_txt, reply_markup=_kb)
        except Exception as _e:
            # „message is not modified" = Stats haben sich nicht geändert -> kein neues Fenster, einfach Button-Laden beenden!
            _msg_e=str(_e).lower()
            if "not modified" in _msg_e or "message is not modified" in _msg_e:
                pass
            else:
                # Anderer Edit-Fehler -> trotzdem keine neue Nachricht (sonst Spam wie 04:06 + 04:07)! Nur Button-Laden beenden!
                pass
        try: await update.callback_query.answer()
        except Exception: pass
    else:
        _m201 = await target.reply_text(_txt, reply_markup=_kb)
        try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        except: pass
        # V245: Getippte Zahl zum Fenster mappen! Beim Schliessen fliegt die Zahl gleich mit weg (wie bei Final Stats)!
        try:
            if num_mid: _CLOSE_NUM_MAP[(int(update.effective_user.id if update.effective_user else 0), int(_m201.message_id))] = int(num_mid)
        except: pass
async def live_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # V206: Live-Hub! Vorher: Live zeigte NUR Favoriten -> "kein Favorit live" obwohl andere Spiele liefen! Jetzt: 2 Faecher!
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Alle Live-Spiele", callback_data="live_all")],
        [InlineKeyboardButton("⭐ Nur meine Favoriten", callback_data="live_mine")],
        [InlineKeyboardButton("🔴 Meine Live-Spiele", callback_data="my_live_games")],  # V210: Eingestellte Einzel-Spiele!
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "🔴 Live\n\nWas willst du sehen?\n🔴 Alle Live-Spiele = alles was GERADE läuft, auch ohne Favoriten!\n⭐ Nur meine Favoriten = nur deine Teams live + letzte Endergebnisse!\n🔴 Meine Live-Spiele = deine eingestellten Einzel-Spiele!", kb)

async def live_all_cmd(update, ctx):
    # V244: Scoreboard-Ticker! Nur Kuerzel + Stand + Spielzeit! Kein LIVE-Label, kein Sender (Sender -> Detail-Ansicht)!
    target = update.message or update.callback_query.message
    _load_live = await _loading_start(target, "⏳ Ich hole alle Live-Spiele... einen Moment")
    lines=["🔴 Live - Alle Spiele\n"]
    _all=[]
    for league in LEAGUES:
        for ev in _scoreboard_dates(league):
            if ev.get("status",{}).get("type",{}).get("state","")!="in": continue
            _all.append((league, str(ev.get("id","")), ev))
    if not _all:
        lines.append("Gerade ist kein Spiel live in den Ligen.")
        lines.append("Schau mal bei ⏭️ Next Games, wann es weitergeht!")
    else:
        for _i, (_lg, _eid, _ev) in enumerate(_all, 1):
            _tl = _live_ticker_line(_ev, _lg)
            if _tl:
                lines.append(f"{_i}. {LEAGUES[_lg]['emoji']} {_tl}")
            else:
                lines.append(f"{_i}. {game_line(_ev, _lg, show_broadcast=False)}")
        lines.append("\nTippe die Zahl für die Details (Sender + aktuelle Stats)!")
    await _loading_done(ctx, update.effective_user.id if update.effective_user else 0, _load_live)
    # V244: Zahlen-Weiterleitung! Liste = dieselbe wie bei Live-Stats, Zahl oeffnet die Detail-Ansicht!
    try:
        ctx.user_data["live_events_v147"] = _all
        ctx.user_data["await_live_stats_pick"] = bool(_all)
    except: pass
    _kb=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
    _m206 = await target.reply_text("\n".join(lines), reply_markup=_kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m206.message_id)
    except: pass

async def live_mine_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    _load_live = await _loading_start(target, "⏳ Ich hole die Live-Spiele... einen Moment")
    # Nur Spiele der eigenen Favoriten - kein NBA wenn kein NBA-Team als Favorit drin ist!
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs = favs_for(user.id) if user else []
    # favs sind wie "Pittsburgh Penguins (NHL)" - Vollname + Liga! Nur Vollname in gleicher Liga zählt,
    # sonst wird East Carolina Pirates (NCAAF) als Pittsburgh Pirates (MLB) angezeigt!
    fav_map = []  # [(liga, vollname_lower)]
    for f in favs:
        name = f.split(" (")[0].strip().lower()
        lg = f.split(" (")[-1].replace(")", "").strip() if " (" in f else None
        fav_map.append((lg, name))
    lines=["🔴 Live - Deine Favoriten\n"]
    live_found=False
    finals=[]
    for league in LEAGUES:
        for ev in _scoreboard_dates(league):
            teams, _ = event_teams(ev)
            team_text = " ".join([x[0] for x in teams]).lower()
            # Nur wenn Vollname in der gleichen Liga vorkommt!
            if fav_map and not any((lg is None or lg==league) and fullname in team_text for lg, fullname in fav_map):
                continue
            status = ev.get("status",{}).get("type",{}).get("state","")
            if status=="in":
                lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league, show_broadcast=True)}")
                # Wenn SO live läuft, jeden Versuch mit ✅ / ❌ zeigen
                for sl in shootout_lines(ev, league):
                    lines.append(sl)
                sc = last_scorer(ev, league)
                if sc: lines.append(sc)
                live_found=True
            elif status=="post":
                finals.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league, show_broadcast=True)}")
                for sl in shootout_lines(ev, league):
                    finals.append(sl)
                scf = last_scorer(ev, league)
                if scf: finals.append(scf)
    if not favs:
        lines.append("Du hast noch keine Favoriten. Füge erst ein Team hinzu, dann zeige ich dir hier nur deine Teams live.")
        try: ctx.user_data["live_finals_list"] = None
        except: pass
    elif not live_found:
        lines.append("Gerade spielt kein Team von deinen Favoriten live.")
        if finals:
            # V154: Finals nummerieren + merken, damit Zahl -> Final Stats geht!
            try:
                _lf = []
                for _lg2 in LEAGUES:
                    for _ev2 in _scoreboard_dates(_lg2):
                        _teams2, _ = event_teams(_ev2)
                        _tt2 = " ".join([x[0] for x in _teams2]).lower()
                        if fav_map and not any((lgx is None or lgx==_lg2) and fnx in _tt2 for lgx, fnx in fav_map): continue
                        if _ev2.get("status",{}).get("type",{}).get("state","")=="post":
                            _lf.append((_lg2, str(_ev2.get("id",""))))
                ctx.user_data["live_finals_list"] = _lf[:5]; ctx.user_data["await_live_stats_pick"] = False  # V246: Live-Flag aus! Diese Liste gewinnt jetzt!
            except: ctx.user_data["live_finals_list"] = None
            lines.append("\n✅ Letzte Endergebnisse deiner Favoriten:")
            # Nummerierte Zeilen: nur die reinen Spiel-Zeilen nummerieren (keine Shootout/Scorer-Zeilen)
            _n = 0
            for _fl in finals[:5]:
                # Spiel-Zeile erkennt man am Liga-Emoji am Anfang
                if _fl[:2].strip() and any(_fl.startswith(LEAGUES[_lg]["emoji"]) for _lg in LEAGUES):
                    _n += 1
                    lines.append(f"{_n}. {_fl}")
                else:
                    lines.append(_fl)
            if ctx.user_data.get("live_finals_list"):
                lines.append("\n✍️ Wenn du mehr über das Spiel erfahren möchtest, schreibe die Zahl des Spiels als Nachricht - dann kommen die Final Stats!")
    else:
        try: ctx.user_data["live_finals_list"] = None
        except: pass
    # V147: KEIN ganzes Menü mehr drunter! Nur [Live-Stats] + [Fenster schließen]!
    # Live-Events für Live-Stats merken (Index -> Liga/Event-ID)
    try:
        _live_list=[]
        for league in LEAGUES:
            for ev in _scoreboard_dates(league):
                teams2,_=event_teams(ev)
                team_text2=" ".join([x[0] for x in teams2]).lower()
                if fav_map and not any((lg2 is None or lg2==league) and fn in team_text2 for lg2,fn in fav_map):
                    continue
                if ev.get("status",{}).get("type",{}).get("state","")=="in":
                    _live_list.append((league, str(ev.get("id","")), ev))
        ctx.user_data["live_events_v147"]=_live_list
    except Exception:
        _live_list=[]
    if live_found and _live_list:
        _kb=InlineKeyboardMarkup([[InlineKeyboardButton("📊 Live-Stats", callback_data="live_stats")],[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
    else:
        _kb=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
        await _loading_done(ctx, update.effective_user.id if update.effective_user else 0, _load_live)
    _m201 = await target.reply_text("\n".join(lines), reply_markup=_kb)
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except: pass
async def settings_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    uid = update.effective_user.id if update.effective_user else 0
    rm = get_reminder_minutes(uid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Favoriten verwalten", callback_data="fav_list")],
        [InlineKeyboardButton("🔔 Benachrichtigungen", callback_data="notif")],
        [InlineKeyboardButton("🔕 Nicht stören", callback_data="dnd")],
        [InlineKeyboardButton(f"🧹 Alte Fenster auto-schließen: {'✅ AN' if get_autoclose(uid) else '❌ AUS'}", callback_data="autoclose_toggle")],
        [InlineKeyboardButton("❓ Allgemeine Hilfe", callback_data="help")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "⚙️ Einstellungen\n\nWas willst du einstellen?", kb)
async def dnd_cmd(update, ctx):
    uid = update.effective_user.id if update.effective_user else 0
    d = get_dnd(uid); pend = get_pending(uid)
    rows = [
        [InlineKeyboardButton(f"🔕 Nicht stören: {'✅ AN' if d['on'] else '❌ AUS'}", callback_data="dnd_toggle")],
        [InlineKeyboardButton(f"⏰ Von: {d['start']:02d}:00", callback_data="dnd_pick_start"), InlineKeyboardButton(f"⏰ Bis: {d['end']:02d}:00", callback_data="dnd_pick_end")],
        [InlineKeyboardButton(f"🤫 Spoiler-Schutz: {'✅ AN' if d['spoiler'] else '❌ AUS'}", callback_data="dnd_spoiler")],
    ]
    if pend: rows.append([InlineKeyboardButton(f"🌅 Während du weg warst ({len(pend)})", callback_data="dnd_summary")])
    rows.append([InlineKeyboardButton("⬅️ Zurück zu Einstellungen", callback_data="settings")])
    await _cb_edit(update, f"🔕 Nicht stören\n\nAktuell: {'AN' if d['on'] else 'AUS'} • {d['start']:02d}:00 – {d['end']:02d}:00 Uhr\nSpoiler-Schutz: {'AN' if d['spoiler'] else 'AUS'}\n\nWenn AN: Keine Live-Nachrichten + keine Reminder in der Zeit - stattdessen sammle ich alles still und zeige es dir danach in '🌅 Während du weg warst'!\n\nSpoiler-Schutz AN = Ergebnisse erst auf Knopfdruck, damit du erst Highlights gucken kannst! 🤫", InlineKeyboardMarkup(rows))
async def dnd_pick_cmd(update, ctx, which):
    rows = []
    try: _cur_dnd = get_dnd(update.effective_user.id if update.effective_user else 0) or {}
    except: _cur_dnd = {}
    _cur_h = _cur_dnd.get("start" if which == "start" else "end")
    for _r in range(6):  # V207: 4 pro Reihe statt 6! Vorher war "00:00" abgeschnitten!
        rows.append([InlineKeyboardButton(f"{'✅' if _cur_h == _h or _cur_h == f'{_h:02d}:00' else ''}{_h:02d}:00", callback_data=f"dnd_set_{which}:{_h}") for _h in range(_r*4, _r*4+4)])
    rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="dnd")])
    # V208: Aktuelle Einstellung + Dauer anzeigen - sofort uebersichtlich!
    try:
        _dd208 = get_dnd(update.effective_user.id if update.effective_user else 0) or {}
        def _norm208(_v):
            try:
                if isinstance(_v, int): return f"{_v:02d}:00"
                return str(_v)
            except: return "?"
        _s208 = _norm208(_dd208.get("start", "?")); _e208 = _norm208(_dd208.get("end", "?"))
        try:
            _dur208 = (int(str(_e208).split(":")[0]) - int(str(_s208).split(":")[0])) % 24 or 24
            _cur208 = f"\nAktuell: {_s208} → {_e208} ({_dur208} Std. Ruhe 😴)"
        except: _cur208 = f"\nAktuell: {_s208} → {_e208}"
    except: _cur208 = ""
    _txt = ("⏰ Von wann soll Nicht-Stören starten?" if which == "start" else "⏰ Bis wann soll Nicht-Stören laufen?") + _cur208
    await _cb_edit(update, _txt + "\n\nEinfach die Stunde antippen!", InlineKeyboardMarkup(rows))
async def dnd_summary_cmd(update, ctx):
    uid = update.effective_user.id if update.effective_user else 0
    pend = get_pending(uid); d = get_dnd(uid)
    if not pend:
        await _cb_edit(update, "🌅 Während du weg warst\n\nNix verpasst - kein Spiel deiner Favoriten in der Zeit! 😊", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])); return
    try: ctx.user_data["dnd_summary_list"] = list(pend)
    except: pass
    clear_pending(uid)  # V203: Zettel weg - Knopf verschwindet beim naechsten Hauptmenue!
    txt, kb = _dnd_summary_build(uid, pend, d["spoiler"])
    await _cb_edit(update, txt, kb)
async def dnd_reveal_cmd(update, ctx, eid, lg):
    target = update.message or update.callback_query.message
    ft = _dnd_final_text(lg, eid, "")
    _m = await target.reply_text(ft or "Ergebnis konnte gerade nicht geladen werden - versuch es in 2 Min nochmal!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]]))
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m.message_id)
    except: pass
async def dnd_reveal_all_cmd(update, ctx):
    target = update.message or update.callback_query.message
    pend = ctx.user_data.get("dnd_summary_list", []) or []
    if not pend:
        await target.reply_text("Nix mehr zum Zeigen - der Zettel ist schon leer! 😊", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])); return
    lines = ["🌅 Alle Ergebnisse:\n"]
    for q in pend:
        ft = _dnd_final_text(q["lg"], q["eid"], q["name"])
        lines.append(f"• {ft or q['name']}")
    _m = await target.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]]))
    try: _chain_add(update.effective_user.id if update.effective_user else 0, _m.message_id)
    except: pass
async def dnd_summary_job(context):
    # V212: Laeuft alle 5 Min - schickt die Zusammenfassung automatisch, sobald DND AUS ist UND was auf dem Zettel steht!
    # V212: Kein 10-Min-Fenster mehr! Vorher: Fenster verpasst (Neustart) = Zusammenfassung nie gekommen, /start noetig!
    # V212: Marker ist jetzt pro Spiele-Batch (nicht pro Tag) - sonst wuerde ein 2. DND-Test am selben Tag blockiert!
    try:
        sett = load_settings() or {}
        now = datetime.now(BERLIN)
        for uid_str, sd in sett.items():
            try: uid = int(uid_str)
            except: continue
            pend = get_pending(uid)
            if not pend: continue
            # V212: DND gerade aktiv? -> Noch sammeln, NIX schicken!
            try:
                if dnd_active(uid): continue
            except: pass
            # V212: Gleicher Batch schon geschickt? -> Nicht doppelt! (Neuer Batch = neue Spiele = schicken!)
            try: _batch = ",".join(sorted(str(x.get("eid")) for x in pend))
            except: _batch = ""
            if _batch and _redis_get(f"dnd_sent_{uid}") == _batch: continue
            d = get_dnd(uid)
            txt, kb = _dnd_summary_build(uid, pend, d["spoiler"])
            try: await context.bot.send_message(chat_id=uid, text=txt, reply_markup=kb)
            except: continue
            if _batch: _redis_set(f"dnd_sent_{uid}", _batch)
            clear_pending(uid)
    except Exception as e:
        logger.warning(f"dnd_summary_job: {e}")

async def settings_reminder_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    uid = update.effective_user.id if update.effective_user else 0
    cur = get_reminder_minutes(uid)
    def _lbl(m):
        return f"{'✅ ' if cur==m else ''}{fmt_reminder(m)}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(_lbl(180), callback_data="reminder_set:180")],
        [InlineKeyboardButton(_lbl(120), callback_data="reminder_set:120")],
        [InlineKeyboardButton(_lbl(60), callback_data="reminder_set:60")],
        [InlineKeyboardButton(_lbl(30), callback_data="reminder_set:30")],
        [InlineKeyboardButton("🔕 Aus" if cur is not None else "✅ Aus", callback_data="reminder_set:off")],
        [InlineKeyboardButton("⬅️ Zurück zu Einstellungen", callback_data="settings")],
    ])
    await _cb_edit(update, "⏰ Reminder-Zeit\n\nWann soll ich dich erinnern?\nEine Zeit für alle Favoriten!\nSpielen 2 deiner Favoriten gleichzeitig, kriegst du 1 Nachricht für beide!", kb)
async def nhl_help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Tabellen", callback_data="tables")]])
    await target.reply_text(NHL_HELP_TEXT, reply_markup=kb)
_REMINDER_SENT = set()
# --- V89: Benachrichtigungen Hub + Live-Scores ---
# V113: Schließen-Kette: Fenster + deine getippten Nachrichten dazu (1en) + Listen dazwischen!
_CLOSE_CHAIN = {}
_CLOSE_NUM_MAP = {}  # V201: (uid, bot_fenster_mid) -> user_zahlen_mid - damit 'Fenster schliessen' die Zahl mitloescht!
_MYWEEK_SUB={}  # (uid, kind) -> message_id des Unter-Fensters aus Meine Woche (News/Next/Tabellen/CFP)
_MYWEEK_MSG={}  # V250: uid -> message_id der AKTUELLEN Meine-Woche-Nachricht - die wird NIE auto-geschlossen (wie Hauptmenue)!
_MYWEEK_CACHE={}  # uid -> (timestamp, lines, has_ncaaf)
def _chain_add(uid, mid):
    try:
        if not uid or not mid: return
        _CLOSE_CHAIN.setdefault(int(uid), [])
        if int(mid) not in _CLOSE_CHAIN[int(uid)]: _CLOSE_CHAIN[int(uid)].append(int(mid))
        # V201: Liste bleibt ueber alle Flows bestehen (kein Clear mehr bei neuem Flow)! Cap 100, damit nix rausfaellt!
                # V201: Cap 20 -> 100! Vorher fielen nach 6-7 Spielen alte Zahlen + Fenster raus -> 'Alle schliessen' brauchte 2x Druecken!
        _CLOSE_CHAIN[int(uid)] = _CLOSE_CHAIN[int(uid)][-100:]
    except: pass
def _chain_clear(uid):
    try: _CLOSE_CHAIN[int(uid)] = []
    except: pass
def _chain_remove(uid, mid):
    # V167: Nur DIESE eine Nachricht aus der Kette nehmen - Rest bleibt!
    try:
        if not uid or not mid: return
        _CLOSE_CHAIN[int(uid)] = [m for m in (_CLOSE_CHAIN.get(int(uid), []) or []) if int(m) != int(mid)]
    except: pass
async def _chain_delete_all(ctx, uid, current_mid=None):
    try:
        _ids = list(_CLOSE_CHAIN.get(int(uid), []) or [])
        if current_mid: _ids.append(int(current_mid))
        # V201: Dedupe + Bremse! Vorher: uralte/ doppelte IDs + 50+ Deletes auf einmal -> Telegram Flood-Limit -> nix ging mehr!
        _seen201 = set(); _ids = [m for m in _ids if not (int(m) in _seen201 or _seen201.add(int(m)))]
        for _mid in _ids:
            try: await ctx.bot.delete_message(chat_id=int(uid), message_id=int(_mid))
            except: pass
            try: await asyncio.sleep(0.05)
            except: pass
        # V201: Auch alle gemappten Zahlen loeschen (Falls eine Zahl nicht in der Kette steht)!
        try:
            _num_ids = [v for (u, b), v in list(_CLOSE_NUM_MAP.items()) if int(u) == int(uid)]
            for _nid in _num_ids:
                try: await ctx.bot.delete_message(chat_id=int(uid), message_id=int(_nid))
                except: pass
            for _k in [k for k in list(_CLOSE_NUM_MAP.keys()) if int(k[0]) == int(uid)]: _CLOSE_NUM_MAP.pop(_k, None)
        except: pass
        _chain_clear(uid)
    except: pass

async def _autoclose_prev(ctx, uid, keep_mid=None):
    # V248: Auto-Schliessen AN? -> Alle bisherigen Fenster zu (wie 'Alle Fenster schliessen'), ausser keep_mid (z.B. Meine Woche bleibt!) + Hauptmenue (steht nie in der Kette)!
    try:
        if not get_autoclose(uid): return
        _ids = list(_CLOSE_CHAIN.get(int(uid), []) or [])
        # V250: Meine Woche ist geschuetzt wie das Hauptmenue - nie auto-schliessen!
        _prot250 = None
        try: _prot250 = _MYWEEK_MSG.get(int(uid))
        except: pass
        _seen = set(); _del = []
        for _m in _ids:
            if int(_m) in _seen: continue
            _seen.add(int(_m))
            if keep_mid and int(_m) == int(keep_mid): continue
            if _prot250 and int(_m) == int(_prot250): continue
            _del.append(int(_m))
        for _mid in _del:
            try: await ctx.bot.delete_message(chat_id=int(uid), message_id=int(_mid))
            except: pass
            try: await asyncio.sleep(0.05)
            except: pass
            # Zahl zu dem Fenster mitloeschen (wie beim Schliessen-Button)!
            try:
                _num = _CLOSE_NUM_MAP.pop((int(uid), int(_mid)), None)
                if _num:
                    try: await ctx.bot.delete_message(chat_id=int(uid), message_id=int(_num))
                    except: pass
            except: pass
        # Geloeschte aus der Kette nehmen, keep_mid + geschuetzte Meine Woche behalten!
        try: _CLOSE_CHAIN[int(uid)] = [m for m in _ids if (keep_mid and int(m) == int(keep_mid)) or (_prot250 and int(m) == int(_prot250))]
        except: pass
    except: pass

async def _cb_edit(update, text, kb):
    # V95: /start-Hauptmenue bleibt IMMER da! Nie bearbeiten!
    # Wenn der Klick aus dem Hauptmenue kommt, NEUE Nachricht als Fenster schicken, Hauptmenue bleibt oben!
    try:
        if update.callback_query and update.callback_query.message:
            _mt = (update.callback_query.message.text or "") if getattr(update.callback_query.message, "text", None) else ""
            _uid_cb = update.effective_user.id if update.effective_user else 0
            if _mt.startswith("Willkommen beim USA Sport Radar"):
                # V201: _chain_clear RAUS! Vorher wurde bei jedem neuen Flow aus dem Hauptmenue die ganze Schliessen-Liste geloescht -> 'Alle schliessen' hat nur den letzten Flow erwischt (2 von 3 weg, Rest blieb)! Jetzt bleibt die Liste ueber alle Flows bestehen!
                await _autoclose_prev(ctx, _uid_cb)
                _m = await update.callback_query.message.reply_text(text, reply_markup=_with_close(kb))
                try: _chain_add(_uid_cb, _m.message_id)
                except: pass
                return _m  # V210: Fenster zurueckgeben, damit Aufrufer die ID mappen kann!
            # V201: Klick AUS Meine Woche (News/Next/Tabellen/CFP) -> NEUE Nachricht, Meine Woche bleibt stehen! Vorher wurde Meine Woche ueberschrieben -> weg!
            if _mt.startswith("\U0001f4c5 Meine Woche"):
                try:
                    _data196 = (update.callback_query.data or "") if update.callback_query else ""
                    _kind196 = _data196.split(":")[0] if _data196 else ""
                    if _kind196 in ("news", "next", "tables", "cfp_top25"):
                        _key196 = (_uid_cb, _kind196)
                        _mid196 = _MYWEEK_SUB.get(_key196)
                        if _mid196:
                            try:
                                await update.callback_query.bot.edit_message_text(chat_id=_uid_cb, message_id=_mid196, text=text, reply_markup=_with_close(kb)); return update.callback_query.message  # V210
                            except: pass
                        await _autoclose_prev(ctx, _uid_cb, keep_mid=update.callback_query.message.message_id)
                        _m196 = await update.callback_query.message.reply_text(text, reply_markup=_with_close(kb))
                        try:
                            _chain_add(_uid_cb, _m196.message_id); _MYWEEK_SUB[_key196] = _m196.message_id
                        except: pass
                        return _m196  # V210
                except: pass
            # Fenster wird bearbeitet (gleiche Nachricht) -> ID merken!
            try: _chain_add(_uid_cb, update.callback_query.message.message_id)
            except: pass
            await update.callback_query.message.edit_text(text, reply_markup=_with_close(kb)); return update.callback_query.message  # V210
    except Exception:
        pass
    try:
        target = update.message or (update.callback_query.message if update.callback_query else None)
        if target is not None:
            _m2 = await target.reply_text(text, reply_markup=_with_close(kb))
            try:
                _uid2 = update.effective_user.id if update.effective_user else 0
                _chain_add(_uid2, _m2.message_id)
            except: pass
            return _m2  # V210: Fenster zurueckgeben (Zahl-Flow!)
    except Exception: pass
def _is_main_msg(msg):
    try:
        _tx = (msg.text or "") if getattr(msg, "text", None) else ""
        return _tx.startswith("Willkommen beim USA Sport Radar")
    except: return False

def _with_close(kb):
    try:
        rows = [list(r) for r in kb.inline_keyboard]
        if any(getattr(b, "callback_data", None) == "close" for r in rows for b in r): return kb
        rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
        return InlineKeyboardMarkup(rows)
    except: return kb
_LIVE_MSG_IDS = {}
# V222: Letzter Live-Text pro Spiel - damit der XP-Edit die TD-Nachricht findet!
_LIVE_LAST_TXT = {}
async def _live_delete_prev(context, uid, eid):
    # V222: Rollende Live-Nachrichten! Alte Nachricht(en) dieses Spiels loeschen, damit nur die neueste steht!
    try:
        _ids = list(_LIVE_MSG_IDS.get((uid, str(eid)), []))
        for _mid in _ids:
            try: await context.bot.delete_message(chat_id=uid, message_id=_mid)
            except: pass
        if _ids:
            _LIVE_MSG_IDS[(uid, str(eid))] = []
            _save_live_msg_ids()
    except: pass
_LIVE_MSG_FILE = '/tmp/live_msg_ids.json'
try:
    import json as _json_msg
    _tmp = _json_msg.load(open(_LIVE_MSG_FILE))
    for _k,_v in _tmp.items():
        _uid,_eid = _k.split('|',1); _LIVE_MSG_IDS[(int(_uid), _eid)] = list(_v)
except: pass
def _save_live_msg_ids():
    try:
        import json as _json2
        _d = {f"{k[0]}|{k[1]}": list(v) for k,v in _LIVE_MSG_IDS.items()}
        open(_LIVE_MSG_FILE,'w').write(_json2.dumps(_d))
    except: pass
async def _live_send(context, uid, eid, text):
    # V222: Rollend! Vor jeder neuen Live-Nachricht die alte(n) dieses Spiels loeschen - nur die neueste steht im Chat!
    # (Nur TD->XP wird NICHT hier geloescht, sondern per Edit geaendert - siehe Poller + Scorer-Job!)
    try:
        try: await _live_delete_prev(context, uid, eid)
        except: pass
        m = await context.bot.send_message(chat_id=uid, text=text)
        if m and getattr(m, "message_id", None):
            _LIVE_MSG_IDS.setdefault((uid, str(eid)), []).append(int(m.message_id))
        _LIVE_LAST_TXT[(uid, str(eid))] = text
        return m
    except Exception:
        try:
            m2 = await context.bot.send_message(chat_id=uid, text=text)
            if m2 and getattr(m2, "message_id", None):
                _LIVE_MSG_IDS.setdefault((uid, str(eid)), []).append(int(m2.message_id))
            _LIVE_LAST_TXT[(uid, str(eid))] = text
            return m2
        except: return None


# ===== V134: News + Liga-Breaking + Spiel-Breaking in einem Rutsch! =====
_ESPN_NEWS_SPORT = {"NFL": ("football","nfl"), "NCAAF": ("football","college-football"), "NBA": ("basketball","nba"), "NHL": ("hockey","nhl"), "MLB": ("baseball","mlb")}
_LIGA_BREAKING_KEYS = ["international series","london","munich","munchen","madrid","berlin","schedule","super bowl","playoffs","trade deadline","expansion","rule change","new stadium","franchise"]
# V167: Spielplan / Flex / Verschiebung! Schefter-Flex (Raiders @ Browns -> SNF) hatte KEINEN Trigger (kein "schedule" im Text) -> nie gemeldet!
# WICHTIG: "sunday night football" allein triggert NICHT (sonst jede SNF-Vorschau = Breaking)! Nur mit flex/move/rescheduled/postponed!
_SCHEDULE_CHANGE_KEYS = ["flex","flexed","flex scheduling","flex game","will move","moves to","move to sunday","game will move","game moved","rescheduled","schedule change","kickoff change","kickoff moved","postponed","time change","doubleheader","makeup game","game postponed","game rescheduled"]
# V134: Pro Liga eigene Begriffe! Super Bowl nur NFL, NBA Finals nur NBA, usw!
_LIGA_BREAKING_PER_LEAGUE = {
 "NFL": ["super bowl","draft","trade deadline","international series","london","munich","munchen","madrid","berlin","schedule","playoffs","franchise tag","rule change","expansion","new stadium","flex","flexed","flex scheduling","flex game","will move","moves to","move to sunday","game will move","game moved","rescheduled","schedule change","kickoff change","kickoff moved","postponed","time change","game postponed","game rescheduled"],
 "NBA": ["nba finals","draft","trade deadline","all-star","playoffs","play-in","schedule","expansion","rule change","postponed","rescheduled","game moved","schedule change","time change","game postponed","game rescheduled"],
 "NHL": ["stanley cup","trade deadline","winter classic","playoffs","draft","schedule","expansion","rule change","postponed","rescheduled","game moved","schedule change","time change","game postponed","game rescheduled"],
 "MLB": ["world series","trade deadline","draft","playoffs","opening day","schedule","expansion","rule change","postponed","rescheduled","game moved","schedule change","time change","doubleheader","makeup game","game postponed","game rescheduled"],
 "NCAAF": ["college football playoff","national championship","bowl games","draft","transfer portal","schedule","playoffs","rule change","postponed","rescheduled","game moved","schedule change","time change","game postponed","game rescheduled"],
}
def get_league_breaking_map(uid):
    try:
        v=load_settings().get(str(uid),{}).get("league_breaking", True)
        if isinstance(v, dict):
            return {lg: bool(v.get(lg, True)) for lg in ["NFL","NBA","NHL","MLB","NCAAF"]}
        if isinstance(v, bool):
            return {lg: bool(v) for lg in ["NFL","NBA","NHL","MLB","NCAAF"]}
        return {lg: True for lg in ["NFL","NBA","NHL","MLB","NCAAF"]}
    except: return {lg: True for lg in ["NFL","NBA","NHL","MLB","NCAAF"]}
def set_league_breaking_league(uid, lg, val):
    try:
        s=load_settings(); s.setdefault(str(uid),{})
        cur=s[str(uid)].get("league_breaking", True)
        if not isinstance(cur, dict): cur={x: bool(cur) for x in ["NFL","NBA","NHL","MLB","NCAAF"]}
        cur[lg]=bool(val); s[str(uid)]["league_breaking"]=cur; save_settings(s)
    except: pass
def get_news_league_open(uid):
    try: return bool(load_settings().get(str(uid),{}).get("news_league_open", False))
    except: return False
def set_news_league_open(uid, val):
    try:
        s=load_settings(); s.setdefault(str(uid),{})["news_league_open"]=bool(val); save_settings(s)
    except: pass
# V134: RedZone / X-Sprache! "Travis Kelce is OUT!" muss treffen! Aber nur als ganzes Wort: " is out", nicht "shout out"!
_BREAKING_KEYS = ["ruled out","out for","out indefinitely","out for season","season-ending","torn acl","torn achilles","ejected","ejection","suspended","carted off","carted","on a cart"," is out"," is out with"," declared out"," listed as out"," out for the game"," out for the rest"," will not return"," done for"," will miss"," sidelined"," is done"," out for tonight"," out for today","air cast","stretcher","helped off","locker room","not putting weight","not putting any weight","taken to the locker room","headed to the locker room","carted to locker room"]

# ===== V135 HELPERS =====
def _v135_slash(v):
    try:
        s=str(v or "").strip()
        if "/" in s: return s
        if "-" in s:
            a,b=s.split("-",1)
            a=a.strip(); b=b.strip()
            if a.isdigit() and b.isdigit(): return f"{a}/{b}"
        return s
    except: return str(v or "")
def _v135_stat_value(sd, wanted):
    try:
        flat={}
        for k,v in (sd or {}).items():
            flat[str(k).lower().replace(" ","").replace("_","")]=v
        for w in wanted:
            wl=w.lower().replace(" ","").replace("_","")
            if wl in flat and str(flat[wl]).strip() not in ("","-","None"): return str(flat[wl]).strip()
            for k,v in flat.items():
                if wl in k or k in wl:
                    if str(v).strip() not in ("","-","None"): return str(v).strip()
        return ""
    except: return ""
def _v135_is_finished(ev):
    try:
        st=(ev.get("status",{}) or {}).get("type",{}).get("state","") or ""
        if st=="post": return True
        if st=="in": return False
        _,dt=fmt_dt(ev.get("date","") or "")
        if dt:
            from datetime import datetime as _dt
            if (_dt.now(BERLIN)-dt).total_seconds()>4*3600: return True
        return False
    except: return False
def _espn_ap_top25():
    try:
        r=requests.get("https://site.api.espn.com/apis/site/v2/sports/football/college-football/rankings",timeout=10)
        d=r.json() or {}
        ranks=d.get("rankings") or []
        chosen=None
        for rk in ranks:
            if "ap" in str(rk.get("name","") or "").lower(): chosen=rk; break
        if not chosen and ranks: chosen=ranks[0]
        if not chosen: return []
        out=[]
        for e in (chosen.get("ranks") or [])[:25]:
            # V136: Team steckt in ESPN mal unter team.displayName, mal unter team.name, mal nur abbreviation!
            tm=e.get("team") or {}
            if isinstance(tm, str): tm={"displayName": tm}
            disp=str(tm.get("displayName","") or tm.get("shortDisplayName","") or tm.get("name","") or tm.get("nickname","") or "").strip()
            short=str(tm.get("shortDisplayName","") or tm.get("nickname","") or tm.get("name","") or disp or "").strip()
            abbr=str(tm.get("abbreviation","") or tm.get("abbr","") or "").strip()
            # Fallback: location + nickname, z.B. "Pittsburgh" + "Panthers"
            if not disp:
                loc=str(tm.get("location","") or "").strip(); nick=str(tm.get("nickname","") or "").strip()
                if loc or nick: disp=f"{loc} {nick}".strip(); short=short or nick or disp
            # Letzter Fallback: Abkürzung als Name, NIE leer lassen!
            if not disp: disp=abbr or str(e.get("teamId","") or "")
            if not short: short=disp or abbr
            if not disp: continue
            rec=str(e.get("recordSummary","") or e.get("record","") or "")
            W=L=0
            try:
                parts=rec.replace(" ","").split("-")
                if len(parts)>=2: W=int(parts[0]); L=int(parts[1])
            except: pass
            out.append((disp,short,abbr,W,L,0,""))
        return out
    except: return []

# V179: Favoriten-Match NUR auf Schul-Name, NIE aufs Maskottchen! Pitt Panthers darf NICHT Georgia State Panthers matchen!
def _fav_school_tokens(fav_name):
    try:
        _n=(fav_name or "").split(" (")[0].strip().lower()
        _words=_n.replace("&","&").split()
        if not _words: return []
        # Letztes Wort = Maskottchen (Panthers, Longhorns, Midshipmen...) -> WEG! Rest = Schule!
        if len(_words)>=2: _school=_words[:-1]
        else: _school=_words
        return _school
    except: return []
def _is_fav_team(disp, favs, league=None):
    # V180: Schule muss EXAKT gleich sein! Texas (Longhorns) != Texas A&M (Aggies)!
    try:
        _clean=(disp or "").split(" (")[0].strip().lower()
        if not _clean: return False
        _disp_school=_fav_school_tokens(_clean)
        if len(_clean.split())==1: _disp_school=[_clean]
        for _f in (favs or []):
            _flg=_f.split(" (")[-1].replace(")","").strip() if " (" in _f else ""
            if league and _flg and _flg!=league: continue
            _school=_fav_school_tokens(_f)
            if not _school: continue
            if len(_school)!=len(_disp_school): continue
            _ok=True
            for _a,_b in zip(_school, _disp_school):
                if _a==_b: continue
                if _a in ("pitt","pittsburgh") and _b in ("pitt","pittsburgh"): continue
                _ok=False; break
            if _ok: return True
        return False
    except: return False
async def _loading_start(target, text="⏳ Ich hole die Daten... einen Moment"):
    # V179: Kurze Lade-Nachricht, wird nachher wieder geloescht!
    try: return await target.reply_text(text)
    except: return None
async def _loading_done(ctx, user_id, msg):
    try:
        if msg: await ctx.bot.delete_message(chat_id=user_id, message_id=msg.message_id)
    except: pass

_CFP_CACHE={"t":0,"data":([],"")}
def _espn_cfp_top25():
    # V189 CACHING: CFP ändert sich nur 1x pro Woche (dienstags)! 15 Min Cache = viel schneller, nie veraltet!
    try:
        import time as _time
        if _time.time()-_CFP_CACHE.get("t",0)<900 and _CFP_CACHE.get("data",([],""))[0]:
            return _CFP_CACHE["data"]
    except: pass
    try:
        r=requests.get("https://site.api.espn.com/apis/site/v2/sports/football/college-football/rankings",timeout=10)
        d=r.json() or {}
        ranks=d.get("rankings") or []
        chosen=None
        for rk in ranks:
            _n=str(rk.get("name","") or "").lower()
            if "cfp" in _n or "playoff" in _n or "college football playoff" in _n: chosen=rk; break
        if not chosen:
            for rk in ranks:
                if "committee" in str(rk.get("name","") or "").lower(): chosen=rk; break
        if not chosen: return [], ""
        _label=str(chosen.get("name","") or "CFP Top 25")
        out=[]
        for e in (chosen.get("ranks") or [])[:25]:
            tm=e.get("team") or {}
            if isinstance(tm, str): tm={"displayName": tm}
            # V181: ESPN Ranking: location="Georgia", nickname="Georgia" (Schule kurz!), name="Bulldogs" (Maskottchen)!
            # Location+nickname = "Georgia Georgia" FALSCH! Location+name = "Georgia Bulldogs" RICHTIG!
            loc=str(tm.get("location","") or "").strip(); _mascot=str(tm.get("name","") or "").strip(); nick=str(tm.get("nickname","") or "").strip()
            _dn=str(tm.get("displayName","") or "").strip()
            if loc and _mascot and _mascot.lower()!=loc.lower(): disp=f"{loc} {_mascot}"
            elif _dn and loc and not _dn.lower().startswith(loc.lower()): disp=f"{loc} {_dn}"
            elif _dn: disp=_dn
            else: disp=str(tm.get("shortDisplayName","") or _mascot or "").strip()
            short=loc or str(tm.get("shortDisplayName","") or nick or disp or "").strip()
            rec=str(e.get("recordSummary","") or e.get("record","") or "")
            out.append((disp, short, rec))
        try:
            import time as _time2
            _CFP_CACHE["t"]=_time2.time(); _CFP_CACHE["data"]=(out, _label)
        except: pass
        return out, _label
    except: return [], ""

# V183: ECHTER Startwert! Ranking vom 10.11.2026 (NCAA.com) - damit Pfeile sofort stimmen, auch beim allerersten Öffnen!
_CFP_PREV_SEED={"georgia bulldogs":1,"utah utes":2,"alabama crimson tide":3,"ucla bruins":4,"notre dame fighting irish":5,"texas longhorns":6,"miami hurricanes":7,"tennessee volunteers":8,"indiana hoosiers":9,"byu cougars":10,"kentucky wildcats":11,"texas tech red raiders":12,"wake forest demon deacons":13,"houston cougars":14,"iowa hawkeyes":15,"oregon ducks":16,"south carolina gamecocks":17,"usc trojans":18,"ole miss rebels":19,"ohio state buckeyes":20,"lsu tigers":21,"missouri tigers":22,"arizona wildcats":23,"boise state broncos":24,"oklahoma state cowboys":25,
# Aliase: Kurzformen, falls ESPN nur Kurzname liefert!
"georgia":1,"utah":2,"alabama":3,"ucla":4,"notre dame":5,"texas":6,"miami":7,"tennessee":8,"indiana":9,"byu":10,"kentucky":11,"texas tech":12,"wake forest":13,"houston":14,"iowa":15,"oregon":16,"south carolina":17,"usc":18,"southern cal":18,"ole miss":19,"ohio state":20,"lsu":21,"missouri":22,"arizona":23,"boise state":24,"oklahoma state":25}
_CFP_DATES=[(3,11,"Di, 03.11."),(10,11,"Di, 10.11."),(17,11,"Di, 17.11."),(24,11,"Di, 24.11. 19:30 ET (01:30 bei uns)"),(1,12,"Di, 01.12. 19:00 ET (01:00 bei uns)"),(6,12,"So, 06.12. Selection Day - FINALES Ranking!")]
def _cfp_next_text():
    try:
        from datetime import date as _d
        _today=_d.today()
        for _day,_mon,_label in _CFP_DATES:
            _dt=_d(2026,_mon,_day)
            if _dt>=_today: return f"\n📅 Nächstes Ranking: {_label}"
        return "\n📅 Nächstes Ranking: Nächste Season (ab Anfang Nov)!"
    except: return ""
# V184: Kurz-Namen! Texas=Longhorns, Texas A&M=Aggies - KEINE Verwechslung! Nur Miami (FL) braucht Zusatz!
_CFP_SHORT={"georgia bulldogs":"Georgia","utah utes":"Utah","alabama crimson tide":"Alabama","ucla bruins":"UCLA","texas longhorns":"Texas","notre dame fighting irish":"Notre Dame","miami hurricanes":"Miami (FL)","indiana hoosiers":"Indiana","tennessee volunteers":"Tennessee","byu cougars":"BYU","wake forest demon deacons":"Wake Forest","texas tech red raiders":"Texas Tech","oregon ducks":"Oregon","ohio state buckeyes":"Ohio State","iowa hawkeyes":"Iowa","kentucky wildcats":"Kentucky","boise state broncos":"Boise State","usc trojans":"USC","arizona wildcats":"Arizona","houston cougars":"Houston","south carolina gamecocks":"South Carolina","oklahoma sooners":"Oklahoma","louisville cardinals":"Louisville","florida gators":"Florida","ole miss rebels":"Ole Miss","texas a&m aggies":"Texas A&M","lsu tigers":"LSU","missouri tigers":"Missouri","oklahoma state cowboys":"Oklahoma State","florida state seminoles":"Florida State","georgia tech yellow jackets":"Georgia Tech","miami (oh) redhawks":"Miami (OH)","arizona state sun devils":"Arizona State","mississippi state bulldogs":"Mississippi State","north carolina tar heels":"North Carolina","penn state nittany lions":"Penn State","michigan wolverines":"Michigan","wisconsin badgers":"Wisconsin","nebraska cornhuskers":"Nebraska","clemson tigers":"Clemson","smu mustangs":"SMU","vanderbilt commodores":"Vanderbilt","auburn tigers":"Auburn","northwestern wildcats":"Northwestern","duke blue devils":"Duke","pittsburgh panthers":"Pitt","navy midshipmen":"Navy","illinois fighting illini":"Illinois","tcu horned frogs":"TCU","kansas state wildcats":"Kansas State","kansas jayhawks":"Kansas","west virginia mountaineers":"West Virginia","colorado buffaloes":"Colorado","utah state aggies":"Utah State"}
def _cfp_short(disp, short=""):
    _k=(disp or "").lower().strip()
    if _k in _CFP_SHORT: return _CFP_SHORT[_k]
    # Fallback: Kurzform von ESPN (z.B. "Texas") oder Schul-Name ohne Maskottchen
    if short and short not in (disp or ""): return short
    return disp or short or ""
async def cfp_top25_cmd(update, ctx):
    target = update.message or update.callback_query.message
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    _load = await _loading_start(target, "⏳ Ich hole die CFP Top 25... einen Moment")
    favs = favs_for(user.id) if user else []
    rows, _label = _espn_cfp_top25()
    await _loading_done(ctx, user.id if user else 0, _load)
    # V182: Pfeile vs. letzte Woche! Prev-Ranking in Redis (ueberlebt Neustarts)!
    # V185 FIX: Mover blieben nur beim 1. Öffnen! Fehler: Bot hat bei JEDEM Öffnen aktuelles Ranking als Prev gespeichert -> Diff 0!
    # NEU: cfp_cur = zuletzt gesehenes Ranking, cfp_prev = Ranking DAVOR! Nur shiften wenn sich Ranking WIRKLICH geändert hat!
    _prev={}; _cur_saved={}
    try:
        _p=_redis_get("cfp_prev")
        if isinstance(_p, dict): _prev=_p
    except: pass
    try:
        _c=_redis_get("cfp_cur")
        if isinstance(_c, dict): _cur_saved=_c
    except: pass
    _new_prev={}
    for _i,(_d,_s,_r) in enumerate(rows,1): _new_prev[_d.lower()]=_i
    if not _prev and not _cur_saved:
        try:
            _first_disp=(rows[0][0] if rows else "").lower()
            if "georgia" in _first_disp:
                _prev=dict(_CFP_PREV_SEED); _cur_saved=dict(_new_prev)
                _redis_set("cfp_prev", _prev); _redis_set("cfp_cur", _cur_saved)
        except: pass
    elif _new_prev!=_cur_saved and _cur_saved:
        _prev=dict(_cur_saved); _cur_saved=dict(_new_prev)
        try: _redis_set("cfp_prev", _prev); _redis_set("cfp_cur", _cur_saved)
        except: pass
    elif not _cur_saved and _prev:
        # V186 MIGRATION: cfp_cur gab es vor V185 noch nicht! Wenn cfp_prev existiert, ist das NICHT letzte Woche,
        # sondern das AKTUELLE Ranking (V183/V184 haben es bei jedem Öffnen überschrieben)! -> Seed vom 10.11. wiederherstellen!
        try:
            _first_disp3=(rows[0][0] if rows else "").lower()
            if "georgia" in _first_disp3:
                _prev=dict(_CFP_PREV_SEED); _cur_saved=dict(_new_prev)
                _redis_set("cfp_prev", _prev); _redis_set("cfp_cur", _cur_saved)
        except: pass
    elif not _cur_saved:
        try: _redis_set("cfp_cur", _new_prev)
        except: pass
    # V185 EINMALIG: Wenn Prev == Cur ist, ist das der V183/V184-Bug (History überschrieben)! -> Seed vom 10.11. wiederherstellen!
    if _prev and _cur_saved and _prev==_cur_saved:
        try:
            _first_disp2=(rows[0][0] if rows else "").lower()
            if "georgia" in _first_disp2:
                _prev=dict(_CFP_PREV_SEED)
                _redis_set("cfp_prev", _prev)
        except: pass
    # V185: _new_prev wird oben schon korrekt als Cur/Prev gespeichert!
    if not rows:
        await _cb_edit(update, "🏆 CFP Top 25\n\nGerade kein CFP-Ranking verfügbar.\nCheck später nochmal!", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="playoffs_league:NCAAF")]])); return
    lines=["🏆 CFP Top 25 | Nächstes: Di 24.11.\n⭐ = Favorit\n"]
    # V184: KEINE Pfeile pro Zeile mehr! Stattdessen unten 3 kompakte Zeilen: Mover / Neu / Raus!
    _movers=[]; _news=[]; _outs=[]
    _cur_keys=set()
    for i,(disp, short, rec) in enumerate(rows,1):
        is_fav=_is_fav_team(disp, favs, "NCAAF")
        star=" ⭐" if is_fav else ""
        _show=_cfp_short(disp, short)  # V184: Kurz-Name! Texas=Longhorns, Texas A&M=Aggies!
        _rec=f" {rec}" if rec else ""
        lines.append(f"{i}. {_show}{_rec}{star}")
        _key=(disp or "").lower(); _cur_keys.add(_key)
        _old=_prev.get(_key)
        if _old is None:
            for _k,_v in _prev.items():
                if _key.startswith(_k) or _k.startswith(_key): _old=_v; break
        if _old is None: _news.append(_show)
        elif abs(_old-i)>=2: _movers.append((_old-i, f"{_show} {'↑'+str(_old-i) if _old>i else '↓'+str(i-_old)}"))
    # Raus: war letzte Woche drin, jetzt nicht mehr!
    # V188 FIX: Nur echte volle Namen! Seed-Aliase wie "southern cal" (= USC!), "lsu", "texas" sind KEINE eigenen Teams!
    # _CFP_SHORT enthält nur echte volle Namen - alles andere wird übersprungen!
    for _k,_v in _prev.items():
        if _k not in _CFP_SHORT: continue
        if _k not in _cur_keys and not any(_k.startswith(_c) or _c.startswith(_k) for _c in _cur_keys):
            _outs.append(_cfp_short(_k, ""))
    _movers.sort(key=lambda x: -abs(x[0]))
    # V187: Mover nur Top 6 (größte Sprünge), sonst wird die Zeile 4 Zeilen lang!
    if _movers: lines.append("\n📈 Mover: "+", ".join(_m[1] for _m in _movers[:6]))
    if _news: lines.append("🆕 Neu: "+", ".join(_news))
    # V187 FIX: [:6] stand hinter dem join -> hat den STRING auf 6 Zeichen gekürzt ("LSU, M")! Jetzt: erst Liste kürzen, dann joinen!
    # + Duplikate ohne Groß/Klein-Unterschied entfernen (LSU vs. lsu aus Seed-Aliasen)!
    if _outs:
        _seen=set(); _outs_clean=[]
        for _o in _outs:
            if not _o: continue
            _k=_o.lower()
            if _k in _seen: continue
            _seen.add(_k); _outs_clean.append(_o)
        lines.append("👋 Raus: "+", ".join(_outs_clean[:6]))
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("🏆 CFP Playoffs", callback_data="playoffs_cfp:NCAAF")],[InlineKeyboardButton("🥣 Bowl Games", callback_data="playoffs_bowls:NCAAF")],[InlineKeyboardButton("⬅️ Zurück", callback_data="playoffs_league:NCAAF")]])
    await _cb_edit(update, "\n".join(lines), kb)

_TEAMS_MAP_CACHE={}
def _espn_teams_map(league):
    # V139: Alle Teams + IDs in einem Call! Navy findet man auch in der Bye Week!
    try:
        if league in _TEAMS_MAP_CACHE: return _TEAMS_MAP_CACHE[league]
        sp,lg=_ESPN_NEWS_SPORT.get(league,("football","nfl"))
        # NCAAF/NFL: teams-Endpoint liefert alle Teams
        sport={"NFL":"football","NCAAF":"football","NBA":"basketball","NHL":"hockey","MLB":"baseball"}.get(league,"football")
        key={"NFL":"nfl","NCAAF":"college-football","NBA":"nba","NHL":"nhl","MLB":"mlb"}.get(league,"nfl")
        r=requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{key}/teams",params={"limit":1000},timeout=12)
        d=r.json() or {}
        m={}
        for entry in (d.get("sports") or [{}])[0].get("leagues") or []:
            for t in (entry.get("teams") or []):
                tm=t.get("team") or {}
                tid=str(tm.get("id","") or "")
                if not tid: continue
                for k in [tm.get("displayName",""),tm.get("shortDisplayName",""),tm.get("name",""),tm.get("nickname",""),tm.get("abbreviation",""),tm.get("location","")]:
                    if k: m[str(k).lower()]=tid
                # "Pittsburgh Panthers" -> auch "pitt", "navy midshipmen" -> "navy"
                disp=str(tm.get("displayName","") or "").lower()
                if disp:
                    for w in disp.split(): m[w]=tid
        _TEAMS_MAP_CACHE[league]=m
        return m
    except: return {}

def _espn_team_id_for(league, team_full):
    try:
        low=(team_full or "").lower().strip()
        # V139: 1) Teams-Map (findet auch Bye-Week-Teams wie Navy!)
        mp=_espn_teams_map(league)
        if low in mp: return mp[low]
        for k,v in mp.items():
            if low in k or k in low: return v
        # 2) Fallback: Scoreboard letzte Tage
        from datetime import date as _date
        for off in range(0,7):
            ds=(_date.today()-timedelta(days=off)).strftime("%Y%m%d")
            try: evs=espn_scoreboard(league,dates=ds) or []
            except: evs=[]
            for ev in evs:
                for comp in (ev.get("competitions") or [{}]):
                    for c in (comp.get("competitors") or []):
                        tm=c.get("team",{}) or {}
                        dn=str(tm.get("displayName","") or "").lower()
                        sn=str(tm.get("shortDisplayName","") or "").lower()
                        if low in dn or dn in low or low in sn or sn in low:
                            tid=tm.get("id")
                            if tid: return str(tid)
        return ""
    except: return ""
def _espn_team_news(league, team_full, limit=8):
    try:
        sp,lg=_ESPN_NEWS_SPORT.get(league,("football","nfl"))
        tid=_espn_team_id_for(league,team_full)
        if not tid:
            # V169: Auch ohne Team-ID noch RSS versuchen (statt sofort leer)!
            return _espn_rss_league_news(league, team_full, limit=limit)
        r=requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{sp}/{lg}/teams/{tid}/news",params={"limit":limit},timeout=8)
        d=r.json() or {}
        out=[]
        for a in (d.get("articles") or [])[:limit]:
            hl=(a.get("headline") or "").strip()
            link=""
            try: link=(a.get("links",{}) or {}).get("web",{}).get("href","") or ""
            except: link=""
            if not link:
                try:
                    lk=a.get("links") or []
                    if isinstance(lk,list) and lk: link=lk[0].get("href","") or ""
                except: pass
            if hl and not _v136_is_scam_news(hl, link) and not _news_is_filler(hl): out.append({"headline":hl,"link":link,"published":a.get("published","")})
        if out: return out
        # V169 Versuch 2: Liga-News-API mit team-Param
        try:
            r2=requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{sp}/{lg}/news",params={"limit":limit*2,"team":tid},timeout=8)
            d2=r2.json() or {}
            out2=[]
            for a in (d2.get("articles") or []):
                hl=(a.get("headline") or "").strip()
                if not hl or not _news_matches_team(hl, team_full) or _news_is_filler(hl): continue
                link=""
                try: link=(a.get("links",{}) or {}).get("web",{}).get("href","") or ""
                except: pass
                if hl and not _v136_is_scam_news(hl, link): out2.append({"headline":hl,"link":link,"published":a.get("published","")})
                if len(out2)>=limit: break
            if out2: return out2
        except: pass
        # V169 Versuch 3: ESPN RSS Liga-Feed gefiltert
        return _espn_rss_league_news(league, team_full, limit=limit)
    except: return []

def _v136_is_scam_news(title, link=""):
    import re as _re2
    re=_re2
    # V136: Offensichtliche Scam / Illegal-Stream Artikel rausfiltern!
    try:
        t=(title or "").strip()
        tl=t.lower()
        # Leerzeichen raus, damit "F r e e" / "L I V E" auch erkannt wird!
        nospace=re.sub(r"\s+","",tl)
        # Alles Nicht-Alphanumerische weg: "!+ 【LIVESTREAMS】" -> "livestreams" - fängt auch Sonderzeichen-Tricks!
        alnum=re.sub(r"[^a-z0-9]","",tl)
        # Harte Scam-Signale im Titel
        bad_subs=["livestream","livestreams","livefree","freeontv","ontvchannel","watchfree","freewatch",
                  "crackstream","buffstream","methstream","streameast","watchlivefree","freelive",
                  "hdq","【","】","!+","*0","*1","*2","*3","*4","*5","*6","*7","*8","*9",
                  "free hd","hd free","on tv channel","tv channel |","channel | free"]
        for b in bad_subs:
            _bn=re.sub(r"[^a-z0-9]","",b)
            if b in tl or b in nospace or (_bn and _bn in alnum): return True
        # Direkt: livestream / free + live im alnum-Text
        if "livestream" in alnum: return True
        if "livestreams" in alnum: return True
        # "LIVE Free" + "Channel" / "TV" zusammen = fast immer Scam
        if "live" in tl and "free" in tl and ("channel" in tl or " tv " in tl or "tv" in nospace): return True
        # Viele Sonderzeichen / Zahlen-Code wie HDQ*0147234
        if re.search(r"\*\d{4,}", t): return True
        if "【" in t or "】" in t: return True
        # Link check: bekannte Scam-Domains
        ll=(link or "").lower()
        for d in ["crackstreams","buffstreams","methstreams","streameast","watchfree","livetv","freestreams"]:
            if d in ll: return True
        return False
    except: return False

# ===== V169: News-Filter + ESPN-Reparatur + Liga-News =====
_NEWS_FILLER_KEYS = ["standings","team schedule","schedule, stats","stats and roster","stats, age","position, height, weight","fantasy & news","does "," play today?","schedule, time, channel","conference standings","team schedule -","news, schedule, stats",
    "fantasy","bets","betting","odds","oddsmakers","game highlights","in action against","after shootout victory","after overtime","in action",
    "preview","pregame","pre-game","pregame notes","into matchup","roster transactions","take losing streak",
    "game notes","lineups","look to","gameday","game day:",
    "practice squad","visits","takes on","laughingstock","viral post","dan's daily","pens points","musings","notebook:",
    "highlights","full highlights","projected","projection","breakdown","insider","matchup","going into","biggest test","visit"]
def _news_is_filler(title):
    try:
        tl=(title or "").lower().strip().replace("\u2019","'").replace("\u2018","'").replace("\u201c",'"').replace("\u201d",'"')
        # V175: Practice Squad ist Kleinkram - IMMER raus, auch wenn "signed" drin steht!
        if "practice squad" in tl: return True
        # V201: 'Why ...' am Anfang = fast immer Meinung/Analyse! Keine echte News!
        if tl.startswith("why "): return True
        # V201 HARTE BLOCKS - schlagen ALLE Ausnahmen (auch CFP/Free Agency)! Grund: "College Football Playoff odd..." ist Betting, obwohl CFP drin steht!
        # Echte Signings ("signs with", "agrees to") sind NICHT in dieser Liste - die bleiben erlaubt!
        # V201: Neue Luecken aus Screenshots! Prognose/Analyse/Insider/Preview-Woerter, die V192 noch durchgelassen hat!
        # "visit" (ohne s!) faengt auch "visits"! "face " mit Leerzeichen, damit "surface" nicht trifft! "stay for" faengt "Will Core Stay for..."!
        # V216: Crime/Gossip + Prediction + Blog-Reports raus! (Screenshots: "Arrest warrants / robbery",
        # "Land New Prediction", "Three Rivers Report: ... problem")
        for _hb in ("odds","oddsmakers","sportsbook","betting","trade target","trade rumors","trade rumor","to host","will host","preview","pregame","pre-game","what to watch","how to watch","be the answer","mock draft","projected","projection","predicted","prediction","predict","breakdown","opponent breakdown","insider","will stay","stay for","going into","biggest test","visit","face ","matchup","facing","lineup","lineup notes","game notes","girlfriend","boyfriend","dating","fiancee","great match for","jeff capel","jeff cap","ncaab","march madness","final four","arrest","warrant","robbery","robbed","charged with","arrested","lawsuit","sued","three rivers","report:","opinion:","column:",
        # V216: Meinungs-Stuecke aus Screenshots! "Should Carry More" = Meinung, "They're In Trouble" / "Bad News for" = Gossip/Meinung!
        # "should " mit Leerzeichen danach, damit "shoulder" (Verletzung!) NICHT trifft! "shouldn" faengt "shouldn't"!
        "should ","shouldn","in trouble","bad news for","some bad news","has some bad news",
        # V217: "Suggestion" = Meinung! ("Makes Surprising ... Suggestion") "suggest" faengt suggestion/suggests/suggested!
        # V219: "Criticism" = Meinung! ("Faces Harsh Criticism For...") "criticism" faengt criticism/criticisms!
        # V220: "Ahead Of ... Showdown" = Preview! ("Given Major Advantage Ahead Of Eagles Showdown")
        # "Why Won't / Why Doesn't / Why Don't" = Meinung mitten im Titel! ("Why Won't Steelers Call It More?")
        "suggest","criticism","ahead of","why won't","why doesn't","why don't"):
            if _hb in tl: return True
        # V175: Free Agency NIE blocken! Qualifying Offer / Signing ist echte News!
        if any(k in tl for k in ("free agency","qualifying offer","signs with","agrees to","free-agent","free agent")): return False
        # V179: CFP NIE blocken! Playoff-Ranking / Bracket ist echte News!
        if any(k in tl for k in ("cfp","college football playoff","playoff ranking","playoff bracket","selection show")): return False
        # V172: Echte Signings NIEMALS blocken! Nur leere "Roster Transactions | Team"-Listen fliegen raus!
        if "signed" in tl and ("roster move" in tl or "active roster" in tl):
            return False
        for k in _NEWS_FILLER_KEYS:
            if k in tl: return True
        if tl.startswith("does ") and "play today" in tl: return True
        return False
    except: return False
def _team_name_tokens(team_full):
    try:
        low=(team_full or "").lower()
        toks=[w for w in re.split(r"[^a-z0-9]+", low) if len(w)>=3]
        # Spitznamen / Kurzformen
        extra={"steelers":["steelers","pittsburgh"],"penguins":["penguins","pens","pittsburgh"],"pirates":["pirates","bucs","pittsburgh"],
                "longhorns":["longhorns","texas"],"panthers":["panthers","pitt","pittsburgh"],"midshipmen":["midshipmen","navy"],
                "eagles":["eagles"],"cowboys":["cowboys"],"packers":["packers"]}
        for k,v in extra.items():
            if k in low: toks+=v
        if "pitt" in low: toks+=["pitt","panthers"]
        if "navy" in low: toks+=["navy","midshipmen"]
        return sorted(set(toks))
    except: return []
def _news_matches_team(title, team_full):
    try:
        tl=(title or "").lower()
        toks=_team_name_tokens(team_full)
        if not toks: return True
        return any(tok in tl for tok in toks)
    except: return True
def _news_is_fresh(pub_raw, max_days=7):
    # V169: Google liefert alte Artikel (September!) - nur <=7 Tage alt!
    try:
        if not pub_raw: return True  # ESPN ohne Datum nicht wegwerfen
        from email.utils import parsedate_to_datetime as _pdt
        from datetime import datetime as _dt
        dt=_pdt(str(pub_raw).strip())
        if dt is None: return True
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        age=(datetime.now(timezone.utc)-dt).total_seconds()/86400.0
        return age<=max_days
    except: return True
def _dedupe_news(arts):
    # V173: Gleiche Story nicht zweimal! z.B. 2x Gaudreau-Statue mit anderer Formulierung.
    # Wenn 60% der wichtigen Woerter gleich sind -> zweite raus!
    try:
        _stop={"the","and","for","with","from","that","this","with","after","into","while","when","says","say","are","has","have","had","will","would","could","should"}
        kept=[]; _seen_toks=[]
        for a in (arts or []):
            hl=(a.get("headline","") or "").lower()
            toks={w for w in __import__("re").split(r"[^a-z0-9]+", hl) if len(w)>=3 and w not in _stop}
            _dup=False
            for _prev in _seen_toks:
                if not toks or not _prev: continue
                _ov=len(toks & _prev)/max(1,min(len(toks),len(_prev)))
                if _ov>=0.6: _dup=True; break
            if not _dup:
                kept.append(a); _seen_toks.append(toks)
        return kept
    except: return arts

def _espn_rss_league_news(league, team_full="", limit=8):
    # V169 Versuch 3: ESPN RSS Liga-Feed, gefiltert auf Team (wenn team_full gegeben)
    try:
        import xml.etree.ElementTree as _ET
        sp,lg=_ESPN_NEWS_SPORT.get(league,("football","nfl"))
        urls=[f"https://www.espn.com/espn/rss/{lg}/news",
              f"https://site.api.espn.com/apis/site/v2/sports/{sp}/{lg}/news?limit={limit}"]
        out=[]
        for url in urls:
            try:
                r=requests.get(url,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
                if not r.content: continue
                # JSON-Variante (site api)
                try:
                    d=r.json()
                    for a in (d.get("articles") or [])[:limit]:
                        hl=(a.get("headline") or "").strip()
                        if not hl: continue
                        if team_full and not _news_matches_team(hl, team_full): continue
                        if _news_is_filler(hl): continue
                        link=""
                        try: link=(a.get("links",{}) or {}).get("web",{}).get("href","") or ""
                        except: pass
                        if hl and not _v136_is_scam_news(hl, link): out.append({"headline":hl,"link":link,"published":a.get("published","")})
                    if out: return out
                    continue
                except: pass
                root=_ET.fromstring(r.content)
                for it in root.iter("item"):
                    tt=it.findtext("title") or ""
                    lk=it.findtext("link") or ""
                    pd=it.findtext("pubDate") or ""
                    if " - " in tt: tt=tt.rsplit(" - ",1)[0]
                    tt=tt.strip()
                    if not tt or not lk: continue
                    if team_full and not _news_matches_team(tt, team_full): continue
                    if _news_is_filler(tt): continue
                    if _v136_is_scam_news(tt, lk): continue
                    out.append({"headline":tt,"link":lk,"published":pd})
                    if len(out)>=limit: break
                if out: return out
            except: continue
        return out
    except: return []

def _google_news_rss(team_full, league, limit=8):
    try:
        import urllib.parse as _up, xml.etree.ElementTree as _ET
        _queries=[f"{team_full} {league} news", f"{team_full} news"]
        _all_out=[]
        for q in _queries:
            url="https://news.google.com/rss/search?q="+_up.quote(q)+"&hl=en-US&gl=US&ceid=US:en"
            r=requests.get(url,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
            root=_ET.fromstring(r.content or b"")
            out=[]
            for it in root.iter("item"):
                tt=it.findtext("title") or ""
                lk=it.findtext("link") or ""
                _pd=it.findtext("pubDate") or ""
                if " - " in tt: tt=tt.rsplit(" - ",1)[0]
                tt=tt.strip()
                if not tt or not lk: continue
                if _v136_is_scam_news(tt, lk): continue
                if _news_is_filler(tt): continue
                if not _news_matches_team(tt, team_full): continue
                if not _news_is_fresh(_pd, 7): continue
                out.append({"headline":tt,"link":lk,"published":_pd})
                if len(out)>=limit: break
            try:
                _pl=(team_full or "").lower()
                if "pitt" in _pl or "pittsburgh panthers" in _pl:
                    out=[a for a in out if not any(k in (a.get("headline","") or "").lower() for k in ("nfl","nfc","carolina panthers","chuba","hubbard","nfc south"))]
            except: pass
            _all_out.extend(out)
            if len(_all_out)>=limit: break
        _seen2=set(); _ded=[]
        for a in _all_out:
            _h=(a.get("headline","") or "").lower().strip()
            if _h and _h not in _seen2: _seen2.add(_h); _ded.append(a)
        return _ded[:limit]
    except: return []
_V215_OPP_NICKS = ["eagles","cowboys","giants","commanders","packers","bears","lions","vikings","falcons","panthers","saints","buccaneers","cardinals","rams","49ers","seahawks","chiefs","bills","dolphins","jets","patriots","ravens","bengals","browns","texans","colts","jaguars","titans","broncos","raiders","chargers","lakers","celtics","knicks","nets","warriors","clippers","suns","mavericks","nuggets","bucks","heat","sixers","hawks","bulls","cavaliers","pistons","raptors","wizards","hornets","magic","pacers","grizzlies","pelicans","thunder","jazz","kings","blazers","spurs","rockets","timberwolves","bruins","rangers","islanders","devils","flyers","hurricanes","lightning","maple leafs","senators","canadiens","red wings","blue jackets","wild","avalanche","stars","blues","predators","jets","flames","oilers","canucks","kraken","ducks","golden knights","kings","sharks","yankees","red sox","dodgers","giants","cubs","cardinals","mets","phillies","braves","astros","orioles","rays","blue jays","mariners","guardians","tigers","royals","twins","white sox","angels","athletics","marlins","nationals","pirates","reds","brewers","rockies","diamondbacks","padres","aggies","tigers","bulldogs","buckeyes","wolverines","crimson tide","volunteers","gators","seminoles","hurricanes","sooners","ducks","bruins","trojans","irish","badgers","hawkeyes"]
def _v215_is_opponent_news(headline, team_full):
    # V215: Headline faengt mit ANDEREM Team an ("Eagles Get Back Star WR vs. Steelers",
    # "Philadelphia Eagles Finally Get Good News Before Steelers Game") -> Gegner-News, raus!
    try:
        hl = (headline or "").lower()
        own = (team_full or "").lower()
        own_nicks = [w for w in re.split(r"[^a-z0-9]+", own) if len(w) >= 3]
        own_nick = own_nicks[-1] if own_nicks else ""
        for _opp in _V215_OPP_NICKS:
            if not _opp or _opp == own_nick: continue
            if _opp in own: continue
            _pos_opp = hl.find(_opp)
            if _pos_opp < 0 or _pos_opp > 25: continue
            # Eigenes Team kommt erst SPAETER (als "vs / before / against") oder gar nicht als Subjekt!
            _pos_own = -1
            for _tok in own_nicks:
                _p = hl.find(_tok)
                if _p >= 0:
                    _pos_own = _p if _pos_own < 0 else min(_pos_own, _p)
            if _pos_own < 0 or _pos_own > _pos_opp:
                return True
        return False
    except: return False

def _team_news_all_uncached(league, team_full, limit=8):
    # V137: 2. Filter-Layer! Auch wenn RSS/ESPN mal Scam liefert, fliegt er hier raus!
    arts=_espn_team_news(league,team_full,limit=limit)
    arts=[a for a in arts if not _v136_is_scam_news(a.get("headline",""), a.get("link","")) and not _news_is_filler(a.get("headline","")) and not _v215_is_opponent_news(a.get("headline",""), team_full)]
    # V175 Pitt-Fix: Carolina Panthers (NFL) raus! "Chuba Hubbard / NFC South" ist NICHT Pitt (NCAAF)!
    try:
        _low=(team_full or "").lower()
        if "pitt" in _low or "pittsburgh panthers" in _low:
            arts=[a for a in arts if not any(k in (a.get("headline","") or "").lower() for k in ("nfl","nfc","carolina panthers","chuba","hubbard","nfc south"))]
    except: pass
    # V175: Auffuellen - wenn ESPN <8 liefert (z.B. Pirates nur 1), Google dazu bis 8! Vorher nur <3!
    if len(arts)<limit:
        try:
            _g=_google_news_rss(team_full,league,limit=limit)
            _seen={(a.get("headline","") or "").lower().strip() for a in arts}
            for _a in _g:
                _h=(_a.get("headline","") or "").lower().strip()
                if _h and _h not in _seen and not _v136_is_scam_news(_a.get("headline",""), _a.get("link","")) and not _news_is_filler(_a.get("headline","")) and not _v215_is_opponent_news(_a.get("headline",""), team_full):
                    arts.append(_a); _seen.add(_h)
                if len(arts)>=limit: break
            # V175: Pitt-Fix auch fuer Google-Auffuellung!
            try:
                _low2=(team_full or "").lower()
                if "pitt" in _low2 or "pittsburgh panthers" in _low2:
                    arts=[a for a in arts if not any(k in (a.get("headline","") or "").lower() for k in ("nfl","nfc","carolina panthers","chuba","hubbard","nfc south"))]
            except: pass
            if arts and len(arts)>=3: return _dedupe_news(arts), "ESPN + Google"
            if arts: return _dedupe_news(arts), "ESPN"
        except: pass
        if arts: return _dedupe_news(arts), "ESPN"
    if arts: return _dedupe_news(arts), "ESPN"
    arts2=_google_news_rss(team_full,league,limit=limit)
    arts2=[a for a in arts2 if not _v136_is_scam_news(a.get("headline",""), a.get("link","")) and not _news_is_filler(a.get("headline","")) and not _v215_is_opponent_news(a.get("headline",""), team_full)]
    if arts2: return _dedupe_news(arts2), "Google News (ESPN leer)"
    return [], "ESPN"

def _team_news_all(league, team_full, limit=8):
    # V247 CACHE: Team-News 5 Min cachen! News braucht bis zu 4 Abrufe (ESPN + Google) -> Team-Fenster oeffnen sich sofort!
    import time as _time2
    _ck = ("news", league, team_full, limit)
    try:
        if _ck in _V247_NEWS_CACHE:
            _ts, _data = _V247_NEWS_CACHE[_ck]
            if (_time2.time() - _ts) < 300:
                return _data
    except: pass
    _res = _team_news_all_uncached(league, team_full, limit=limit)
    try: _V247_NEWS_CACHE[_ck] = (_time2.time(), _res)
    except: pass
    return _res
# ===== /V135 HELPERS =====

def espn_news(league, limit=8):
    # ESPN News API: nur Headline + Link! Kein Text, kein Spam!
    try:
        sp, lg = _ESPN_NEWS_SPORT.get(league, ("football","nfl"))
        import requests as _rq
        r=_rq.get(f"https://site.api.espn.com/apis/site/v2/sports/{sp}/{lg}/news", params={"limit": limit}, timeout=8)
        d=r.json() or {}
        out=[]
        for a in (d.get("articles") or [])[:limit]:
            hl=(a.get("headline") or "").strip()
            link=""
            try: link=(a.get("links",{}).get("web",{}).get("href") or a.get("links",{}).get("web",{}).get("href") or "")
            except: link=""
            if not link:
                try: link=(a.get("links") or [{}])[0].get("href","") if isinstance(a.get("links"), list) else ""
                except: link=""
            if hl: out.append({"headline": hl, "link": link, "published": a.get("published","")})
        return out
    except: return []
def _news_sent(uid):
    try: return set(load_settings().get(str(uid),{}).get("news_sent",[]) or [])
    except: return set()
def _news_mark_sent(uid, key):
    try:
        s=load_settings(); s.setdefault(str(uid),{}); s[str(uid)].setdefault("news_sent",[])
        if key not in s[str(uid)]["news_sent"]: s[str(uid)]["news_sent"].append(key)
        s[str(uid)]["news_sent"]=s[str(uid)]["news_sent"][-200:]
        save_settings(s)
    except: pass
def get_league_breaking(uid):
    try: return bool(load_settings().get(str(uid),{}).get("league_breaking", True))
    except: return True
def set_league_breaking(uid, val):
    try:
        s=load_settings(); s.setdefault(str(uid),{})["league_breaking"]=bool(val); save_settings(s)
    except: pass

async def news_league_menu_cmd(update, ctx):
    # V169: Liga-News Auswahl - nur Reingucken, kein Push!
    rows=[]
    _em={"NFL":"🏈","NBA":"🏀","NHL":"🏒","MLB":"⚾","NCAAF":"🎓"}
    for _lg in ["NFL","NBA","NHL","MLB","NCAAF"]:
        rows.append([InlineKeyboardButton(f"{_em.get(_lg,'📰')} Liga-News: {_lg}", callback_data=f"news_league:{_lg}")])
    rows.append([InlineKeyboardButton("⬅️ Zurück zu News", callback_data="news")])
    await _cb_edit(update, "📰 Liga-News\n\nTippe eine Liga an - nur zum Reingucken, kein Push!\nNur Headline + Link, Artikel auf Englisch.", InlineKeyboardMarkup(rows))
async def news_league_cmd(update, ctx, league):
    # V169: Liga-News on-demand, gleiche Filter wie Team-News!
    try:
        arts=espn_news(league, limit=8) or []
        arts=[a for a in arts if not _v136_is_scam_news(a.get("headline",""), a.get("link","")) and not _news_is_filler(a.get("headline",""))]
        _src="ESPN"
        if len(arts)<3:
            _keep=list(arts)
            arts=_google_news_rss(f"{league} league", league, limit=8) if False else []
            # Google Liga-Suche: eigener Query, ohne Team-Filter (Liga statt Team!)
            try:
                import urllib.parse as _up2, xml.etree.ElementTree as _ET2
                q=f"{league} news"
                url="https://news.google.com/rss/search?q="+_up2.quote(q)+"&hl=en-US&gl=US&ceid=US:en"
                r=requests.get(url,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
                root=_ET2.fromstring(r.content or b"")
                for it in root.iter("item"):
                    tt=it.findtext("title") or ""; lk=it.findtext("link") or ""; _pd=it.findtext("pubDate") or ""
                    if " - " in tt: tt=tt.rsplit(" - ",1)[0]
                    tt=tt.strip()
                    if not tt or not lk: continue
                    if _v136_is_scam_news(tt, lk) or _news_is_filler(tt) or not _news_is_fresh(_pd, 7): continue
                    arts.append({"headline":tt,"link":lk,"published":_pd})
                    if len(arts)>=12: break
            except: pass
            # V170: ESPN-Artikel behalten + Google dazu, ohne Dubletten!
            _seen2={(a.get("headline","") or "").lower().strip() for a in _keep}
            _merged=list(_keep)
            for _a in arts:
                _h=(_a.get("headline","") or "").lower().strip()
                if _h and _h not in _seen2: _merged.append(_a); _seen2.add(_h)
                if len(_merged)>=8: break
            arts=_merged
            _src="ESPN + Google" if _keep and len(arts)>len(_keep) else ("Google News (ESPN leer)" if arts else "ESPN")
        arts=_dedupe_news(arts)
        if not arts:
            await _cb_edit(update, f"📰 Liga-News - {league}\n\nGerade keine neuen {league}-News.\nCheck später nochmal!", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Liga-News", callback_data="news_league_menu")]])); return
        import html as _html2
        lines=[f"📰 Liga-News - {league}\n", f"Nur Headline + Link! Artikel auf Englisch! Quelle: {_src}!\n"]
        for i,a in enumerate(arts,1):
            _hl=_html2.escape(a['headline']); _link=(a.get("link") or "").replace('"','')
            lines.append(f"{i}. {_hl} - <a href=\"{_link}\">🔗 Lesen</a>" if _link else f"{i}. {_hl}")
        _kb=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Liga-News", callback_data="news_league_menu")]])
        _txt="\n".join(lines)
        try:
            q=update.callback_query
            if q and q.message:
                try: await q.message.edit_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True)
                except Exception: _m201 = await q.message.reply_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True); _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
            else: _m201 = await update.message.reply_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True); _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        except Exception:
            await _cb_edit(update, "\n".join([f"📰 Liga-News - {league}\n"]+[f"{i}. {a['headline']}" for i,a in enumerate(arts,1)]), _kb)
    except Exception as _e:
        await _cb_edit(update, f"📰 Liga-News - {league}\n\nGerade keine neuen News.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Liga-News", callback_data="news_league_menu")]]))

async def news_cmd(update, ctx):
    # Team-News: nur Favoriten! Nur Headline + Link!
    uid=update.effective_user.id if update.effective_user else 0
    favs=favs_for(uid)
    if not favs:
        await _cb_edit(update, "📰 News\n\nDu hast noch keine Favoriten. Füge erst ein Team hinzu!", small_kb()); return
    _lb_map = get_league_breaking_map(uid)
    _open = get_news_league_open(uid)
    _on_list = [lg for lg,_v in _lb_map.items() if _v]
    _on_txt = f" ({len(_on_list)} an: {', '.join(_on_list)})" if not _open else ""
    rows=[[InlineKeyboardButton(f"🌍 Liga-Breaking {'▾' if _open else '▸'}{_on_txt}", callback_data="news_league_expand")],
     [InlineKeyboardButton("📰 Liga-News ▸", callback_data="news_league_menu")]]
    if _open:
        _em={"NFL":"🏈","NBA":"🏀","NHL":"🏒","MLB":"⚾","NCAAF":"🎓"}
        for _lg in ["NFL","NBA","NHL","MLB","NCAAF"]:
            rows.append([InlineKeyboardButton(f"{'✅' if _lb_map.get(_lg) else '❌'} {_em[_lg]} {_lg}", callback_data=f"news_league_toggle:{_lg}")])
        rows.append([InlineKeyboardButton("✖️ Zuklappen", callback_data="news_league_expand")])
    for i,f in enumerate(favs): rows.append([InlineKeyboardButton(f"📰 {f}", callback_data=f"news_team:{i}")])
    rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    await _cb_edit(update, "📰 News - Nur deine Favoriten!\n\n🌍 Liga-Breaking oben = Push für große Sachen (International Series, Schedule, Super Bowl, Playoffs, Trade Deadline)!\n\nTippe ein Team an, dann kriegst du nur Headline + Link! Artikel sind auf Englisch, Quelle: ESPN!\n📰 Liga-News = Ligen zum Reingucken, kein Push!\nKein Push-Spam - News holst du dir, wenn du willst!", InlineKeyboardMarkup(rows))
async def news_team_cmd(update, ctx, idx):
    uid=update.effective_user.id if update.effective_user else 0
    favs=favs_for(uid)
    if idx<0 or idx>=len(favs): await news_cmd(update, ctx); return
    f=favs[idx]; lg=f.split(" (")[-1].replace(")","").strip() if " (" in f else "NFL"
    _full = f.split(" (")[0].strip()
    arts, _src = _team_news_all(lg, _full, limit=8)
    # V137: 3. Layer - Scam auch beim Anzeigen raus, falls Liste schon alt/cached war!
    arts=[a for a in arts if not _v136_is_scam_news(a.get("headline",""), a.get("link",""))]
    arts=_dedupe_news(arts)
    if not arts:
        await _cb_edit(update, f"📰 News - {f}\n\nGerade keine neuen {_full}-News.\nCheck später nochmal!", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu News", callback_data="news")]])); return
    import html as _html
    lines=[f"📰 News - {f}\n", f"Nur Headline + Link! Artikel auf Englisch! Quelle: {_src}!\n"]
    for i,a in enumerate(arts,1):
        _hl=_html.escape(a['headline'])
        _link=(a.get("link") or "").replace('"','')
        if _link: lines.append(f"{i}. {_hl} - <a href=\"{_link}\">🔗 Lesen</a>")
        else: lines.append(f"{i}. {_hl}")
    _kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu News", callback_data="news")]])
    _txt = "\n".join(lines)
    try:
        q=update.callback_query
        if q and q.message:
            try: await q.message.edit_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True)
            except Exception: _m201 = await q.message.reply_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True); _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
        else: _m201 = await update.message.reply_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True); _chain_add(update.effective_user.id if update.effective_user else 0, _m201.message_id)
    except Exception:
        await _cb_edit(update, "\n".join([f"📰 News - {f}\n"]+[f"{i}. {a['headline']}" for i,a in enumerate(arts,1)]), _kb)

async def news_breaking_job(context):
    # V134: Alle 10 Min: Liga-Breaking + Spiel-Breaking checken! Kein Spam: nur 1x pro Headline!
    try:
        for uid_str in list(load_settings().keys()):
            try: uid=int(uid_str)
            except: continue
            _lbmap = get_league_breaking_map(uid)
            sent=_news_sent(uid)
            # Liga-Breaking: nur große Themen, pro Liga eigene Begriffe + pro Liga Toggle!
            for lg in ["NFL","NCAAF","NBA","NHL","MLB"]:
                if not _lbmap.get(lg, True): continue
                _keys = _LIGA_BREAKING_PER_LEAGUE.get(lg, _LIGA_BREAKING_KEYS)
                for a in espn_news(lg, limit=5):
                    hl=(a.get("headline") or "").lower()
                    if not any(k in hl for k in _keys): continue
                    key=f"liga:{lg}:{a['headline']}"
                    if key in sent: continue
                    _news_mark_sent(uid, key)
                    # V167: Bei Spielplan-Aenderung Hinweis dazu - Next Games zieht nach, sobald ESPN es hat (ESPN ist oft Stunden hinter Schefter her)!
                    _is_sched = any(k in hl for k in _SCHEDULE_CHANGE_KEYS)
                    _hint = "\n\n📅 Hinweis: Sobald ESPN es bestätigt, steht die neue Zeit auch in Next Games!" if _is_sched else ""
                    try: await context.bot.send_message(chat_id=uid, text=f"🌍 LIGA-BREAKING: {lg}\n\n{a['headline']}\n🔗 {a.get('link','')}{_hint}")
                    except: pass
            # Spiel-Breaking: nur wenn Breaking AN + Headline hat OUT/Ejection + Team ist Favorit!
            favs=favs_for(uid)
            for f in favs:
                cfg=get_live_team(uid, f)
                if not cfg.get("breaking"): continue
                lg=f.split(" (")[-1].replace(")","").strip() if " (" in f else "NFL"
                short=_short_team(f)
                for a in espn_news(lg, limit=8):
                    hl_low=(a.get("headline") or "").lower()
                    if short.lower() not in hl_low: continue
                    if not any(k in hl_low for k in _BREAKING_KEYS): continue
                    key=f"spiel:{f}:{a['headline']}"
                    if key in sent: continue
                    _news_mark_sent(uid, key)
                    try: await context.bot.send_message(chat_id=uid, text=f"🚨 SPIEL-BREAKING: {f}\n\n{a['headline']}\n🔗 {a.get('link','')}")
                    except: pass
    except: pass

async def notif_cmd(update, ctx):
    target = update.message or update.callback_query.message
    uid = update.effective_user.id if update.effective_user else 0
    rm = get_reminder_minutes(uid); master = get_live_master(uid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⏰ Reminder - Aktuell: {fmt_reminder(rm)}", callback_data="settings_reminder")],
        [InlineKeyboardButton(f"🔴 Live-Scores: {'✅ AN' if master else '❌ AUS'}", callback_data="notif_master")],
        [InlineKeyboardButton("🔴 Live-Scores pro Team einstellen", callback_data="notif_teams")],
        [InlineKeyboardButton("⬅️ Zurück zu Einstellungen", callback_data="settings")],
    ])
    await _cb_edit(update, "🔔 Benachrichtigungen\n\n⏰ Reminder: vor dem Spiel.\n🔴 Live-Scores: Favoriten + Meine Live-Spiele! Pro Team einzeln: Score / Start + Quarter / Endstand.\n\nAlles aus = kein Spam - du entscheidest!", kb)
async def notif_teams_cmd(update, ctx):
    target = update.message or update.callback_query.message
    uid = update.effective_user.id if update.effective_user else 0
    favs = favs_for(uid)
    if not favs:
        await target.reply_text("Du hast noch keine Favoriten. Füge erst ein Team hinzu!", reply_markup=small_kb()); return
    rows = []
    for i, f in enumerate(favs):
        cfg = get_live_team(uid, f)
        on = any(cfg.values())
        rows.append([InlineKeyboardButton(f"{'✅' if on else '❌'} {f}", callback_data=f"notif_team:{i}")])
    # V112: Meine Live-Spiele - alle einzelnen Spiele, die du bei Nächste Spiele angemacht hast!
    rows.append([InlineKeyboardButton("🔴 Meine Live-Spiele", callback_data="my_live_games")])
    rows.append([InlineKeyboardButton("⬅️ Zurück zu Benachrichtigungen", callback_data="notif")])
    await _cb_edit(update, "🔴 Live-Scores pro Team\n\nTippe ein Team an, dann kannst du pro Team einstellen: Score / Start + Quarter / Endstand!\n\n🔴 Meine Live-Spiele = deine einzelnen Spiele (z.B. München), die du bei Nächste Spiele angemacht hast!", InlineKeyboardMarkup(rows))
async def my_live_games_cmd(update, ctx):
    uid = update.effective_user.id if update.effective_user else 0
    try: oo = load_settings().get(str(uid), {}).get("oneoff_live", {}) or {}
    except: oo = {}
    # Nur Spiele, wo was an ist!
    active = []
    for eid, d in oo.items():
        if not d: continue
        if any([d.get("score"), d.get("period"), d.get("final"), d.get("crunch"), d.get("start"), d.get("reminder")]): active.append((str(eid), d.get("lg",""), d.get("name","") or f"Spiel {eid}", d))
    if not active:
        await _cb_edit(update, "🔴 Meine Live-Spiele\n\nNoch keine einzelnen Spiele angemacht.\nGeh zu Next Games → Heute/Morgen → Zahl vom Spiel schreiben, dann tauchen sie hier auf!", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Teams", callback_data="notif_teams")]])); return
    lines = ["🔴 Meine Live-Spiele\n"]
    _shown209 = []; _to_delete209 = []; _any_data209 = False; _num209 = 0
    for eid, lg, nm, d in active:
        _on = []
        if d.get("score"): _on.append("Score")
        if d.get("period"): _on.append(period_toggle_label(lg))
        if d.get("final"): _on.append("Endstand")
        if d.get("crunch"): _on.append("Crunch-Time")
        if d.get("breaking"): _on.append("Breaking")
        # V209: Frischen Stand holen statt eingefrorenem Foto! (Patriots-Spiel zeigte 6 Tage lang "LIVE"!)
        _fresh209 = None
        try:
            from datetime import date as _date209
            _today209 = _date209.today()
            for _off209 in (0, 1, -1, 2, -2, -3, -4, -5, -6, -7, -8):
                _dd209 = _today209 + timedelta(days=_off209)
                _evs209 = espn_scoreboard(lg, dates=_dd209.strftime("%Y%m%d"))
                if _evs209: _any_data209 = True
                for _ev209 in _evs209:
                    if str(_ev209.get("id","")) == str(eid):
                        _fresh209 = _ev209; break
                if _fresh209 is not None: break
        except: _fresh209 = None
        _skip209 = False; _nm_clean = ""
        if _fresh209 is not None:
            _state209 = _fresh209.get("status",{}).get("type",{}).get("state","")
            if _state209 == "post":
                try:
                    _, _dt209 = fmt_dt(_fresh209.get("date",""))
                    if _dt209 and (datetime.now(BERLIN) - _dt209).total_seconds() > 5*3600:
                        # V213: Fertig + Anpfiff >5h her -> Altlast! Raus aus der Liste! (Vorher: 30h - viel zu lang!)
                        _to_delete209.append(eid); _skip209 = True
                except: pass
            if not _skip209:
                _nm_clean = game_line(_fresh209, lg)
        else:
            if _any_data209:
                # Spiel in den letzten 8 Tagen nirgends gefunden -> uralt/ungueltig! Raus!
                _to_delete209.append(eid); _skip209 = True
            else:
                # API-Ausfall? Nichts loeschen, alten Namen zeigen!
                _nm_clean = nm or ""
        if _skip209: continue
        # V117: Kompakt! Stadion-Name kürzen: "FC Bayern Munich Stadium, Munich" -> "München", Zeilenumbrüche weg!
        _nm_clean = (_nm_clean or "").replace("\n"," ").replace("FC Bayern Munich Stadium, Munich","München").replace("FC Bayern Munich Stadium","München")
        # Kurz-Namen: "New England Patriots" -> "Patriots" in der Liste (nur Anzeige, nicht speichern!)
        for _full,_short in [("New England Patriots","Patriots"),("Detroit Lions","Lions")]:
            _nm_clean = _nm_clean.replace(_full,_short)
        _num209 += 1
        _shown209.append((eid, lg))
        lines.append(f"{_num209}. {_nm_clean} • {' + '.join(_on) if _on else 'an'}")
    # V209: Altlasten wirklich loeschen!
    if _to_delete209:
        try:
            _s209 = load_settings(); _u209 = str(uid)
            for _eid209 in _to_delete209:
                try: _s209.get(_u209, {}).get("oneoff_live", {}).pop(str(_eid209), None)
                except: pass
            save_settings(_s209)
        except: pass
    try: ctx.user_data["my_live_list"] = _shown209; ctx.user_data["await_live_stats_pick"] = False  # V246: Live-Flag aus! Diese Liste gewinnt jetzt!
    except: pass
    if not _shown209:
        await _cb_edit(update, "🔴 Meine Live-Spiele\n\nKeine einzelnen Spiele mehr - die fertigen sind automatisch rausgeflogen! 🧹\nGeh zu Next Games → Heute/Morgen → Zahl vom Spiel schreiben, dann tauchen sie hier auf!", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Teams", callback_data="notif_teams")]])); return
    lines.append("\n✏️ Tippe die Zahl ein, bei dem Spiel wo du was ändern willst!")
    lines.append("Dann ploppt genau das Fenster auf und du kannst nachträglich was an / aus machen!")
    await _cb_edit(update, "\n".join(lines), InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Teams", callback_data="notif_teams")]]))

async def notif_team_cmd(update, ctx, idx):
    target = update.message or update.callback_query.message
    uid = update.effective_user.id if update.effective_user else 0
    favs = favs_for(uid)
    if idx < 0 or idx >= len(favs):
        await notif_teams_cmd(update, ctx); return
    f = favs[idx]; cfg = get_live_team(uid, f)
    _lg_team = f.split(" (")[-1].replace(")", "").strip() if " (" in f else ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅' if cfg['score'] else '❌'} Jeder Score (TD / FG / Tor / Run)", callback_data=f"notif_toggle:{idx}:score")],
        [InlineKeyboardButton(f"{'✅' if cfg['period'] else '❌'} {period_toggle_label(_lg_team if _lg_team in ('NFL','NCAAF','NBA','NHL','MLB') else 'NFL')}", callback_data=f"notif_toggle:{idx}:period")],
        [InlineKeyboardButton(f"{'✅' if cfg['final'] else '❌'} Endstand", callback_data=f"notif_toggle:{idx}:final")],
        [InlineKeyboardButton(f"{'✅' if cfg.get('crunch') else '❌'} Crunch-Time (8 Min, knapp!)", callback_data=f"notif_toggle:{idx}:crunch")],
        [InlineKeyboardButton(f"{'✅' if cfg.get('breaking') else '❌'} 🚨 Spiel-Breaking (Verletzung / Ejection)", callback_data=f"notif_toggle:{idx}:breaking")],
        [InlineKeyboardButton("⬅️ Zurück zu Teams", callback_data="notif_teams")],
    ])
    _hint = "\nHinweis: NBA = jeder Korb = viele Nachrichten! Da lieber nur Viertel-Ende + Beginn + Endstand!" if _lg_team == "NBA" else ""
    await _cb_edit(update, f"🔴 Live-Scores - {f}\n\nTippe an / aus. Nur was du anmachst, schicke ich dir!{_hint}", kb)
def _score_only(ev):
    try:
        teams, _ = event_teams(ev)
        if len(teams) >= 2:
            home_t = next((x for x in teams if (x[1] or '').lower()=='home'), None)
            away_t = next((x for x in teams if (x[1] or '').lower()=='away'), None)
            if home_t is None or away_t is None: away_t, home_t = teams[0], teams[1]
            return f"{away_t[0]} {away_t[2] or ''}".strip() + ' @ ' + f"{home_t[0]} {home_t[2] or ''}".strip()
    except: pass
    return ''
def _clock_secs(ev):
    try:
        st = ev.get('status', {}) or {}
        c = (st.get('displayClock') or '').strip()
        if not c or ':' not in c: return None
        mm, ss = c.split(':'); return int(mm)*60 + int(ss)
    except: return None
_LIVE_SEEN = {}
def _live_scores_of(ev):
    try:
        comps = ev.get("competitions", [{}])[0]
        out = {}
        for c in comps.get("competitors", []):
            nm = (c.get("team", {}) or {}).get("displayName", "")
            try: out[nm] = int(c.get("score", 0) or 0)
            except: out[nm] = 0
        return out
    except: return {}
async def _scorer_update_job(context):
    # V101-FIX: Scorer steht NICHT im Scoreboard, nur in der Summary! Deswegen Summary holen!
    # V225: ROLLENDER SCORER! TD-Nachricht kommt SOFORT (ohne Warten!), Scorer rollt per Edit rein (30/60/120-Staffel)! XP rollt vorher schon per Edit rein (V222)!
    try:
        d = context.job.data or {}
        uid = int(d.get("uid", 0)); eid = str(d.get("eid", "")); lg = d.get("lg", ""); mid = int(d.get("mid", 0)); orig = d.get("orig", "")
        if not uid or not eid or not mid or not orig: return
        # V228: XP-Edit OHNE Scorer! Wenn der Scorer nicht gefunden wird, bleibt die Nachricht sonst ewig beim TD-Stand (13 statt 14)!
        async def _xp_only_edit228():
            try:
                import re as _re228
                if not ("TOUCHDOWN" in orig or "Touchdown" in orig): return
                _m228 = _re228.search(r"(\d+)\s:\s(\d+)", orig)
                if not _m228: return
                _o_a228, _o_h228 = int(_m228.group(1)), int(_m228.group(2))
                _cur228 = {}
                for _ev228 in _scoreboard_dates(lg):
                    if str(_ev228.get("id", "")) == eid:
                        _cur228 = _live_scores_of(_ev228); break
                if not _cur228: return
                _away_nm228 = (d.get("away", "") or ""); _home_nm228 = (d.get("home", "") or "")
                _c_a228 = _c_h228 = None
                for _k228, _v228 in _cur228.items():
                    if _away_nm228 and (_away_nm228.lower() in _k228.lower() or _k228.lower() in _away_nm228.lower()): _c_a228 = _v228
                    if _home_nm228 and (_home_nm228.lower() in _k228.lower() or _k228.lower() in _home_nm228.lower()): _c_h228 = _v228
                if _c_a228 is None or _c_h228 is None: return
                _da228, _dh228 = _c_a228 - _o_a228, _c_h228 - _o_h228
                # Genau EINE Seite +1/+2, andere 0 -> XP/2PC ist drin! Beide Seiten gestiegen = danach kam noch was -> nix raten!
                if _da228 in (1, 2) and _dh228 == 0: _diff228 = _da228
                elif _dh228 in (1, 2) and _da228 == 0: _diff228 = _dh228
                else: return
                _new_txt228 = _re228.sub(r"\d+\s:\s\d+", f"{_c_a228} : {_c_h228}", orig, count=1)
                if _diff228 == 1:
                    _new_txt228 = _new_txt228.replace("TOUCHDOWN!", "TOUCHDOWN + EXTRA POINT!")
                    _new_txt228 = _new_txt228.replace("Touchdown...", "Touchdown + Extra Point...")
                else:
                    _new_txt228 = _new_txt228.replace("TOUCHDOWN!", "TOUCHDOWN + 2-POINT!")
                    _new_txt228 = _new_txt228.replace("Touchdown...", "Touchdown + 2-Point...")
                if _new_txt228 != orig:
                    try: await context.bot.edit_message_text(chat_id=uid, message_id=mid, text=_new_txt228)
                    except: pass
            except: pass
        # Summary-Details holen (da steht der Scorer wirklich drin!)
        _dets = []
        try: _dets = espn_summary_details({"id": eid}, lg) or []
        except: _dets = []
        _sc = ""
        # Auch Scoreboard als Fallback probieren
        if not _dets:
            try:
                for _ev2 in _scoreboard_dates(lg):
                    if str(_ev2.get("id", "")) == eid:
                        _sc = last_scorer(_ev2, lg) or ""
                        break
            except: pass
            if _sc.strip() and _sc.strip() not in orig:
                try: await context.bot.edit_message_text(chat_id=uid, message_id=mid, text=orig + "\n" + _sc.strip())
                except: pass
            else:
                # V228: Auch ohne Scorer den XP reinholen! (TCU-Fall: 13 statt 14!)
                await _xp_only_edit228()
                # V105: Auch hier Retry, wenn Scoreboard auch keinen Scorer hatte!
                try:
                    _try2 = int((context.job.data or {}).get("try", 1) or 1)
                    if _try2 < 3 and context.job_queue:
                        _nd2 = dict(context.job.data or {}); _nd2["try"] = _try2 + 1
                        # V225: Retry-Staffel! 2. Versuch nach 60, 3. nach 120 Sek (vorher immer 120)!
                        context.job_queue.run_once(_scorer_update_job, 60 if _try2 == 1 else 120, data=_nd2, name=f"scorer_retry2_{eid}_{mid}_{_try2+1}")
                except: pass
            return
        # Letzten Scoring-Play aus Summary-Details suchen (letzter zuerst)
        for _d in reversed(_dets):
            try:
                _raw_type = _d.get("type", "") if isinstance(_d, dict) else ""
                if isinstance(_raw_type, str):
                    _dtype = _raw_type
                elif isinstance(_raw_type, dict):
                    _dtype = _raw_type.get("text", "") or _raw_type.get("shortText", "") or _raw_type.get("abbreviation", "") or ""
                else:
                    _dtype = ""
                if not _dtype:
                    _dtype = _d.get("playType", "") or _d.get("text", "") or ""
                if not any(k.lower() in _dtype.lower() for k in ["Goal", "Touchdown", "Field Goal", "Home Run", "Three Point", "Two Point", "Dunk", "Layup", "Single", "Double", "Triple", "Extra Point", "Safety", "Return Touchdown", "Return TD", "Pick Six"]): continue  # V226: Safety + Return-TDs sind auch Scoring-Plays!
                # V104: Extra Point / PAT ist kein TD - ueberspringen, wir wollen den TD selbst!
                if "extra point" in _dtype.lower() and "touchdown" not in _dtype.lower(): continue
                _scorer = ""
                for _p in _d.get("participants", []) or _d.get("athletesInvolved", []) or []:
                    if isinstance(_p, str):
                        _scorer = _p; break
                    _ath = _p.get("athlete", {}) if isinstance(_p, dict) else {}
                    if isinstance(_ath, str):
                        _scorer = _ath; break
                    if isinstance(_ath, dict) and _ath.get("displayName"): _scorer = _ath.get("displayName"); break
                    if isinstance(_p, dict) and _p.get("displayName"): _scorer = _p.get("displayName"); break
                if not _scorer:
                    _txt = _d.get("text", "") or _dtype
                    _scorer = _txt
                _team = (_d.get("team", {}) or {}).get("shortDisplayName", "") or (_d.get("team", {}) or {}).get("displayName", "")
                _clock = (_d.get("clock", {}) or {}).get("displayValue", "") or ""
                _per = _d.get("period", "")
                _emo = "🏒" if lg=="NHL" else "🏈" if lg in ("NFL","NCAAF") else "⚾" if lg=="MLB" else "🏀"
                _label = _v226_scorer_label(_dtype, lg)  # V226: Echte Score-Art (Pick Six, Safety, Field Goal...) statt "Letzter Touchdown"!
                _extra = f" \u2022 {_clock} P{_per}" if lg=="NHL" and _clock else ""
                if _scorer:
                    _sc = f"   {_emo} {_label}: {_scorer} ({_team}){_extra}" if _team else f"   {_emo} {_label}: {_scorer}{_extra}"
                    break
            except: continue
        if not _sc.strip():
            # V228: Auch ohne Scorer den XP reinholen! Nachricht darf nicht ewig beim TD-Stand haengen!
            await _xp_only_edit228()
            # V105: Retry! Wenn nach 2 Min noch kein Scorer da ist, nochmal in 2 Min probieren (max 3x)!
            try:
                _try = int((context.job.data or {}).get("try", 1) or 1)
                if _try < 3 and context.job_queue:
                    _nd = dict(context.job.data or {}); _nd["try"] = _try + 1
                    # V225: Retry-Staffel! 2. Versuch nach 60, 3. nach 120 Sek (vorher immer 120)!
                    context.job_queue.run_once(_scorer_update_job, 60 if _try == 1 else 120, data=_nd, name=f"scorer_retry_{eid}_{mid}_{_try+1}")
            except: pass
            return
        if _sc.strip() in orig: return
        # V102: Wenn bis zum Scorer-Edit schon der XP / 2PC drin ist (+1 / +2), dann TD-Nachricht auf Endstand bringen!
        # V222: One-Liner-Format! orig ist jetzt "🔴 Touchdown... Tigers • Tigers 33 : 24 Midshipmen • 12:38 Q4"
        # Alter Parser suchte "Team X @ Team Y" (V102-Format) -> fand im neuen Format NIX -> XP-Merge nie passiert! Jetzt: "AWAY <n> : <m> HOME"!
        # V222: Merge NUR bei TD-Nachrichten! Sonst wuerde ein FG-Text den Score eines spaeteren Safety uebernehmen!
        _final_txt = orig + "\n" + _sc.strip()
        try:
            # Aktuellen Score holen (Scoreboard)
            _cur_scores = {}
            try:
                for _ev3 in _scoreboard_dates(lg):
                    if str(_ev3.get("id", "")) == eid:
                        _cur_scores = _live_scores_of(_ev3); break
            except: _cur_scores = {}
            import re as _re2
            # V222: Score aus One-Liner parsen: "33 : 24" (mit Leerzeichen um den Doppelpunkt - Uhr "12:38" hat keine und matcht nicht!)
            _m = _re2.search(r"(\d+)\s:\s(\d+)", orig) if ("TOUCHDOWN" in orig or "Touchdown" in orig) else None
            if _m and _cur_scores:
                _away_sc, _home_sc = int(_m.group(1)), int(_m.group(2))
                # Finde welches Team gescored hat (aus _sc Team in Klammern)
                _tm = _re2.search(r"\((.+?)\)", _sc)
                _sc_team = _tm.group(1) if _tm else ""
                # Away/Home-Namen aus Job-Data (V222: Poller uebergibt sie!)
                _away_nm = (context.job.data or {}).get("away", "") or ""
                _home_nm = (context.job.data or {}).get("home", "") or ""
                _cur = None; _is_away = False
                for _k, _v in _cur_scores.items():
                    if _sc_team and (_sc_team.lower() in _k.lower() or _k.lower() in _sc_team.lower()):
                        _cur = _v
                        # Ist Scorer-Team Away oder Home?
                        if _away_nm and (_sc_team.lower() in _away_nm.lower() or _away_nm.lower() in _sc_team.lower()): _is_away = True
                        elif _home_nm and (_sc_team.lower() in _home_nm.lower() or _home_nm.lower() in _sc_team.lower()): _is_away = False
                        else: _is_away = (_away_nm.lower() in _k.lower() or _k.lower() in _away_nm.lower()) if _away_nm else False
                        break
                if _cur is not None:
                    _orig_sc = _away_sc if _is_away else _home_sc
                    _diff = _cur - _orig_sc
                    if _diff == 1:
                        # XP ist drin! Score in orig ersetzen + Label auf TOUCHDOWN + EXTRA POINT!
                        _new_away = _away_sc + 1 if _is_away else _away_sc
                        _new_home = _home_sc + 1 if not _is_away else _home_sc
                        _final_txt = _re2.sub(r"\d+\s:\s\d+", f"{_new_away} : {_new_home}", orig, count=1)
                        _final_txt = _final_txt.replace("TOUCHDOWN!", "TOUCHDOWN + EXTRA POINT!")
                        _final_txt = _final_txt.replace("Touchdown...", "Touchdown + Extra Point...")
                        _final_txt = _final_txt + "\n" + _sc.strip()
                    elif _diff == 2:
                        _new_away = _away_sc + 2 if _is_away else _away_sc
                        _new_home = _home_sc + 2 if not _is_away else _home_sc
                        _final_txt = _re2.sub(r"\d+\s:\s\d+", f"{_new_away} : {_new_home}", orig, count=1)
                        _final_txt = _final_txt.replace("TOUCHDOWN!", "TOUCHDOWN + 2-POINT!")
                        _final_txt = _final_txt.replace("Touchdown...", "Touchdown + 2-Point...")
                        _final_txt = _final_txt + "\n" + _sc.strip()
        except: _final_txt = orig + "\n" + _sc.strip()
        try: await context.bot.edit_message_text(chat_id=uid, message_id=mid, text=_final_txt)
        except: pass
    except Exception as e:
        try: logger.warning(f"scorer_update: {e}")
        except: pass
async def live_score_job(context):
    try:
        favs_all = load_favs()
        # V109: One-Off Live-Spiele (Nicht-Favoriten) als Pseudo-Favs dazu!
        try:
            _sett = load_settings() or {}
            for _uid2, _sd in _sett.items():
                _oo2 = (_sd or {}).get("oneoff_live", {}) or {}
                for _eid2, _od in _oo2.items():
                    if not _od or not any([_od.get("score"), _od.get("period"), _od.get("final"), _od.get("crunch"), _od.get("start")]): continue
                    _lg2 = _od.get("lg",""); _nm2 = _od.get("name","") or f"Spiel {_eid2}"
                    if _lg2 not in LEAGUES: continue
                    # Pseudo-Fav: ONEOFF:<eid> ( <LG> ) - im Loop erkennen wir das!
                    _pseudo = f"ONEOFF:{_eid2} ({_lg2})"
                    favs_all.setdefault(str(_uid2), [])
                    if _pseudo not in favs_all[str(_uid2)]:
                        favs_all[str(_uid2)].append(_pseudo)
        except: pass
        if not favs_all: return
        for uid_str, favs in favs_all.items():
            if not favs: continue
            try: uid = int(uid_str)
            except: continue
            if not get_live_master(uid): continue
            for fav in favs:
                # V109: One-Off oder Favorit?
                _is_oneoff = fav.startswith("ONEOFF:")
                if _is_oneoff:
                    _eid_one = fav.split(":")[1].split(" ")[0]
                    lg = fav.split(" (")[-1].replace(")", "").strip() if " (" in fav else None
                    if lg not in LEAGUES: continue
                    cfg = get_oneoff_live(uid, _eid_one)
                    if not any([cfg.get("score"), cfg.get("period"), cfg.get("final"), cfg.get("crunch"), cfg.get("start")]): continue
                    name = ""  # One-Off matcht per EID, nicht per Name!
                else:
                    cfg = get_live_team(uid, fav)
                    if not any(cfg.values()): continue
                    name = fav.split(" (")[0].strip(); lg = fav.split(" (")[-1].replace(")", "").strip() if " (" in fav else None
                    if lg not in LEAGUES: continue
                    _eid_one = None
                for ev in _scoreboard_dates(lg):
                    teams, _ = event_teams(ev)
                    team_text = " ".join([x[0] for x in teams]).lower()
                    if _is_oneoff:
                        if str(ev.get("id","")) != str(_eid_one): continue
                    else:
                        if name.lower() not in team_text: continue
                    eid = str(ev.get("id", ""))
                    _fav_disp = game_line(ev, lg) if _is_oneoff else fav
                    state = (ev.get("status", {}) or {}).get("type", {}).get("state", "")
                    scores = _live_scores_of(ev); period = (ev.get("status", {}) or {}).get("period")
                    # V118: PRE-Spiele merken, wenn Spielstart an! Sonst sehen wir den Kickoff-Übergang nie!
                    if state not in ("in", "post"):
                        if cfg.get("period") or cfg.get("start"):
                            _k2 = (uid, str(ev.get("id","")), fav)
                            _prev2 = _LIVE_SEEN.get(_k2)
                            if _prev2 is None or _prev2.get("state") != "pre":
                                _LIVE_SEEN[_k2] = {"scores": scores, "period": period, "state": "pre", "last_td": {}, "awaiting_resume": None, "halftime_sent": False, "crunch_sent": False, "start_sent": False, "ints_sent": []}
                        continue
                    key = (uid, eid, fav)
                    prev = _LIVE_SEEN.get(key)
                    if prev is None:
                        # V211: Spiel schon fertig beim ersten Sehen? -> Als 'pre' merken, damit der Endstand trotzdem feuert! Vorher: Neustart + fertiges Spiel = Endstand still verloren!
                        _LIVE_SEEN[key] = {"scores": scores, "period": period, "state": ("pre" if state == "post" else state), "last_td": {}, "awaiting_resume": None, "halftime_sent": False, "crunch_sent": False, "start_sent": False, "ints_sent": []}
                        if state != "post": continue
                    # V119: SPIELSTART gehört zu PERIOD! Wer Quarter-Ende + Beginn will, will auch Spielstart!
                    # (cfg.start noch drin für alle, die V118 schon an hatten - sonst geht nix verloren!)
                    if (cfg.get("period") or cfg.get("start")) and state == "in" and prev.get("state") == "pre" and not prev.get("start_sent"):
                        try: await _live_send_dnd(context, uid, eid, lg, _fav_disp, f"🚨 Es geht los! {game_start_label(lg)} • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg) if _score_line_short(ev, lg) else game_line(ev, lg)} • Viel Spaß! 🔥")
                        except: pass
                        prev["start_sent"] = True
                    # Score geaendert?
                    if cfg.get("score") and state == "in" and scores != prev["scores"]:
                        diffs = {k: scores.get(k, 0) - prev["scores"].get(k, 0) for k in scores}
                        # V96: TOR ABERKANNT! Score ist KLEINER geworden (z.B. NHL-Tor zurueckgenommen, NFL-TD overturned)!
                        _neg = {k: v for k, v in diffs.items() if v < 0}
                        if _neg:
                            _team_neg = min(_neg, key=lambda k: _neg[k]); _d_neg = _neg[_team_neg]
                            if lg == "NHL": _label_neg = "TOR ABERKANNT"
                            elif lg in ("NFL", "NCAAF"): _label_neg = "TOUCHDOWN ABERKANNT" if _d_neg <= -6 else "FIELD GOAL ABERKANNT" if _d_neg == -3 else "SCORE ABERKANNT"
                            elif lg == "MLB": _label_neg = "RUN ABERKANNT"
                            elif lg == "NBA": _label_neg = "KORB ABERKANNT"
                            else: _label_neg = "PUNKT ABERKANNT"
                            try: await _live_send_dnd(context, uid, eid, lg, _fav_disp, f"❌ {_label_neg}! {_team_neg} • {LEAGUES[lg]['emoji']} {game_line(ev, lg)} • Wieder {scores.get(_team_neg, 0)} - zurückgenommen!")
                            except: pass
                        scorer = max(diffs, key=lambda k: diffs[k]) if diffs else ""
                        d = diffs.get(scorer, 0)
                        if d > 0:
                            # V98: XP / 2PC! TD+XP in einem Rutsch = 7, TD+2PC = 8. XP allein kurz nach TD = 1, 2PC allein = 2!
                            import time as _time_mod
                            _now_ts = _time_mod.time()
                            _last_td = (prev.get("last_td") or {}).get(scorer, 0) if isinstance(prev.get("last_td"), dict) else 0
                            _recent_td = (_now_ts - _last_td) < 180 if _last_td else False
                            if lg in ("NFL", "NCAAF"):
                                if d == 7: label = "TOUCHDOWN + EXTRA POINT"
                                elif d == 8: label = "TOUCHDOWN + 2-POINT"
                                elif d == 6: label = "TOUCHDOWN"
                                elif d == 3: label = "FIELD GOAL"
                                elif d == 2 and _recent_td: label = "2-POINT CONVERSION"
                                elif d == 1 and _recent_td: label = "EXTRA POINT"
                                elif d == 2: label = "SAFETY"
                                elif d == 1: label = "EXTRA POINT"
                                else: label = "SCORE"
                                if d >= 6:
                                    try:
                                        _ltd = dict(prev.get("last_td") or {}); _ltd[scorer] = _now_ts; prev["last_td"] = _ltd
                                    except: pass
                            elif lg == "NHL": label = "TOR"
                            elif lg == "MLB": label = "RUN"
                            else: label = "KORB"
                            # V222: XP / 2PC kurz nach TD = KEIN eigener Push! TD-Nachricht aendert sich per Edit (Scorer-Job)!
                            # Vorher: TD-Push + extra XP-Push untereinander = Stapel! Jetzt: TD-Nachricht wird zu "TD + XP" editiert!
                            _skip_xp222 = (lg in ("NFL", "NCAAF") and label in ("EXTRA POINT", "2-POINT CONVERSION") and _recent_td)
                            if _skip_xp222:
                                try:
                                    _last_ids222 = _LIVE_MSG_IDS.get((uid, str(eid)), [])
                                    _last_txt222 = _LIVE_LAST_TXT.get((uid, str(eid)), "")
                                    if _last_ids222 and _last_txt222 and context.job_queue:
                                        _et222 = event_teams(ev)
                                        _teams222 = _et222[0] if _et222 else []
                                        _away222 = next((x[0] for x in _teams222 if (x[1] or "").lower()=="away"), "")
                                        _home222 = next((x[0] for x in _teams222 if (x[1] or "").lower()=="home"), "")
                                        context.job_queue.run_once(_scorer_update_job, 30, data={"uid": uid, "eid": eid, "lg": lg, "mid": int(_last_ids222[-1]), "orig": _last_txt222, "away": _away222, "home": _home222}, name=f"scorer_xp_{eid}_{_last_ids222[-1]}")
                                except: pass
                            # V89-FIX2: Scorer dazu, wenn ESPN ihn schon hat! Sonst Nachricht trotzdem ohne Scorer schicken!
                            _scorer_line = ""
                            try:
                                _ls = last_scorer(ev, lg) or ""
                                if _ls.strip(): _scorer_line = "\n" + _ls.strip()
                            except: _scorer_line = ""
                            # V124: Scores nur Info, kein Satz! Fav = GROSS, Gegner = klein mit ...
                            _is_fav_scorer = (not _is_oneoff and name and name.lower() in scorer.lower()) if scorer else False
                            _short_scorer = _short_team(scorer) if scorer else ""
                            if lg in ("NFL","NCAAF"):
                                if "TOUCHDOWN" in label: _lbl2 = "TOUCHDOWN!" if _is_fav_scorer else "Touchdown..."
                                elif "FIELD GOAL" in label: _lbl2 = "Field Goal!" if _is_fav_scorer else "Field Goal..."
                                elif "SAFETY" in label: _lbl2 = "Safety!" if _is_fav_scorer else "Safety..."
                                elif "EXTRA POINT" in label or "2-POINT" in label: _lbl2 = label.title() if _is_fav_scorer else label.lower()+"..."
                                else: _lbl2 = label
                                _emoji2 = "🔴" if "TOUCHDOWN" in label else "🏈"
                            elif lg=="NHL": _lbl2 = "TOR!" if _is_fav_scorer else "Tor..."; _emoji2="🏒"
                            elif lg=="MLB": _lbl2 = "RUN!" if _is_fav_scorer else "Run..."; _emoji2="⚾"
                            elif lg=="NBA": _lbl2 = "Korb!" if _is_fav_scorer else "Korb..."; _emoji2="🏀"
                            else: _lbl2 = label; _emoji2=LEAGUES[lg]['emoji']
                            # V124: Zeit dazu! Sonst weiß man nicht, wann der Score war!
                            _clk = ""
                            try: _clk = live_clock(ev, lg) or ""
                            except: _clk = ""
                            # V222: Einzeiler! Vorher 3 Zeilen (Label + Score + Uhr) = Stapel im Chat!
                            _time_line = f" • ⏰ {_clk}" if _clk else ""
                            _live_txt = f"{_emoji2} {_lbl2} {_short_scorer} • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}{_time_line}{_scorer_line}"
                            # V222: XP nach TD = kein eigener Push (siehe _skip_xp222 oben - TD-Nachricht wird per Edit aktualisiert)!
                            if not _skip_xp222:
                                try:
                                    _lm = await _live_send_dnd(context, uid, eid, lg, _fav_disp, _live_txt)
                                    # V98-A: In 2 Min Scorer nachladen und reineditieren (wenn ESPN ihn dann hat)!
                                    try:
                                        if _lm and getattr(_lm, "message_id", None) and context.job_queue:
                                            _et222b = event_teams(ev)
                                            _teams222b = _et222b[0] if _et222b else []
                                            _away222b = next((x[0] for x in _teams222b if (x[1] or "").lower()=="away"), "")
                                            _home222b = next((x[0] for x in _teams222b if (x[1] or "").lower()=="home"), "")
                                            context.job_queue.run_once(_scorer_update_job, 30, data={"uid": uid, "eid": eid, "lg": lg, "mid": int(_lm.message_id), "orig": _live_txt, "away": _away222b, "home": _home222b}, name=f"scorer_{eid}_{_lm.message_id}")  # V225: 1. Scorer-Versuch schon nach 30 Sek (vorher 120)! Scorer rollt frueher rein!
                                    except: pass
                                except: pass
                    # V103: Halbzeit / Intermission extra! ESPN bleibt bei NCAAF in der Halbzeit bei Q2 + Detail Halftime, Period springt erst bei Q3!
                    try:
                        _detail = ((ev.get("status", {}) or {}).get("type", {}) or {}).get("detail", "") or ((ev.get("status", {}) or {}).get("type", {}) or {}).get("shortDetail", "") or ""
                        _dl = _detail.lower()
                        _is_ht = ("halftime" in _dl or "half time" in _dl or "intermission" in _dl or "end of 2nd" in _dl or "end of 2nd quarter" in _dl)
                        if cfg.get("period") and state == "in" and _is_ht and not prev.get("halftime_sent"):
                            # V124: Halbzeit warm, aber kurz! München wenn International!
                            _is_muc = False
                            try:
                                _is_muc,_ = is_neutral_or_international(ev, "")
                            except: pass
                            _ort = " in München!" if _is_muc else "!"
                            if lg in ("NFL", "NCAAF"):
                                _ht_txt = f"⏸️ Halbzeit{_ort} • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Kurze Pause! 🥤"
                            elif lg == "NHL":
                                _ht_txt = f"⏸️ Pause! • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Kurze Pause! 🥤"
                            elif lg == "NBA":
                                _ht_txt = f"⏸️ Halbzeit! • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Kurze Pause! 🥤"
                            else:
                                _ht_txt = f"⏸️ Pause! • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}"
                            try: await _live_send_dnd(context, uid, eid, lg, _fav_disp, _ht_txt)  # V211: DND!
                            except: pass
                            prev["halftime_sent"] = True
                            try: prev["awaiting_resume"] = int(period) + 1 if period is not None else None
                            except: prev["awaiting_resume"] = None
                        # Wenn Spiel wieder laeuft (Detail nicht mehr Halftime), Flag zuruecksetzen, damit naechste Halbzeit wieder kommt
                        if _is_ht is False and prev.get("halftime_sent") and period is not None and int(period) >= 3:
                            # Weiter gehts wird unten schon geschickt, Halftime-Flag erst bei naechstem Spiel zuruecksetzen - hier nicht, sonst doppelt!
                            pass
                    except: pass
                    # Perioden-Ende? Period hat sich erhoeht, Spiel noch live
                    # V100-FIX: NICHT game_line(ev) nehmen (zeigt schon neue Uhr 14:28 Q2)! Nur Score + Stand nach altem Abschnitt!
                    # V103: Wenn Halbzeit schon geschickt (2->3), kein doppeltes Perioden-Ende mehr! Weiter kommt unten!
                    _skip_pe = bool(prev.get("halftime_sent") and prev["period"] is not None and int(prev["period"]) == 2 and period is not None and int(period) == 3)
                    if cfg.get("period") and state == "in" and prev["period"] is not None and period is not None and int(period) > int(prev["period"]) and int(prev["period"]) >= 1 and not _skip_pe:  # V223: 0.-Quarter-Fix! Vorherige Periode 0 = Spiel hat noch nicht angefangen -> KEIN "0. Quarter vorbei!" mehr!
                        try: await _live_send_dnd(context, uid, eid, lg, _fav_disp, f"⏸️ {live_period_label(lg, prev['period'])} vorbei! • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}")  # V211: DND!
                        except: pass
                        try: prev["awaiting_resume"] = int(period)
                        except: pass
                    # V100: Weiter gehts! Uhr im neuen Abschnitt laeuft (mind. 5 Sek unter Max) -> Spiel geht weiter!
                    if cfg.get("period") and state == "in" and prev.get("awaiting_resume") is not None and period is not None and int(period) == int(prev.get("awaiting_resume")):
                        try:
                            _cs = _clock_secs(ev)
                            _max = 1200 if lg == "NHL" else 900 if lg in ("NFL", "NCAAF") else 720 if lg == "NBA" else None
                            if _cs is not None and _max is not None and _cs < _max - 5:
                                # V127: Nur Zeit dazu! Kurz bleibt kurz! 14:17 zeigt: schon 43 Sek gespielt, weil ESPN 50 Sek braucht!
                                try: await _live_send_dnd(context, uid, eid, lg, _fav_disp, f"▶️ {live_period_label(lg, period)} läuft! • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • ⏰ {live_clock(ev, lg) or ''}")  # V211: DND!
                                except: pass
                                prev["awaiting_resume"] = None
                        except: pass
                    # V108: Crunch-Time! 1x pro Spiel, wenn knapp + 8:00 auf ESPN-Uhr (=5-6 Min echt)!
                    try:
                        if cfg.get("crunch") and state == "in" and not prev.get("crunch_sent"):
                            _diff = abs(list(scores.values())[0] - list(scores.values())[1]) if len(scores) >= 2 else 999
                            _is_crunch = False
                            if lg in ("NFL", "NCAAF", "NBA"):
                                _cs = _clock_secs(ev)
                                if period is not None and int(period) == 4 and _cs is not None and 0 < _cs <= 480:
                                    _thr = 7 if lg in ("NFL","NCAAF") else 10
                                    if _diff <= _thr: _is_crunch = True
                            elif lg == "NHL":
                                _cs = _clock_secs(ev)
                                if period is not None and int(period) == 3 and _cs is not None and 0 < _cs <= 480:
                                    if _diff <= 1: _is_crunch = True
                            elif lg == "MLB":
                                if period is not None and int(period) >= 8:
                                    if _diff <= 2: _is_crunch = True
                            if _is_crunch:
                                _fav_nm = "" if _is_oneoff else fav.split(" (")[0].strip()
                                _fav_sc = None; _opp_sc = None
                                for _k,_v in scores.items():
                                    if _fav_nm.lower() in _k.lower() or _k.lower() in _fav_nm.lower(): _fav_sc = _v
                                    else: _opp_sc = _v
                                _behind = (_opp_sc - _fav_sc) if (_fav_sc is not None and _opp_sc is not None) else _diff
                                _mm = (_clock_secs(ev)//60 if _clock_secs(ev) is not None else 8); _ss = (_clock_secs(ev)%60 if _clock_secs(ev) is not None else 0)
                                if _behind > 0: _ct = f"🔥🔥🔥 CRUNCH-TIME!!! 🔥🔥🔥 • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Noch {_mm}:{_ss:02d} • Nur {_behind} hinten — JETZT WIRD\'S WILD! 👀🔥"
                                elif _behind < 0: _ct = f"🔥🔥🔥 CRUNCH-TIME!!! 🔥🔥🔥 • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Noch {_mm}:{_ss:02d} • Nur {abs(_behind)} vorne — HALT DICH FEST! 😱🔥"
                                else: _ct = f"🔥🔥🔥 CRUNCH-TIME!!! 🔥🔥🔥 • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Noch {_mm}:{_ss:02d} • Unentschieden — JETZT WIRD\'S WILD! 👀🔥"
                                if lg == "MLB": _ct = f"🔥🔥🔥 CRUNCH-TIME!!! 🔥🔥🔥 • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • {int(period)}. Inning! • JETZT WIRD\'S WILD! 👀🔥"
                                try: await _live_send_dnd(context, uid, eid, lg, _fav_disp, _ct)  # V211: DND!
                                except: pass
                                prev["crunch_sent"] = True
                    except: pass
                    # V223: CRUNCH-TIME INTERCEPTION! Nur NFL/NCAAF, nur wenn Crunch-Schalter an + Spiel gerade in der Crunch-Phase (Q4, <=8:00, Diff <=7)!
                    # ESPN Summary-Details enthalten den Play-Typ "Interception" - 1x pro Play (Dedupe via Play-Key in prev["ints_sent"])!
                    # Kein Team-Name im Text: ESPN ordnet den INT-Play nicht immer eindeutig dem fangenden Team zu - lieber kein Name als ein falscher!
                    try:
                        if cfg.get("crunch") and state == "in" and lg in ("NFL", "NCAAF") and period is not None and int(period) == 4:
                            _cs_int = _clock_secs(ev)
                            _diff_int = abs(list(scores.values())[0] - list(scores.values())[1]) if len(scores) >= 2 else 999
                            if _cs_int is not None and 0 < _cs_int <= 480 and _diff_int <= 7:
                                if not prev.get("ints_sent"): prev["ints_sent"] = []
                                for _d in (espn_summary_details(ev, lg) or []):
                                    try:
                                        _dt_raw = _d.get("type") or {}
                                        if isinstance(_dt_raw, dict):
                                            _dtype = _dt_raw.get("text", "") or _dt_raw.get("shortText", "") or ""
                                        else:
                                            _dtype = str(_dt_raw or "")
                                        _dtxt = ((_d.get("text", "") or "") + " " + _dtype).lower()
                                        if "intercept" not in _dtxt: continue
                                        _dper = _d.get("period")
                                        if _dper is not None and int(_dper) != 4: continue
                                        _dclock = _d.get("clock", {})
                                        if isinstance(_dclock, dict): _dclock = _dclock.get("displayValue", "") or ""
                                        _dclock = str(_dclock or "")
                                        _dkey = str(_d.get("id", "") or "") or f"{_dper}|{_dclock}|{_dtxt[:60]}"
                                        if _dkey in prev["ints_sent"]: continue
                                        prev["ints_sent"].append(_dkey)
                                        try: await _live_send_dnd(context, uid, eid, lg, _fav_disp, f"🚨 INTERCEPTION! Ballwechsel! • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • ⏰ {live_clock(ev, lg) or ''} • Jetzt wird's wild! 👀")  # V223: DND!
                                        except: pass
                                    except: continue
                    except: pass
                    # V124: 2-Minute Warning! Nur NFL/NCAAF, nur 4. Quarter, nur wenn eng (Diff <=8)!
                    try:
                        if cfg.get("period") and state=="in" and lg in ("NFL","NCAAF") and period is not None and int(period)==4 and not prev.get("2min_sent"):
                            _cs2=_clock_secs(ev)
                            _diff2=abs(list(scores.values())[0]-list(scores.values())[1]) if len(scores)>=2 else 999
                            if _cs2 is not None and 0 < _cs2 <= 120 and _diff2 <= 8:
                                try: await _live_send_dnd(context, uid, eid, lg, _fav_disp, f"⏰ 2-Minute Warning! • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Noch 2:00 im 4. Quarter! • Jetzt wird\'s ernst! 👀")  # V211: DND!
                                except: pass
                                prev["2min_sent"]=True
                    except: pass
                    # V124: Spiel-Breaking! RULED OUT / OUT - nur wenn an, 1x pro Spieler!
                    # ESPN Injuries-API: wir gucken die Verletzungsliste für das Liga-Team (nur NFL/NCAAF, sonst zu viel)!
                    # Hier: Platzhalter-Logik über Summary-Details (Ejection / Injury im Detail-Text)!
                    try:
                        if cfg.get("breaking") and state=="in" and not prev.get("breaking_sent_ids"):
                            prev["breaking_sent_ids"]=[]
                    except: pass
                    # Endstand?
                    # V211: DND an? -> Endstand nur sammeln, NIX schicken! Vorher ging der Endstand direkt raus - nie auf dem Zettel!
                    if dnd_active(uid) and cfg.get("final") and state == "post" and prev["state"] != "post":
                        try: add_pending(uid, eid, lg, _fav_disp)
                        except: pass
                    elif cfg.get("final") and state == "post" and prev["state"] != "post":
                        try:
                            _fs_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Final Stats", callback_data=f"finalstats:{eid}:{lg}")]])
                            # V124: Endstand custom! Fav gewonnen/verloren? Bye Week?
                            _final_txt = f"🏁 Endstand! • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Was ein Spiel!"
                            try:
                                if not _is_oneoff and fav and lg:
                                    _fav_nm = fav.split(" (")[0].strip()
                                    _fav_sc2=None; _opp_sc2=None; _opp_nm2=""
                                    for _k2,_v2 in scores.items():
                                        if _fav_nm.lower() in _k2.lower(): _fav_sc2=_v2
                                        else: _opp_sc2=_v2; _opp_nm2=_k2
                                    # Beide Favoriten? Dann neutral!
                                    _both_fav=False
                                    try:
                                        _favs_all2=load_favs().get(str(uid),[]) or []
                                        _cnt2=sum(1 for _f2 in _favs_all2 if _f2.split(" (")[0].strip().lower() in " ".join(scores.keys()).lower())
                                        # Einfacher: beide Teams in Fav-Liste?
                                        _names_low=[_k2.lower() for _k2 in scores.keys()]
                                        _both_fav = all(any(_fn.split(" (")[0].strip().lower() in _nl for _fn in _favs_all2) for _nl in _names_low) and len(_names_low)>=2 and len(_favs_all2)>=2 and sum(1 for _fn in _favs_all2 if any(_fn.split(" (")[0].strip().lower() in _nl for _nl in _names_low))>=2
                                    except: _both_fav=False
                                    if _fav_sc2 is not None and _opp_sc2 is not None and not _both_fav:
                                        _short_fav=_short_team(_fav_nm)
                                        if _fav_sc2 > _opp_sc2:
                                            _final_txt = f"🏁 Sieg! {_short_fav} gewinnen! 🎉 • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Jaaaa! Was ein Spiel!"
                                        elif _fav_sc2 < _opp_sc2:
                                            _has_next=_has_game_next_week(_fav_nm, lg)
                                            if _has_next:
                                                _final_txt = f"🏁 Schade... {_short_fav} verlieren 😔 • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Hm, schade... Aber nächste Woche wird weiter gekämpft! 💪"
                                            else:
                                                _final_txt = f"🏁 Schade... {_short_fav} verlieren 😔 • {LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)} • Hm, schade... Jetzt erstmal Bye Week, Pause! Danach wird weiter gekämpft! 💪"
                            except: pass
                            # V222: Rollend! Endstand ersetzt die letzte Live-Nachricht - nur der Endstand steht da!
                            try: await _live_delete_prev(context, uid, eid)
                            except: pass
                            _em = await context.bot.send_message(chat_id=uid, text=_final_txt, reply_markup=_fs_kb)
                            if _em and getattr(_em, "message_id", None): _LIVE_MSG_IDS.setdefault((uid, str(eid)), []).append(int(_em.message_id)); _save_live_msg_ids()
                        except:
                            try: await _live_send(context, uid, eid, f"✅ Endstand: {_fav_disp} • {LEAGUES[lg]['emoji']} {game_line(ev, lg)}")
                            except: pass
                    if state == "post" and prev["state"] != "post" and _LIVE_MSG_IDS.get((uid, str(eid))) and not dnd_active(uid):  # V211: Bei DND nicht nachts aufpoppen!
                        try:
                            _cq = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, löschen", callback_data=f"live_clean_yes:{eid}"), InlineKeyboardButton("❌ Nein, behalten", callback_data=f"live_clean_no:{eid}")]])
                            _qm = await context.bot.send_message(chat_id=uid, text=f"🏁 Spiel zu Ende! {_fav_disp}\n\nSoll ich die Live-Nachrichten von diesem Spiel löschen?", reply_markup=_cq)
                            if _qm and getattr(_qm, "message_id", None): _LIVE_MSG_IDS.setdefault((uid, str(eid)), []).append(int(_qm.message_id)); _save_live_msg_ids()
                        except: pass
                    _LIVE_SEEN[key] = {"scores": scores, "period": period, "state": state, "last_td": prev.get("last_td") or {}, "awaiting_resume": prev.get("awaiting_resume"), "halftime_sent": prev.get("halftime_sent", False), "crunch_sent": prev.get("crunch_sent", False), "start_sent": prev.get("start_sent", False), "2min_sent": prev.get("2min_sent", False), "ints_sent": prev.get("ints_sent") or []}
    except Exception as e:
        logger.warning(f"live_score_job: {e}")
_REMEMBER = None
async def reminder_job(context):
    # V67: Alle 15 Min laufen! Gruppiert Spiele mit gleichem Start in 1 Nachricht + Sender dazu!
    try:
        favs_all = load_favs()
        if not favs_all: return
        now = datetime.now(BERLIN)
        for uid_str, favs in favs_all.items():
            if not favs: continue
            try: uid = int(uid_str)
            except: continue
            mins = get_reminder_minutes(uid)
            if mins is None: continue
            # Naechste Spiele der Favoriten in den naechsten (mins+15) Min suchen
            upcoming = []  # (start_dt, league, ev, fav_name)
            for league in LEAGUES:
                for offset in range(0, 3):
                    d = now.date() + timedelta(days=offset)
                    for ev in espn_scoreboard(league, dates=d.strftime("%Y%m%d")):
                        if ev.get("status",{}).get("type",{}).get("state","")=="post": continue
                        _, dt = fmt_dt(ev.get("date",""))
                        if not dt: continue
                        diff = (dt - now).total_seconds()/60
                        if diff < 0 or diff > mins + 15: continue
                        teams,_ = event_teams(ev)
                        team_text = " ".join([x[0] for x in teams]).lower()
                        for f in favs:
                            name = f.split(" (")[0].strip()
                            lg = f.split(" (")[-1].replace(")", "").strip() if " (" in f else None
                            if lg and lg != league: continue
                            if name.lower() in team_text:
                                key = (uid, ev.get("id"), mins)
                                if key in _REMINDER_SENT: break
                                upcoming.append((dt, league, ev, name))
                                break
            # V204: Reminder auch fuer einzelne Live-Spiele (One-Off)! Gleicher Reminder wie Favoriten!
            try:
                _oo204 = (load_settings().get(str(uid), {}) or {}).get("oneoff_live", {}) or {}
                for _eid204, _od204 in _oo204.items():
                    if not _od204 or not _od204.get("reminder"): continue
                    _lg204 = _od204.get("lg","")
                    if _lg204 not in LEAGUES: continue
                    for _off204 in range(-1, 3):
                        _d204 = now.date() + timedelta(days=_off204)
                        for _ev204 in espn_scoreboard(_lg204, dates=_d204.strftime("%Y%m%d")):
                            if str(_ev204.get("id","")) != str(_eid204): continue
                            if _ev204.get("status",{}).get("type",{}).get("state","") == "post": continue
                            _, _dt204 = fmt_dt(_ev204.get("date",""))
                            if not _dt204: continue
                            _diff204 = (_dt204 - now).total_seconds()/60
                            if _diff204 < 0 or _diff204 > mins + 15: continue
                            _key204 = (uid, _ev204.get("id"), mins)
                            if _key204 in _REMINDER_SENT: continue
                            upcoming.append((_dt204, _lg204, _ev204, _od204.get("name","") or f"Spiel {_eid204}"))
            except: pass
            if not upcoming: continue
            # Gruppieren nach Startzeit (gleiche Minute = gleiche Nachricht!)
            groups = {}
            for dt, league, ev, name in sorted(upcoming, key=lambda x: x[0]):
                k = dt.strftime("%d.%m. %H:%M")
                groups.setdefault(k, []).append((dt, league, ev, name))
            for k, items in groups.items():
                if dnd_active(uid): continue  # V203: DND an = kein Reminder - Handy bleibt ruhig! Spiel wird per Live gesammelt!
                # V222: Echte Restzeit zum Sendezeitpunkt! Vorher: starrer Text aus der Einstellung ("1h") - aber wenn DND den Reminder verzoegert, waren es nur noch 37 Min!
                _diff_min = max(0, (items[0][0] - now).total_seconds() / 60)
                if _diff_min >= 60:
                    _h222 = int(_diff_min // 60); _m222 = int(round(_diff_min % 60))
                    _remain222 = f"In ca. {_h222}h" if _m222 == 0 else f"In ca. {_h222}h {_m222} Min"
                else:
                    _remain222 = f"In ca. {int(round(_diff_min))} Min"
                lines = [f"⏰ Reminder - {_remain222} geht's los! ({k})\n"]
                for dt, league, ev, name in items:
                    _REMINDER_SENT.add((uid, ev.get("id"), mins))
                    b = broadcast_line(ev)
                    btxt = f" - 📺 {b}" if b else ""
                    lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league)}{btxt}")
                lines.append("\nViel Spaß! 🍿")
                try: await context.bot.send_message(chat_id=uid, text="\n".join(lines))
                except Exception: pass
    except Exception as e:
        logger.warning(f"reminder_job: {e}")
async def remind_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await settings_reminder_cmd(update, ctx)

async def _typing(update, ctx):
    # V114: Bot tippt... anzeigen, fühlt sich flüssiger an!
    try: await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except: pass

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # V147: Zahl für Live-Stats-Auswahl (z.B. „1" nach „Tippe die Zahl ein")!
    try:
        _txt0=(update.message.text or "").strip() if update.message else ""
        if _txt0.isdigit() and ctx.user_data.get("await_live_stats_pick"):
            _live2=ctx.user_data.get("live_events_v147") or []
            _n=int(_txt0)
            if 1 <= _n <= len(_live2):
                # V246: Flag BLEIBT an! Sonst ging nach dem Schliessen eines Spiels die naechste Zahl nicht mehr!
                await live_stats_one_cmd(update, ctx, _n-1, num_mid=update.message.message_id); return
    except Exception:
        pass
    await _typing(update, ctx)
    txt = (update.message.text or "").strip()
    # V113: Deine getippte Zahl in die Schließen-Kette!
    try:
        if txt.isdigit():
            _uid_o = update.effective_user.id if update.effective_user else 0
            _chain_add(_uid_o, update.message.message_id)
    except: pass
    # V112: Zahl für Meine Live-Spiele!
    if txt.isdigit() and ctx.user_data.get("my_live_list") and not ctx.user_data.get("awaiting_fav"):
        _ml = ctx.user_data.get("my_live_list") or []
        _nm = int(txt)
        if 1 <= _nm <= len(_ml):
            _eid_m, _lg_m = _ml[_nm-1]
            # V240: Liste BEHALTEN! Vorher = None -> nach Schliessen passierte bei der naechsten Zahl nix mehr!
            await next_live_pick_cmd(update, ctx, _lg_m, _eid_m, num_mid=update.message.message_id); return
    # V110: Zahl für Nächste Spiele Live (wie bei Favoriten!)
    if txt.isdigit() and ctx.user_data.get("next_live_list") and not ctx.user_data.get("awaiting_fav"):
        _nl = ctx.user_data.get("next_live_list") or []
        _n = int(txt)
        if 1 <= _n <= len(_nl):
            _lg, _eid = _nl[_n-1]
            # V240: Liste BEHALTEN! Vorher = None -> nach Schliessen passierte bei der naechsten Zahl nix mehr!
            await next_live_pick_cmd(update, ctx, _lg, _eid, num_mid=update.message.message_id); return
    # V227: Zahl für Next Games Heute/Morgen -> Detail + Benachrichtigungen!
    if txt.isdigit() and ctx.user_data.get("next_games_list") and not ctx.user_data.get("awaiting_fav"):
        _ng227 = ctx.user_data.get("next_games_list") or []
        _n227 = int(txt)
        if 1 <= _n227 <= len(_ng227):
            _lg227, _eid227 = _ng227[_n227-1]
            # V240: Liste BEHALTEN! Vorher = None -> nach Schliessen passierte bei der naechsten Zahl nix mehr! (Heute-Liste!)
            await next_live_pick_cmd(update, ctx, _lg227, _eid227, num_mid=update.message.message_id); return
    # V110: Zahl für Ergebnisse Final Stats!
    if txt.isdigit() and ctx.user_data.get("results_list") and not ctx.user_data.get("awaiting_fav"):
        _rl = ctx.user_data.get("results_list") or []
        _n2 = int(txt)
        if 1 <= _n2 <= len(_rl):
            _lg2, _eid2 = _rl[_n2-1]
            # V240: Liste BEHALTEN! Vorher = None -> nach Schliessen passierte bei der naechsten Zahl nix mehr!
            _uid2 = update.effective_user.id if update.effective_user else 0
            _load = await update.message.reply_text("⏳ Spiel wird zusammengefasst...\nEinen Moment, ich hol die Stats von ESPN!")
            _txt2 = get_final_stats_text(_eid2, _lg2) if _lg2 in LEAGUES else ""
            if _txt2:
                try: await ctx.bot.delete_message(chat_id=_uid2, message_id=_load.message_id)
                except: pass
                _del_rows = []
                if _lg2 in LEAGUES:
                    _del_rows.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{_eid2}:{_lg2}")])
                # V158: YouTube Highlights + Pressekonferenz - du entscheidest selbst!
                _del_rows.extend(_yt_buttons_for_game(_eid2, _lg2, _txt2))
                _del_rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
                _del_kb = InlineKeyboardMarkup(_del_rows)
                _m2 = await update.message.reply_text(_txt2, reply_markup=_del_kb)
                # V201: Fenster in Kette + Zahl mappen (sonst blieb Fenster bei 'Alle schliessen' uebrig)!
                try: _chain_add(_uid2, _m2.message_id); _CLOSE_NUM_MAP[(int(_uid2), int(_m2.message_id))] = int(update.message.message_id)
                except: pass
            else:
                _kb2 = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, nochmal schauen!", callback_data=f"finalstats_retry:{_eid2}:{_lg2}"), InlineKeyboardButton("❌ Nein, danke!", callback_data=f"finalstats_no:{_eid2}:{_lg2}")]])
                try: await ctx.bot.edit_message_text(chat_id=_uid2, message_id=_load.message_id, text="😅 Grad noch keine Stats vorhanden!\nESPN ist noch langsam!\nSoll ich in 5 Min nochmal schauen?", reply_markup=_kb2)
                except: pass
            return
    # V154: Zahl für Live-Finals -> Final Stats (nur wenn kein results_list aktiv)!
    if txt.isdigit() and ctx.user_data.get("live_finals_list") and not ctx.user_data.get("results_list") and not ctx.user_data.get("awaiting_fav"):
        _lf2 = ctx.user_data.get("live_finals_list") or []
        _nlf = int(txt)
        if 1 <= _nlf <= len(_lf2):
            _lg3, _eid3 = _lf2[_nlf-1]
            # V240: Liste BEHALTEN! Vorher = None -> nach Schliessen passierte bei der naechsten Zahl nix mehr!
            _uid3 = update.effective_user.id if update.effective_user else 0
            _load3 = await update.message.reply_text("⏳ Spiel wird zusammengefasst...\nEinen Moment, ich hol die Stats von ESPN!")
            _txt3 = get_final_stats_text(_eid3, _lg3) if _lg3 in LEAGUES else ""
            if _txt3:
                try: await ctx.bot.delete_message(chat_id=_uid3, message_id=_load3.message_id)
                except: pass
                _rows3 = []
                if _lg3 in LEAGUES:
                    _rows3.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{_eid3}:{_lg3}")])
                _rows3.extend(_yt_buttons_for_game(_eid3, _lg3, _txt3))
                _rows3.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
                _m3 = await update.message.reply_text(_txt3, reply_markup=InlineKeyboardMarkup(_rows3))
                # V201: Fenster in Kette + Zahl mappen!
                try: _chain_add(_uid3, _m3.message_id); _CLOSE_NUM_MAP[(int(_uid3), int(_m3.message_id))] = int(update.message.message_id)
                except: pass
            else:
                _kb3 = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, nochmal schauen!", callback_data=f"finalstats_retry:{_eid3}:{_lg3}"), InlineKeyboardButton("❌ Nein, danke!", callback_data=f"finalstats_no:{_eid3}:{_lg3}")]])
                try: await ctx.bot.edit_message_text(chat_id=_uid3, message_id=_load3.message_id, text="😅 Grad noch keine Stats vorhanden!\nESPN ist noch langsam!\nSoll ich in 5 Min nochmal schauen?", reply_markup=_kb3)
                except: pass
            return
    if txt.isdigit() and 1 <= int(txt) <= 10 and ctx.user_data.get("top10_list") and not ctx.user_data.get("awaiting_fav"):
        await top10_detail_cmd(update, ctx, int(txt)); return
    # V214: Zahl für Tabellen -> Team-Fenster!
    if txt.isdigit() and ctx.user_data.get("tables_team_list") and not ctx.user_data.get("awaiting_fav"):
        _tl214 = ctx.user_data.get("tables_team_list") or {}
        _trows214 = _tl214.get("rows") or []
        _tn214 = int(txt)
        if 1 <= _tn214 <= len(_trows214):
            # V240: Liste BEHALTEN! Vorher = None -> nach Schliessen passierte bei der naechsten Zahl nix mehr! (Tabellen!)
            await team_window_cmd(update, ctx, _tl214.get("league", ""), _trows214[_tn214-1], _tn214, _tl214.get("div", ""), _tl214.get("back", ""), num_mid=update.message.message_id)
            return

    # V242: Zahl für Nerd-Modus Teams (1-32)!
    if txt.isdigit() and ctx.user_data.get("nerd_teams_list") and not ctx.user_data.get("awaiting_fav"):
        _nt242 = ctx.user_data.get("nerd_teams_list") or []
        _nn242 = int(txt)
        if 1 <= _nn242 <= len(_nt242):
            # V240: Liste BEHALTEN!
            await nerd_team_cmd(update, ctx, _nt242[_nn242-1]); return
    # V242: Zahl für Nerd-Modus Hall of Famers!
    if txt.isdigit() and ctx.user_data.get("nerd_hof_list") and not ctx.user_data.get("awaiting_fav"):
        _nh242 = ctx.user_data.get("nerd_hof_list") or {}
        _names242 = _nh242.get("names") or []
        _nhn242 = int(txt)
        if 1 <= _nhn242 <= len(_names242):
            # V240: Liste BEHALTEN!
            await nerd_hof_detail_cmd(update, ctx, _nh242.get("team", ""), _nhn242-1); return
    if not ctx.user_data.get("awaiting_fav"): return
    ctx.user_data["awaiting_fav"]=False
    name = update.message.text.strip()
    low = name.lower().strip()
    # 1) Exakter Vollname? z.B. "Pittsburgh Steelers"
    for lg, lst in TEAMS.items():
        for full in lst:
            if low == full.lower():
                chosen = f"{full} ({lg})"
                favs = load_favs(); uid=str(update.effective_user.id); favs.setdefault(uid, [])
                if chosen not in favs[uid]: favs[uid].append(chosen)
                save_favs(favs)
                await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=small_kb())
                return
    # 2) Spitzname? z.B. "Steelers" oder "Panthers"
    if low in NICKNAME_MAP:
        cands = NICKNAME_MAP[low]
        if len(cands)==1:
            chosen = cands[0]
            favs = load_favs(); uid=str(update.effective_user.id); favs.setdefault(uid, [])
            if chosen not in favs[uid]: favs[uid].append(chosen)
            save_favs(favs)
            await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=small_kb())
            return
        else:
            ctx.user_data["fav_candidates"]=cands
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{i+1}. {m}", callback_data=f"fav_pick:{i}")] for i,m in enumerate(cands)])
            await update.message.reply_text("Welches Team meinst du? Bitte nur die Zahl schicken:", reply_markup=kb)
            ctx.user_data["awaiting_fav_pick"]=True
            return
    # 3) Stadt / Bundesstaat? z.B. "Texas", "New York", "Los Angeles", "Pittsburgh"
    city_cands = _find_by_city_or_state(low)
    if len(city_cands)>1:
        ctx.user_data["fav_candidates"]=city_cands
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{i+1}. {m}", callback_data=f"fav_pick:{i}")] for i,m in enumerate(city_cands[:12])])
        await update.message.reply_text("Welches Team meinst du? Bitte nur die Zahl schicken:", reply_markup=kb)
        ctx.user_data["awaiting_fav_pick"]=True
        return
    elif len(city_cands)==1:
        chosen = city_cands[0]
        favs = load_favs(); uid=str(update.effective_user.id); favs.setdefault(uid, [])
        if chosen not in favs[uid]: favs[uid].append(chosen)
        save_favs(favs)
        await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=small_kb())
        return
    # 4) Teil-Suche: z.B. "Steel" findet Steelers, "Longhorn" findet Longhorns
    partial=[]
    for lg, lst in TEAMS.items():
        for full in lst:
            if low in full.lower(): partial.append(f"{full} ({lg})")
    if len(partial)>1:
        ctx.user_data["fav_candidates"]=partial
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{i+1}. {m}", callback_data=f"fav_pick:{i}")] for i,m in enumerate(partial[:12])])
        await update.message.reply_text("Welches Team meinst du? Bitte nur die Zahl schicken:", reply_markup=kb)
        ctx.user_data["awaiting_fav_pick"]=True
        return
    elif len(partial)==1:
        chosen = partial[0]
        favs = load_favs(); uid=str(update.effective_user.id); favs.setdefault(uid, [])
        if chosen not in favs[uid]: favs[uid].append(chosen)
        save_favs(favs)
        await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=small_kb())
        return
    # 5) Gar nichts gefunden -> nicht einfach speichern, sondern nachfragen!
    await update.message.reply_text(f"Hmm, '{name}' nicht gefunden. Probier mal den vollen Teamnamen, z.B. 'Pittsburgh Steelers'.", reply_markup=small_kb())
    return
    chosen = partial[0] if partial else name
    favs = load_favs(); uid=str(update.effective_user.id)
    favs.setdefault(uid, [])
    if chosen not in favs[uid]: favs[uid].append(chosen)
    save_favs(favs)
    await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=small_kb())


# V94: Hilfe passend zur Funktion, wo man grade ist! Nur beim Start / Hauptmenue die ganze Hilfe!

# V134: Hilfe in Kategorien - nicht mehr ein Batzen Text!
HELP_CATS = {
 "grund": "❓ Hilfe - Grundlagen\n\n**Gast @ Heim**\nErstes Team = Auswärts, zweites = Heim!\nZ.B. Vikings @ Packers = Vikings spielt bei den Packers!\n\n**⭐ = Dein Team**\nDas ist einer deiner Favoriten!\n\n**📺 = US-Sender**\nSender in den USA (CBS / FOX / ESPN...). Deutsche Sender zeigen wir nicht, Rechte ändern sich ständig!\n\n**📍 / 🏟️ = Stadion / Ort**\nWo das Spiel stattfindet!\n\n**Kürzel in Listen**\nSF = 49ers, MIN = Vikings, DAL = Cowboys - kurz + schnell! Volle Namen stehen im Detail!",
 "spiele": "❓ Hilfe - Spiele / Live / Next Games\n\n**🔴 Live**\nLäuft gerade! Scoreboard: Kürzel + Punktestand + Zeit! Scorer rollt rein, wenn einer punktet! Nach Spielende: Fenster schließen reicht!\n\n**⏭️ Next Games**\nHeute / Morgen = alle Spiele! Nur Favoriten = nur deine Teams! Zahl vom Spiel schreiben = Details + Benachrichtigungen!\n\n**✅ Ergebnisse**\nWie die letzten Spiele ausgingen, mit Final Stats!\n\n**ℹ️ Mehr Infos zum Spiel**\nSpiel-Informationen: Kickoff (US-Zeit zuerst, dann DE-Zeit), Wetter, Ort + Sender als eigene Zeilen! Zahl = Benachrichtigungen für das Spiel!",
 "tabellen": "❓ Hilfe - Tabellen / Top 10\n\n**📊 Tabellen**\nW-L-OTL = Siege - Niederlagen - Overtime-Niederlagen.\nNHL: Sieg = 2 Punkte, Overtime-Niederlage = 1 Punkt!\n\n**👉 Zahl tippen = Team-Fenster!**\nIn der Tabelle die Zahl vom Team tippen (z.B. 1) → Platz, Bilanz, Punkte/GB, Heim/Auswärts, Streak, Letzte 10, nächste 3, letzte 3, News + Key Spieler!\n\n**🏆 Top 10**\nTippe Zahl 1-10 für Rating + Warum so bewertet!\nRating (z.B. ⭐ 9,9/10) steht nur im Detail!\n\n**🎓 CFP Top 25**\nNur NCAAF: Die besten 25 College-Teams + nächstes Ranking!",
 "benach": "❓ Hilfe - Benachrichtigungen\n\nIn ⚙️ Einstellungen → 🔔 Benachrichtigungen:\n**⏰ Reminder** - 3h / 2h / 1h / 30 Min / Aus. 2 Favoriten gleichzeitig = 1 Nachricht für beide, mit Sender!\n**🔴 Live-Scores** - Nur für Favoriten, pro Team: Jeder Score / Spielstart + Quarter-Wechsel / Endstand / Crunch-Time / Spiel-Breaking!\n**🌙 DND / Nicht stören** - Nachts keine Nachrichten! Danach kommt eine Zusammenfassung!\nAlles aus = kein Spam!",
 "news": "❓ Hilfe - News / Verletzungen / Breaking\n\n**📰 News** - Nur deine Favoriten! Nur Headline + Link!\nQuelle: ESPN! Artikel sind auf Englisch!\nKein Push-Spam - du holst dir News, wenn du willst!\n\n**🌍 Liga-Breaking** - In News ganz oben als Toggle! Nur große Sachen: International Series, Schedule, Super Bowl, Playoffs, Trade Deadline! Push, aber nur 1x!\n\n**🚨 Spiel-Breaking** - Bei Favorit / Live-Spiel: Nur OUT / RULED OUT / Ejection! Nur 1x pro Spieler!\n\n**🏥 Verletzungen** - Daten von Sleeper (NFL) / ESPN (NBA, NHL, MLB). Offizielle Team-Apps können bis zu 15 Min schneller sein - Bot holt alle 15 Min neu!",
 "myweek": "❓ Hilfe - Meine Woche\n\n**📅 Meine Woche**\nAlle deine Favoriten auf einen Blick: Platz + Bilanz + neue News (24 Std.)! Bei NCAAF auch CFP-Ranking!\n\n**Knöpfe**\nNext Games / News / Tabellen / CFP Top 25 öffnen sich als Unter-Fenster - Meine Woche bleibt stehen!\n\n**🔄 Aktualisieren**\nHolt alles neu! Innerhalb von 5 Min kommt der Cache (Stand-Zeit steht oben)!",
 "nerd": "❓ Hilfe - Nerd-Modus / Draft\n\n**🧠 Nerd-Modus**\nNFL + Hall of Famers: Pro Spieler Detail-Seite mit echten Werten (nix erfunden)! Ein Fenster, kein Stapel!\n\n**🏆 NFL Draft-Vorschau**\nDraft 29.04.-01.05.2027, Washington D.C.! Reihenfolge nach aktuellem Tabellenstand (schlechtestes Team zuerst) + Top-10-Prospects!",
 "fenster": "❓ Hilfe - Fenster\n\n**🪟 Fenster**\nAuswahl = Fenster ändert sich! Detail = neues Fenster! ✖️ = Fenster weg!\n\n**🧹 Auto-Schließen**\nIn ⚙️ Einstellungen → 🪟 Fenster: AN = altes Fenster schließt sich, wenn du aus dem Hauptmenü was Neues öffnest! Hauptmenü + Meine Woche bleiben immer! AUS = alles bleibt offen!\n\n**Einfach auf Knöpfe drücken** - kein @, kein Befehl nötig!",
}
HELP_SHORT = {
    "top10": "❓ Hilfe - Top 10\n\nTippe eine Zahl 1-10 in den Chat für Rating + Warum!\nRating steht nur im Detail, nicht in der Übersicht!\n\n📅 Top 10 zeigt nur Spiele dieser Woche (heute bis Sonntag)! Spiele von nächster Woche sind NICHT dabei!",
    "tables": "❓ Hilfe - Tabellen\n\nW-L-OTL = Siege - Niederlagen - Overtime-Niederlagen.\nBei NHL: Sieg = 2 Punkte, Overtime-Niederlage = 1 Punkt!\n\n💡 Zahl tippen = Team-Fenster! (z.B. 1 für Platz 1)",
    "next": "❓ Hilfe - Next Games\n\nHeute / Morgen = alle Spiele!\nNur Favoriten = nur deine Teams!\n✍️ In Heute/Morgen: Zahl vom Spiel schreiben = Details + Benachrichtigungen!",
    "live": "❓ Hilfe - Live\n\nLäuft gerade! Scorer rollt rein, wenn einer punktet!\nNach Spielende: Fenster schließen reicht!",
    "results": "❓ Hilfe - Ergebnisse\n\nWelche Liga? Dann siehst du, wie die letzten Spiele ausgingen!",
    "settings": "❓ Hilfe - Einstellungen\n\nHier: Favoriten + Benachrichtigungen + Fenster!\nReminder + Live-Scores sind unter Benachrichtigungen!\nAuto-Schließen ist unter Fenster!",
    "notif": "❓ Hilfe - Benachrichtigungen\n\nReminder + Live-Scores!\nLive nur für Favoriten, pro Team: Jeder Score / Perioden-Ende + Weiter / Endstand!",
    "fav": "❓ Hilfe - Favoriten\n\nFavorit hinzufügen / entfernen!\n⭐ = dein Team!",
    "injuries": "❓ Hilfe - Verletzungen\n\nDaten von Sleeper / ESPN, bis zu 15 Min verzögert!\nOffizielle Team-Apps sind schneller!",
    "game_info": "❓ Hilfe - Mehr Infos\n\nWetter, Form, Wer fehlt?\nWähle Liga → Spiel → Detail!",
}

def _help_cats_kb():
    # V251: EIN Kategorien-Menue fuer ueberall - Hauptmenue, /help, Einstellungen, Kontext-Hilfe!
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Grundlagen (Gast @ Heim, ⭐, 📺)", callback_data="help_cat:grund")],
        [InlineKeyboardButton("🏈 Spiele / Live / Next Games", callback_data="help_cat:spiele")],
        [InlineKeyboardButton("📊 Tabellen / Top 10", callback_data="help_cat:tabellen")],
        [InlineKeyboardButton("🔔 Benachrichtigungen", callback_data="help_cat:benach")],
        [InlineKeyboardButton("📰 News / Verletzungen / Breaking", callback_data="help_cat:news")],
        [InlineKeyboardButton("📅 Meine Woche", callback_data="help_cat:myweek")],
        [InlineKeyboardButton("🧠 Nerd-Modus / Draft-Vorschau", callback_data="help_cat:nerd")],
        [InlineKeyboardButton("🪟 Fenster", callback_data="help_cat:fenster")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])


def get_expert_stats_text(eid, lg):
    # V201: SofaScore-Style! NFL/NCAAF: Offense / Passen / Laufspiel. NHL/NBA/MLB: eigene Gruppen (siehe _expert_generic).
    # Final Stats bleiben wie sie sind! Nur Experten-Stats wird SofaScore-Style!
    # Alles aus ESPN Boxscore + Drives. Kein EPA/CPOE. Kein neuer Key!
    # Unsere 5 alten Experten-Werte (Points per Drive, 3-and-Out, Explosive, Sack Rate) bleiben drin, in Offense!
    try:
        if lg in ("NHL", "NBA", "MLB"): return _expert_generic(eid, lg)
        if lg not in ("NFL", "NCAAF"): return ""
        key = LEAGUES[lg]["espn"]
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/{key}/summary"
        r = requests.get(url, params={"event": eid}, timeout=12)
        data = r.json()
        hdr = data.get("header", {}) or {}
        comps = hdr.get("competitions", []) or []
        comp = comps[0] if comps else {}
        competitors = comp.get("competitors", []) or []
        box = data.get("boxscore", {}) or {}
        teams_bs = box.get("teams", []) or []
        stats_by_team = {}; names = []; abbrs = {}
        for tm in teams_bs:
            _team = tm.get("team", {}) or {}
            _nm = _team.get("shortDisplayName", "") or _team.get("displayName", "") or ""
            _abbr = _team.get("abbreviation", "") or ""
            _sd = {}
            for _st in tm.get("statistics", []) or []:
                _lbl = _st.get("displayValue", "") or _st.get("label", "") or ""
                _name = _st.get("name", "") or _st.get("label", "") or ""
                if _name: _sd[_name.lower()] = _lbl
                if _lbl: _sd[(_st.get("label", "") or "").lower()] = _lbl
            stats_by_team[_nm] = _sd; names.append(_nm); abbrs[_nm] = _abbr
        if len(names) < 2: return ""
        a, b = names[0], names[1]
        sa, sb = stats_by_team.get(a, {}), stats_by_team.get(b, {})
        def _score_for(nm):
            for c in competitors:
                _t = c.get("team", {}) or {}
                _n = _t.get("shortDisplayName", "") or _t.get("displayName", "")
                if _n == nm or nm in _n or _n in nm:
                    try: return float(str(c.get("score", "0") or "0").replace(",", ""))
                    except: return 0
            return 0
        def _pick(sd, keys):
            # V160-HYBRID: Erst exakt, dann Teilstring NUR wenn Suchbegriff IN Kandidat steckt (nicht umgekehrt!)
            # V159-Fehler war: 'passing' in 'passing td' -> 120 als TD. Jetzt: 'passing' darf 'passing touchdowns' NICHT treffen, weil Kandidat kuerzer ist!
            def _norm(s):
                return str(s).lower().replace(' ', '').replace('_', '').replace('-', '').replace('/', '')
            flat = {_norm(k): v for k, v in (sd or {}).items()}
            for _k in keys:
                _nk = _norm(_k)
                if _nk in flat and str(flat[_nk]).strip() not in ('', '-', 'None'):
                    return str(flat[_nk]).strip()
            # Fallback: Suchbegriff muss IN Kandidat stecken, Kandidat muss mind. so lang sein wie Suchbegriff - verhindert 'passing' -> 'passing touchdowns'
            for _k in keys:
                _nk = _norm(_k)
                for _kk, _vv in flat.items():
                    if _nk and _nk in _kk and len(_kk) >= len(_nk) and str(_vv).strip() not in ('', '-', 'None'):
                        return str(_vv).strip()
            return ''
        def _num(v):
            try: return float(str(v).replace(",", "").strip())
            except: return None
        def _int(v):
            try: return int(float(str(v).split("-")[0].split("/")[0].strip()))
            except: return None
        def _split_pair(v):
            # "3-25" / "4-46" / "16/32" / "1/1" -> (3, 25) etc.
            try:
                s = str(v).strip().replace(",", "")
                for _sep in ("-", "/"):
                    if _sep in s:
                        x, y = s.split(_sep, 1)
                        return int(float(x.strip())), int(float(y.strip()))
                return int(float(s)), None
            except: return None, None
        # --- Drives: Points per Drive, 3-and-Out, Explosive ---
        abbr_to_name = {}
        for c in competitors:
            _t = c.get("team", {}) or {}
            _n = _t.get("shortDisplayName", "") or _t.get("displayName", "")
            _ab = _t.get("abbreviation", "") or ""
            if _ab: abbr_to_name[_ab] = _n
        for _nm, _ab in abbrs.items():
            if _ab: abbr_to_name[_ab] = _nm
        _dr = data.get("drives", {}) or {}
        _all_drives = list(_dr.get("previous", []) or []) + ([_dr.get("current")] if _dr.get("current") else [])
        _info = {a: {"drives": 0, "three_out": 0, "expl": 0}, b: {"drives": 0, "three_out": 0, "expl": 0}}
        for _d in _all_drives:
            if not isinstance(_d, dict): continue
            _dt = _d.get("team", {}) or {}
            _dnm = abbr_to_name.get(_dt.get("abbreviation", ""), "")
            if _dnm not in _info:
                _ddn = _dt.get("displayName", "") or _dt.get("shortDisplayName", "")
                for _cand in (a, b):
                    if _ddn and (_ddn in _cand or _cand in _ddn): _dnm = _cand; break
            if _dnm not in _info: continue
            _plays = _d.get("plays", []) or []
            if not _plays: continue
            _info[_dnm]["drives"] += 1
            _res = str(_d.get("result", "") or _d.get("shortDisplayResult", "") or _d.get("displayResult", "") or "").lower()
            # V163-FIX 3-and-Out: Definition = kein First Down im Drive + endet mit Punt oder Turnover on Downs!
            # V162-Bugs: (1) len<=3 war zu eng - 4th-Down-Drive hat 4 Plays, Punt-Drive hat oft noch Punt-Return als extra Play -> alles fiel raus -> 0%!
            # (2) 'down' in result traf auch 'touchdown' - schneller TD waere faelschlich 3-and-Out gewesen!
            _OFF_TYPES = ("pass", "pass completion", "pass reception", "passing", "rush", "rushing", "run", "rushing attempt", "sack", "qb sack", "scramble", "pass attempt")
            def _ptype(_pp):
                _ty = _pp.get("type", {}) if isinstance(_pp, dict) else {}
                return str(_ty.get("text", "") if isinstance(_ty, dict) else _ty).lower().strip()
            _off = [p for p in _plays if isinstance(p, dict) and _ptype(p) in _OFF_TYPES]
            # First Down im Drive? ESPN Play hat oft firstDown=True, sonst Text-Check (1st Down / First Down)
            _has_fd = False
            for _pp in _plays:
                if not isinstance(_pp, dict): continue
                if _pp.get("firstDown") is True or _pp.get("first_down") is True: _has_fd = True; break
                _ptxt2 = str(_pp.get("text", "") or "").lower()
                if "first down" in _ptxt2 or "1st down" in _ptxt2: _has_fd = True; break
            _is_score = any(_k in _res for _k in ("touchdown", "field goal", "extra point", "safety", "two-point"))
            _is_punt_or_downs = ("punt" in _res or "turnover on downs" in _res or "downs" in _res or "interception" in _res or "fumble" in _res)
            if (not _has_fd) and (not _is_score) and _is_punt_or_downs and len(_off) <= 4:
                _info[_dnm]["three_out"] += 1
            for _pl in _plays:
                if not isinstance(_pl, dict): continue
                _ptype = _pl.get("type", {})
                _ptxt = str(_ptype.get("text", "") if isinstance(_ptype, dict) else _ptype).lower()
                if _ptxt not in ("pass", "pass completion", "pass reception", "passing", "rush", "rushing", "run", "rushing attempt", "pass", "rushing", ""):
                    # Nur Offense-Plays zaehlen, keine Punts/Kickoffs - wenn Typ unbekannt, trotzdem pruefen (ESPN Typen variieren!)
                    if _ptxt in ("punt", "kickoff", "field goal", "extra point", "kickoff return", "punt return"): continue
                _y = None
                for _k in ("statYardage", "yards", "yardsGained", "yardage"):
                    if _pl.get(_k) is not None:
                        try: _y = abs(float(str(_pl.get(_k)).replace(",", "")))
                        except: _y = None
                        break
                if _y is not None and _y >= 20: _info[_dnm]["expl"] += 1
        sca, scb = _score_for(a), _score_for(b)
        # V167: TDs aus Scoring-Plays! ESPN Team-Stats haben KEINE Passing/Rushing-TDs (darum fehlten sie in V159!)
        # Verifiziert: PIT 2 Pass-TDs (Rodgers), CIN 4 Pass-TDs (Burrow) + je 1 Rush-TD? Aus Scoring-Plays zaehlen!
        _td_counts = {a: {'pass': 0, 'rush': 0, 'total': 0}, b: {'pass': 0, 'rush': 0, 'total': 0}}
        try:
            _sp = data.get('scoringPlays', []) or []
            for _play in _sp:
                if not isinstance(_play, dict): continue
                _pt = _play.get('team', {}) or {}
                _pabbr = _pt.get('abbreviation', '') or ''
                _pname = abbr_to_name.get(_pabbr, '')
                if _pname not in _td_counts:
                    _dn = _pt.get('displayName', '') or _pt.get('shortDisplayName', '') or ''
                    for _cand in (a, b):
                        if _dn and (_dn in _cand or _cand in _dn): _pname = _cand; break
                if _pname not in _td_counts: continue
                _txt = str(_play.get('type', {})).lower() + ' ' + str(_play.get('text', '') or '').lower() + ' ' + str(_play.get('play', {})).lower()
                _is_td = 'touchdown' in _txt or 'td' in _txt.split()
                if not _is_td: continue
                _td_counts[_pname]['total'] += 1
                if 'pass' in _txt: _td_counts[_pname]['pass'] += 1
                elif 'rush' in _txt or 'run' in _txt: _td_counts[_pname]['rush'] += 1
                else:
                    # Ohne Typ: aus Play-Text raten - 'pass' vs 'rush' steht meist drin, sonst als total lassen
                    pass
        except Exception:
            pass
        lines = [f"\U0001f9e0 Experten-Stats: {a} {int(sca)} @ {b} {int(scb)}", f"{abbrs.get(a,'') or a} - {abbrs.get(b,'') or b}"]
        # Helper: Wert fuer beide Teams holen
        def _both(fn):
            va, vb = fn(sa), fn(sb)
            return va, vb
        def _fmt_pair(va, vb, fmt="{v}"):
            return f"{va if va not in ('', None) else '-'} - {vb if vb not in ('', None) else '-'}"
        # ============ OFFENSE (SofaScore-Style + unsere Experten-Werte) ============
        lines.append("")
        lines.append("--- Offense ---")
        # Touchdowns
        def _td(sd):
            v = _pick(sd, ['totaltouchdowns', 'total touchdowns', 'touchdowns'])
            if v and _int(v) is not None and int(_int(v)) > 0: return str(_int(v))
            pt = _int(_pick(sd, ['passing touchdowns', 'passingTouchdowns']))
            rt = _int(_pick(sd, ['rushing touchdowns', 'rushingTouchdowns']))
            if pt is not None or rt is not None: return str((pt or 0) + (rt or 0))
            # V160-Fallback: Scoring-Plays! ESPN Team-Stats haben keine TDs!
            _nm = a if sd is sa else b
            _c = _td_counts.get(_nm, {})
            if _c.get('total'): return str(_c['total'])
            if _c.get('pass') or _c.get('rush'): return str((_c.get('pass') or 0) + (_c.get('rush') or 0))
            return ''
        va, vb = _both(_td)
        if va or vb: lines.append(f"Touchdowns: {_fmt_pair(va, vb)}")
        # Field Goals
        def _fg(sd):
            v = _pick(sd, ["fieldgoals", "field goals", "field goals made"])
            if v and ("/" in str(v) or "-" in str(v)):
                x, y = _split_pair(v)
                return f"{x}/{y}" if y is not None else str(x)
            m = _pick(sd, ["fieldgoalsmade", "field goals made"])
            at = _pick(sd, ["fieldgoalsattempted", "field goals attempted", "fieldgoalattempts"])
            if m and at: return f"{_int(m)}/{_int(at)}"
            return ""
        va, vb = _both(_fg)
        if va or vb: lines.append(f"Field Goals: {_fmt_pair(va, vb)}")
        # Yards gesamt + Yards pro Spielzug
        def _tot_y(sd): return _pick(sd, ["totalyards", "total yards", "totyards"])
        va, vb = _both(_tot_y)
        if va or vb: lines.append(f"Yards gesamt: {_fmt_pair(va, vb)}")
        def _ypp(sd):
            v = _pick(sd, ["yardsperplay", "yards per play", "avgyardsperplay"])
            if v: return str(v)
            ty = _num(_pick(sd, ["totalyards", "total yards"]))
            tp = _num(_pick(sd, ["totalplays", "total plays"]))
            if ty is not None and tp: return f"{ty/tp:.1f}"
            return ""
        va, vb = _both(_ypp)
        if va or vb: lines.append(f"Yards pro Spielzug: {_fmt_pair(va, vb)}")
        # Turnovers
        def _to(sd): return _pick(sd, ["turnovers", "turnover"])
        va, vb = _both(_to)
        if va or vb: lines.append(f"Turnovers: {_fmt_pair(va, vb)}")
        # Red Zone
        def _rz(sd):
            v = _pick(sd, ["redzone", "red zone", "redzoneattempts"])
            if not v: return ""
            x, y = _split_pair(v)
            return f"{x}/{y}" if y is not None else str(v)
        va, vb = _both(_rz)
        if va or vb: lines.append(f"Red-Zone-Effizienz: {_fmt_pair(va, vb)}")
        # Time of Possession
        def _pos(sd): return _pick(sd, ["possessiontime", "possession", "time of possession"])
        va, vb = _both(_pos)
        if va or vb: lines.append(f"Time of possession: {_fmt_pair(va, vb)}")
        # First Downs
        def _fd(sd): return _pick(sd, ["firstdowns", "first downs", "1st downs"])
        va, vb = _both(_fd)
        if va or vb: lines.append(f"First Downs: {_fmt_pair(va, vb)}")
        # 3rd / 4th Down (aus Final Stats bekannt, hier auch gut!)
        def _third(sd): return _pick(sd, ["thirddown", "3rd down", "third down"])
        va, vb = _both(_third)
        if va or vb: lines.append(f"Third-Down-Effizienz: {_fmt_pair(va, vb)}")
        # Unsere Experten-Werte in Offense:
        if _info[a]["drives"] > 0 or _info[b]["drives"] > 0:
            _ppd_a = f"{sca/_info[a]['drives']:.1f}" if _info[a]["drives"] else "-"
            _ppd_b = f"{scb/_info[b]['drives']:.1f}" if _info[b]["drives"] else "-"
            lines.append(f"Points per Drive: {_ppd_a} - {_ppd_b}")
            _to_a = f"{round(_info[a]['three_out']/_info[a]['drives']*100)}%" if _info[a]["drives"] else "-"
            _to_b = f"{round(_info[b]['three_out']/_info[b]['drives']*100)}%" if _info[b]["drives"] else "-"
            lines.append(f"3-and-Out %: {_to_a} - {_to_b}")
            lines.append(f"Explosive Plays (20+ Yds): {_info[a]['expl']} - {_info[b]['expl']}")
        # ============ PASSEN ============
        lines.append("")
        lines.append("--- Passen ---")
        def _pfd(sd): return _pick(sd, ["passingfirstdowns", "passing 1st downs", "passing first downs"])
        va, vb = _both(_pfd)
        if va or vb: lines.append(f"Passing 1st Downs: {_fmt_pair(va, vb)}")
        # Net / Gross
        def _net(sd):
            v = _pick(sd, ["netpassingyards", "net passing yards", "passingyards", "passing yards"])
            return str(v) if v else ""
        def _sack_yards(sd):
            v = _pick(sd, ['sacks', 'sack'])
            _, y = _split_pair(v) if v else (None, None)
            if y is not None: return y
            # Fallback: separate Sack-Yards-Stat (ESPN liefert Sacks mal als '3', mal als '3-25')
            y2 = _pick(sd, ['sackyards', 'sack yards', 'sacksyardslost', 'yardslost'])
            try: return int(float(str(y2).strip())) if y2 else 0
            except: return 0
        def _sack_count(sd):
            v = _pick(sd, ['sacks', 'sack'])
            x, _ = _split_pair(v) if v else (None, None)
            return x or 0
        # V160-KORREKTUR: ESPN 'Sacks' = KASSIERTE Sacks (eigene O-Line)! Covers: PIT 3-25, CIN 1-3 -> Gross = Net + EIGENE Sack-Yards!
        # V159 hatte versehentlich Gegner-Sacks genommen -> Gross 125-426 war FALSCH, richtig ist 145-409!
        va_n, vb_n = _both(_net)
        try:
            _na = _num(va_n); _nb = _num(vb_n)
            va_g = str(int(_na + _sack_yards(sa))) if _na is not None else ''
            vb_g = str(int(_nb + _sack_yards(sb))) if _nb is not None else ''
        except:
            va_g, vb_g = '', ''
        if va_n or vb_n: lines.append(f'Net Passing Yards: {_fmt_pair(va_n, vb_n)}')
        if va_g or vb_g: lines.append(f'Gross Passing Yards: {_fmt_pair(va_g, vb_g)}')
        def _ptd(sd):
            v = _pick(sd, ['passing touchdowns', 'passingtouchdowns', 'passing td'])
            if v and _int(v) is not None: return str(_int(v))
            _nm = a if sd is sa else b
            _c = _td_counts.get(_nm, {})
            if _c.get('total'): return str(_c.get('pass', 0))
            return ''
        va, vb = _both(_ptd)
        if va or vb: lines.append(f"Touchdowns durch Pässe: {_fmt_pair(va, vb)}")
        def _int_thrown(sd):
            v = _pick(sd, ["interceptionsthrown", "interceptions thrown", "passinginterceptions", "interceptions"])
            return str(_int(v)) if v and _int(v) is not None else ""
        va, vb = _both(_int_thrown)
        if va or vb: lines.append(f"Geworfene Interceptions: {_fmt_pair(va, vb)}")
        # Yards pro Versuch = Net / Attempts - V167: EIGENE Sacks NICHT in Nenner, sonst 3.6 statt 3.8! Verifiziert: 120/32=3.8, 406/44=9.2
        def _att_from_ca(sd):
            v = _pick(sd, ['comp/att', 'completions/attempts', 'compatt'])
            if v and '/' in str(v):
                try: return float(str(v).split('/')[-1].strip())
                except: pass
            for _k in ('passingattempts', 'passattempts', 'passing attempts', 'pass attempts'):
                _v = _pick(sd, [_k])
                if _v:
                    try: return float(str(_v).strip().split('/')[-1].strip())
                    except: pass
            return None
        def _ypa_pair():
            out = []
            for _sd in (sa, sb):
                n = _num(_net(_sd))
                att = _att_from_ca(_sd)
                if n is None or att is None or att <= 0: out.append('')
                else: out.append(f'{n/att:.1f}')
            return out[0], out[1]
        va, vb = _ypa_pair()
        if va or vb: lines.append(f'Durchschn. Passing Yards pro Versuch: {_fmt_pair(va, vb)}')
        def _ca2(sd):
            v = _pick(sd, ["comp/att", "completions/attempts", "compatt"])
            if v and "/" in str(v): return str(v).strip()
            c = _pick(sd, ["completions", "passingcompletions"])
            at = None
            for _k in ("passingattempts", "passing attempts"):
                _v = _pick(sd, [_k])
                if _v: at = str(_v).strip().split("/")[-1].strip(); break
            if c and at: return f"{_int(c)}/{_int(at)}"
            return ""
        va, vb = _both(_ca2)
        if va or vb: lines.append(f"Comp/Att: {_fmt_pair(va, vb)}")
        # Sack Rate = EIGENE kassierte Sacks / (Attempts + EIGENE Sacks) - V167: ESPN Sacks = kassiert! PIT 3/(32+3)=9%, CIN 1/(44+1)=2%
        def _sackrate_pair():
            out = []
            for _sd in (sa, sb):
                sacks_allowed = _sack_count(_sd)
                att = _att_from_ca(_sd)
                if att is None or (att + sacks_allowed) <= 0: out.append('')
                else: out.append(f'{round(sacks_allowed/(att+sacks_allowed)*100)}%')
            return out[0], out[1]
        va, vb = _sackrate_pair()
        if va or vb: lines.append(f'Sack Rate: {_fmt_pair(va, vb)}')
        # ============ LAUFSPIEL ============
        lines.append("")
        lines.append("--- Laufspiel ---")
        def _ratt(sd): return _pick(sd, ["rushingattempts", "rushing attempts", "rush attempts"])
        va, vb = _both(_ratt)
        if va or vb: lines.append(f"Rushing-Versuche: {_fmt_pair(va, vb)}")
        def _ry(sd): return _pick(sd, ["rushingyards", "rushing yards", "rush yards"])
        va, vb = _both(_ry)
        if va or vb: lines.append(f"Yards Laufspiel: {_fmt_pair(va, vb)}")
        def _ypc(sd):
            y = _num(_ry(sd)); at = _num(_ratt(sd))
            if y is None or not at: return ""
            return f"{y/at:.1f}"
        va, vb = _both(_ypc)
        if va or vb: lines.append(f"Durchschn. Rushing Yards pro Versuch: {_fmt_pair(va, vb)}")
        def _rfd(sd): return _pick(sd, ["rushingfirstdowns", "rushing 1st downs", "rushing first downs"])
        va, vb = _both(_rfd)
        if va or vb: lines.append(f"Rushing 1st Downs: {_fmt_pair(va, vb)}")
        def _rtd(sd):
            v = _pick(sd, ['rushing touchdowns', 'rushingtouchdowns'])
            if v and _int(v) is not None: return str(_int(v))
            _nm = a if sd is sa else b
            _c = _td_counts.get(_nm, {})
            if _c.get('total'): return str(_c.get('rush', 0))
            return ''
        va, vb = _both(_rtd)
        if va or vb: lines.append(f"Touchdowns durch Lauf: {_fmt_pair(va, vb)}")
        # ============ ANDERE ============
        lines.append("")
        lines.append("--- Andere ---")
        # V159: Strafen: '4-46' -> Count 4 / Yards 46. Wenn nur Count da, Yards aus penaltyYards holen! So passt es zu Final Stats!
        def _pen_n(sd):
            v = _pick(sd, ['penalties', 'penalty'])
            x, _ = _split_pair(v) if v else (None, None)
            return str(x) if x is not None else ''
        def _pen_y(sd):
            v = _pick(sd, ['penalties', 'penalty'])
            _, y = _split_pair(v) if v else (None, None)
            if y is not None: return str(y)
            y2 = _pick(sd, ['penaltyyards', 'penalty yards'])
            return str(y2) if y2 else ''
        va, vb = _both(_pen_n)
        if va or vb: lines.append(f'Strafen: {_fmt_pair(va, vb)}')
        va, vb = _both(_pen_y)
        if va or vb: lines.append(f'Penalty Yards: {_fmt_pair(va, vb)}')
        def _fum(sd): return _pick(sd, ["fumbles", "totalfumbles", "total fumbles"])
        va, vb = _both(_fum)
        if va or vb: lines.append(f"Anzahl der Fumbles: {_fmt_pair(va, vb)}")
        def _fum_lost(sd):
            v = _pick(sd, ["fumbleslost", "fumbles lost", "lost fumbles"])
            return str(_int(v)) if v and _int(v) is not None else ""
        va, vb = _both(_fum_lost)
        if va or vb: lines.append(f"Verlorene Fumbles: {_fmt_pair(va, vb)}")
        if len(lines) <= 3: return ""
        lines.append("")
        lines.append("Quelle: ESPN Play-by-Play + Boxscore - NFL / NCAAF - Nach dem Spiel am genauesten!")
        return "\n".join(lines)
    except Exception:
        return ""
def get_live_stats_text(eid, lg):
    # V147: Live-Stats = gleiche ESPN Summary wie Final Stats, aber mit Live-Header + Quarter/Clock!
    # ESPN liefert Boxscore auch während dem Spiel (nach Drive, 1-3 Min Delay) - wenn leer, "" zurück!
    try:
        _txt=get_final_stats_text(eid, lg)
        if not _txt: return ""
        # Header umbenennen: Final -> Live, + Clock aus Scoreboard wenn möglich
        _txt=_txt.replace("📊 Final Stats:", "📊 Live-Stats:")
        return _txt
    except Exception:
        return ""


def _pick_norm_global(sd, keys):
    # V201: Normalisierte Suche - ESPN-Feldnamen variieren (shotsOnGoal vs shots)!
    def _n2(s): return str(s).lower().replace(' ', '').replace('_', '').replace('-', '').replace('/', '')
    flat = {_n2(kk): vv for kk, vv in (sd or {}).items()}
    for _k in keys:
        _nk = _n2(_k)
        if _nk in flat and str(flat[_nk]).strip() not in ('', '-', 'None'): return str(flat[_nk]).strip()
    for _k in keys:
        _nk = _n2(_k)
        for _kk, _vv in flat.items():
            if _nk and _nk in _kk and len(_kk) >= len(_nk) and str(_vv).strip() not in ('', '-', 'None'): return str(_vv).strip()
    return ''

def _expert_generic(eid, lg):
    # V201: Experten-Stats fuer NHL / NBA / MLB - gleiche Struktur wie NFL, Gruppen pro Liga, alles aus ESPN Boxscore!
    try:
        key = LEAGUES[lg]["espn"]
        sport = 'hockey' if lg=='NHL' else 'basketball' if lg=='NBA' else 'baseball'
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{key}/summary"
        r = requests.get(url, params={"event": eid}, timeout=12)
        data = r.json()
        hdr = data.get("header", {}) or {}
        comps = hdr.get("competitions", []) or []
        comp = comps[0] if comps else {}
        competitors = comp.get("competitors", []) or []
        box = data.get("boxscore", {}) or {}
        teams_bs = box.get("teams", []) or []
        stats_by_team = {}; names = []; abbrs = {}
        for tm in teams_bs:
            _team = tm.get("team", {}) or {}
            _nm = _team.get("shortDisplayName", "") or _team.get("displayName", "") or ""
            _abbr = _team.get("abbreviation", "") or ""
            _sd = {}
            for _st in tm.get("statistics", []) or []:
                _lbl = _st.get("displayValue", "") or _st.get("label", "") or ""
                _name = _st.get("name", "") or _st.get("label", "") or ""
                if _name: _sd[_name.lower()] = _lbl
                if _lbl: _sd[(_st.get("label","") or "").lower()] = _lbl
            stats_by_team[_nm] = _sd; names.append(_nm); abbrs[_nm] = _abbr
        if len(names) < 2: return ""
        a, b = names[0], names[1]
        sa, sb = stats_by_team.get(a, {}), stats_by_team.get(b, {})
        def _score_for(nm):
            for c in competitors:
                _t = c.get("team", {}) or {}
                _n = _t.get("shortDisplayName","") or _t.get("displayName","")
                if _n == nm or nm in _n or _n in nm: return c.get("score","")
            return ""
        sca, scb = _score_for(a), _score_for(b)
        lines = [f"\U0001f9e0 Experten-Stats: {a} {sca} @ {b} {scb}", f"{abbrs.get(a,'') or a} - {abbrs.get(b,'') or b}"]
        def _fmt(va, vb): return f"{va or '-'} - {vb or '-'}"
        def _group(title, items):
            _gl = []
            for _keys, _lbl in items:
                va = _pick_norm_global(sa, _keys); vb = _pick_norm_global(sb, _keys)
                if va or vb: _gl.append(f"{_lbl}: {_fmt(va, vb)}")
            if _gl:
                lines.append(""); lines.append(f"--- {title} ---"); lines.extend(_gl)
        if lg == "NHL":
            _group("Schüsse / Angriff", [(["shotsongoal","shots","shots on goal"],"Shots on Goal"), (["hits"],"Hits"), (["blockedshots","blocked shots"],"Blocked Shots")])
            _group("Überzahl / Disziplin", [(["powerplaygoals","power play goals"],"PP Tore"), (["powerplayopportunities","power play opportunities"],"PP Chancen"), (["penaltyminutes","penalty minutes"],"Strafminuten"), (["penalties","penalty"],"Strafen")])
            _group("Zweikampf", [(["faceoffwinpct","faceoffs won","faceoffswon","faceoffs"],"Faceoffs"), (["giveaways"],"Giveaways"), (["takeaways"],"Takeaways")])
        elif lg == "NBA":
            # V201: Punkte-Zeile RAUS! ESPN liefert da falsche Werte (35-19 statt 98-126)! Endstand steht schon im Titel!
            _group("Wurf", [(["fieldgoalpct","field goal pct"],"FG%"), (["threepointfieldgoalpct","three point pct"],"3PT%"), (["freethrowpct","free throw pct"],"FT%")])
            _group("Rebounds / Ball", [(["rebounds"],"Rebounds"), (["offensiverebounds","offensive rebounds"],"Off. Rebounds"), (["defensiverebounds","defensive rebounds"],"Def. Rebounds"), (["assists"],"Assists"), (["turnovers"],"Turnovers")])
            _group("Defense", [(["steals"],"Steals"), (["blocks"],"Blocks"), (["fouls","personal fouls"],"Fouls")])
        elif lg == "MLB":
            _group("Schlagen", [(["hits"],"Hits"), (["homeruns","home runs"],"Home Runs"), (["runsbattedin","rbi"],"RBI"), (["runs"],"Runs"), (["stolenbases","stolen bases"],"Stolen Bases")])
            _group("Werfen", [(["strikeouts"],"Strikeouts"), (["walks","base on balls"],"Walks"), (["earnedruns","earned runs"],"Earned Runs")])
            _group("Feld", [(["errors"],"Errors"), (["leftonbase","left on base"],"Left on Base"), (["doubleplays","double plays"],"Double Plays")])
        if len(lines) <= 2: return ""
        lines.append(""); lines.append("Quelle: ESPN Boxscore!")
        return "\n".join(lines)
    except Exception:
        return ""

def get_final_stats_text(eid, lg):
    try:
        key = LEAGUES[lg]["espn"]
        sport = 'hockey' if lg=='NHL' else 'basketball' if lg in ('NBA',) else 'football' if lg in ('NFL','NCAAF') else 'baseball'
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{key}/summary"
        r = requests.get(url, params={"event": eid}, timeout=12)
        data = r.json()
        hdr = data.get("header", {}) or {}
        comps = hdr.get("competitions", []) or []
        comp = comps[0] if comps else {}
        competitors = comp.get("competitors", []) or []
        box = data.get("boxscore", {}) or {}
        teams_bs = box.get("teams", []) or []
        stats_by_team = {}
        names = []
        abbrs = {}
        for tm in teams_bs:
            _team = tm.get("team", {}) or {}
            _nm = _team.get("shortDisplayName", "") or _team.get("displayName", "") or ""
            _abbr = _team.get("abbreviation","") or ""
            _sd = {}
            for _st in tm.get("statistics", []) or []:
                _lbl = _st.get("displayValue", "") or _st.get("label", "") or ""
                _name = _st.get("name", "") or _st.get("label", "") or ""
                if _name: _sd[_name.lower()] = _lbl
                if _lbl: _sd[(_st.get("label","") or "").lower()] = _lbl
            stats_by_team[_nm] = _sd
            names.append(_nm)
            abbrs[_nm]=_abbr
        if len(names) < 2 or not stats_by_team:
            return ""
        a, b = names[0], names[1]
        sa, sb = stats_by_team.get(a, {}), stats_by_team.get(b, {})
        def _score_for(nm):
            for c in competitors:
                _t = c.get("team", {}) or {}
                _n = _t.get("shortDisplayName","") or _t.get("displayName","")
                if _n == nm or nm in _n or _n in nm:
                    return c.get("score","")
            return ""
        # Abkürzungen aus competitors falls boxscore keine hat
        for c in competitors:
            _t=c.get("team",{}) or {}
            _n=_t.get("shortDisplayName","") or _t.get("displayName","")
            if _n in abbrs and not abbrs[_n]: abbrs[_n]=_t.get("abbreviation","") or ""
        sca, scb = _score_for(a), _score_for(b)
        _ab_a = abbrs.get(a,"") or a
        _ab_b = abbrs.get(b,"") or b
        lines = [f"📊 Final Stats: {a} {sca} @ {b} {scb}" if sca!="" else f"📊 Final Stats: {a} @ {b}", f"{_ab_a} - {_ab_b}"]
        def _pick(sd, keys):
            for _k in keys:
                for _kk, _vv in sd.items():
                    if _k.lower() in _kk.lower() or _kk.lower() in _k.lower():
                        if _vv not in ("", "-"): return _vv
                if sd.get(_k.lower()): return sd.get(_k.lower())
            return ""
        if lg in ("NFL","NCAAF"):
            # V134: Maximum + deine Version! Sacks nur Anzahl, Rest so lassen!
            _raw_picks = [(["firstDowns","first downs","1st downs"],"First Downs"),(["totalYards","total yards","totyards"],"Yards"),(["passingYards","passing","pass"],"Pass"),(["rushingYards","rushing","rush"],"Rush"),(["turnovers","turnover"],"Turnovers"),(["sacks","sack"],"Sacks"),(["thirdDown","3rd down","third down"],"3rd Down"),(["fourthDown","4th down","fourth down"],"4th Down"),(["penalties","penalty"],"Strafen"),(["possessionTime","possession","time of possession","ballbesitz"],"Ballbesitz")]
            _sacks_missing=False
            for _keys,_lbl in _raw_picks:
                va = _pick(sa, _keys); vb = _pick(sb, _keys)
                if _lbl=="Sacks":
                    # "5-39" -> nur "5"! Yards interessieren nicht!
                    def _only_count(v):
                        try:
                            s=str(v).strip()
                            if "-" in s: return s.split("-")[0].strip()
                            return s
                        except: return v
                    if not va and not vb: _sacks_missing=True
                    va=_only_count(va) if va else va; vb=_only_count(vb) if vb else vb
                if _lbl=="Strafen":
                    # V167: EXAKT wie Experte! Loose _pick kann falsche Penalties finden (z.B. penaltyYards zuerst) -> Final 3-1 vs Experte 4-8!
                    # Darum: Hybrid-Exact wie in get_expert_stats_text, Count + Yards aus "penalties" (z.B. "4-46"), sonst aus penaltyYards!
                    def _hybrid_pen(_sd):
                        _flat = {str(k).lower().replace(" ", "").replace("_", "").replace("-", ""): v for k, v in (_sd or {}).items()}
                        _v = _flat.get("penalties", "") or _flat.get("penalty", "") or ""
                        _s = str(_v or "").strip()
                        if not _s: return ""
                        if "/" in _s or "-" in _s:
                            return _v135_slash(_s)
                        _y = _flat.get("penaltyyards", "") or _flat.get("penaltyyard", "") or ""
                        if _y and str(_y).strip() not in ("", "-"):
                            return f"{_s}/{str(_y).strip()}"
                        return _s
                    va = _hybrid_pen(sa); vb = _hybrid_pen(sb)
                elif _lbl in ("3rd Down","4th Down"):
                    va=_v135_slash(va) if va else va; vb=_v135_slash(vb) if vb else vb
                if va or vb: lines.append(f"{_lbl}: {va or '-'} - {vb or '-'}")
                elif _lbl=="Sacks":
                    lines.append("Sacks: - - -")
            try:
                if not any(l.startswith("Pass:") for l in lines):
                    _y_a = _pick(sa, ["totalYards","total yards"]); _r_a = _pick(sa, ["rushingYards","rushing","rush"])
                    _y_b = _pick(sb, ["totalYards","total yards"]); _r_b = _pick(sb, ["rushingYards","rushing","rush"])
                    if _y_a and _r_a and _y_b and _r_b:
                        lines.insert(3, f"Pass: {int(float(str(_y_a).replace(',','')))-int(float(str(_r_a).replace(',','')))} - {int(float(str(_y_b).replace(',','')))-int(float(str(_r_b).replace(',','')))}")
            except: pass
            # Top Performer aus boxscore players (wenn ESPN sie schon hat!)
            try:
                _leaders=[]
                _players = box.get("players", []) or []
                for _pg in _players:
                    _tm2=(_pg.get("team",{}) or {}).get("shortDisplayName","") or ""
                    for _cat in (_pg.get("statistics",[]) or []):
                        _catname=str(_cat.get("name","") or "").lower()
                        _ath=(_cat.get("athletes",[]) or [])
                        if not _ath: continue
                        _a0=_ath[0] or {}
                        _an=(_a0.get("athlete",{}) or {}).get("displayName","") or ""
                        _stats=_a0.get("stats",[]) or []
                        _sd2={}
                        for _s in _stats:
                            if isinstance(_s,dict): _sd2[str(_s.get("name","") or "").lower()]=_s.get("displayValue","")
                            elif isinstance(_s,str): _sd2[_s.lower()]=_s
                        _py=_v135_stat_value(_sd2,["passingyards","passingYards","passyards"])
                        _ptd=_v135_stat_value(_sd2,["passingtouchdowns","passingTD"])
                        _ry=_v135_stat_value(_sd2,["rushingyards","rushingYards","rushyards"])
                        _rtd=_v135_stat_value(_sd2,["rushingtouchdowns","rushingTD"])
                        _cy=_v135_stat_value(_sd2,["receivingyards","receivingYards"])
                        if "pass" in _catname and _an and _py:
                            _leaders.append(f"Pass: {_an} {_py} Yds" + (f", {_ptd} TD" if _ptd else ""))
                        elif "rush" in _catname and _an and _ry:
                            _leaders.append(f"Rush: {_an} {_ry} Yds" + (f", {_rtd} TD" if _rtd else ""))
                        elif "receiv" in _catname and _an and _cy:
                            _leaders.append(f"Catch: {_an} {_cy} Yds")
                _leaders=[x for x in _leaders if x and " Yds" in x][:3]
                if _leaders:
                    lines.append("")
                    lines.append("⭐ Top Performer:")
                    lines.extend(_leaders)
            except: pass
            if _sacks_missing:
                lines.append("")
                lines.append("ℹ️ Sacks: Noch nicht von ESPN geliefert.")
        elif lg == "NBA":
            for _k,_lbl in [("rebounds","Rebounds"),("assists","Assists"),("steals","Steals"),("blocks","Blocks"),("turnovers","Turnovers"),("fieldGoalPct","FG%"),("threePointFieldGoalPct","3PT%")]:
                va = sa.get(_k.lower(),"") or sa.get(_lbl.lower(),"")
                vb = sb.get(_k.lower(),"") or sb.get(_lbl.lower(),"")
                if _lbl=="Strafen":
                    # V159: Strafen als Count/Yards (4/46) - wenn nur Count da, Yards aus penaltyYards holen, damit Final Stats = Experten-Stats!
                    def _combine_pen(_v, _sd):
                        try:
                            _s = str(_v or '').strip()
                            if not _s: return _s
                            if '/' in _s or '-' in _s: return _v135_slash(_s)
                            # V167: penaltyYards per EXAKTEM Match suchen (loose _pick findet 'penaltyYards' sonst nicht, wenn Key 'penaltyyards' ist!)
                            _flat = {str(k).lower().replace(' ', '').replace('_', ''): v for k, v in (_sd or {}).items()}
                            _y = _flat.get('penaltyyards', '') or _flat.get('penaltyyard', '') or ''
                            if not _y: _y = _pick(_sd, ['penaltyYards', 'penalty yards'])
                            if _y and str(_y).strip() not in ('', '-'):
                                return f'{_s}/{str(_y).strip()}'
                            return _s
                        except: return _v
                    va = _combine_pen(va, sa); vb = _combine_pen(vb, sb)
                elif _lbl in ("3rd Down","4th Down"):
                    va=_v135_slash(va) if va else va; vb=_v135_slash(vb) if vb else vb
                if va or vb: lines.append(f"{_lbl}: {va or '-'} - {vb or '-'}")
                elif _lbl=="Sacks":
                    lines.append("Sacks: - - -")
        elif lg == "NHL":
            # V201: Robuste Picks (ESPN-Feldnamen variieren!) + mehr Werte! Vorher kamen nur Hits + PP an!
            for _keys,_lbl in [(["shotsongoal","shots","shots on goal"],"Schüsse"),(["hits"],"Hits"),(["faceoffwinpct","faceoffs won","faceoffswon","faceoffs"],"Faceoffs"),(["powerplaygoals","power play goals"],"PP Tore"),(["powerplayopportunities","power play opportunities"],"PP Chancen"),(["penaltyminutes","penalty minutes"],"Strafminuten"),(["blockedshots","blocked shots"],"Blocked Shots"),(["giveaways"],"Giveaways"),(["takeaways"],"Takeaways")]:
                va = _pick_norm_global(sa, _keys)
                vb = _pick_norm_global(sb, _keys)
                if _lbl=="Strafen":
                    # V159: Strafen als Count/Yards (4/46) - wenn nur Count da, Yards aus penaltyYards holen, damit Final Stats = Experten-Stats!
                    def _combine_pen(_v, _sd):
                        try:
                            _s = str(_v or '').strip()
                            if not _s: return _s
                            if '/' in _s or '-' in _s: return _v135_slash(_s)
                            # V167: penaltyYards per EXAKTEM Match suchen (loose _pick findet 'penaltyYards' sonst nicht, wenn Key 'penaltyyards' ist!)
                            _flat = {str(k).lower().replace(' ', '').replace('_', ''): v for k, v in (_sd or {}).items()}
                            _y = _flat.get('penaltyyards', '') or _flat.get('penaltyyard', '') or ''
                            if not _y: _y = _pick(_sd, ['penaltyYards', 'penalty yards'])
                            if _y and str(_y).strip() not in ('', '-'):
                                return f'{_s}/{str(_y).strip()}'
                            return _s
                        except: return _v
                    va = _combine_pen(va, sa); vb = _combine_pen(vb, sb)
                elif _lbl in ("3rd Down","4th Down"):
                    va=_v135_slash(va) if va else va; vb=_v135_slash(vb) if vb else vb
                if va or vb: lines.append(f"{_lbl}: {va or '-'} - {vb or '-'}")
                elif _lbl=="Sacks":
                    lines.append("Sacks: - - -")
        elif lg == "MLB":
            for _k,_lbl in [("hits","Hits"),("homeRuns","HR"),("RBIs","RBI"),("errors","Errors"),("strikeouts","Strikeouts"),("walks","Walks")]:
                va = sa.get(_k.lower(),"") or sa.get(_lbl.lower(),"")
                vb = sb.get(_k.lower(),"") or sb.get(_lbl.lower(),"")
                if _lbl=="Strafen":
                    # V159: Strafen als Count/Yards (4/46) - wenn nur Count da, Yards aus penaltyYards holen, damit Final Stats = Experten-Stats!
                    def _combine_pen(_v, _sd):
                        try:
                            _s = str(_v or '').strip()
                            if not _s: return _s
                            if '/' in _s or '-' in _s: return _v135_slash(_s)
                            # V167: penaltyYards per EXAKTEM Match suchen (loose _pick findet 'penaltyYards' sonst nicht, wenn Key 'penaltyyards' ist!)
                            _flat = {str(k).lower().replace(' ', '').replace('_', ''): v for k, v in (_sd or {}).items()}
                            _y = _flat.get('penaltyyards', '') or _flat.get('penaltyyard', '') or ''
                            if not _y: _y = _pick(_sd, ['penaltyYards', 'penalty yards'])
                            if _y and str(_y).strip() not in ('', '-'):
                                return f'{_s}/{str(_y).strip()}'
                            return _s
                        except: return _v
                    va = _combine_pen(va, sa); vb = _combine_pen(vb, sb)
                elif _lbl in ("3rd Down","4th Down"):
                    va=_v135_slash(va) if va else va; vb=_v135_slash(vb) if vb else vb
                if va or vb: lines.append(f"{_lbl}: {va or '-'} - {vb or '-'}")
                elif _lbl=="Sacks":
                    lines.append("Sacks: - - -")
        if len(lines) <= 2:
            return ""
        return "\n".join(lines)
    except Exception as e:
        return ""
async def finalstats_retry_job(context):
    # V106: Nach 5 Min nochmal Stats holen!
    try:
        d = context.job.data or {}
        uid = int(d.get("uid",0)); eid = str(d.get("eid","")); lg = d.get("lg",""); mid = int(d.get("mid",0))
        if not uid or not eid or not lg: return
        _txt = get_final_stats_text(eid, lg) if lg in LEAGUES else ""
        if _txt:
            try: await context.bot.delete_message(chat_id=uid, message_id=mid)
            except: pass
            _rows_retry = []
            if lg in LEAGUES:
                _rows_retry.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{eid}:{lg}")])
            _rows_retry.extend(_yt_buttons_for_game(eid, lg, _txt))
            _fs_del_kb2 = InlineKeyboardMarkup(_rows_retry)
            await context.bot.send_message(chat_id=uid, text=_txt, reply_markup=_fs_del_kb2)
        else:
            _kb3 = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, nochmal schauen!", callback_data=f"finalstats_retry:{eid}:{lg}"), InlineKeyboardButton("❌ Nein, danke!", callback_data=f"finalstats_no:{eid}:{lg}")]])
            try: await context.bot.edit_message_text(chat_id=uid, message_id=mid, text="😅 Immer noch keine Stats!\nESPN ist noch langsam!\nNochmal in 5 Min schauen?", reply_markup=_kb3)
            except: pass
    except: pass


# V109: One-Off Live für Nicht-Favoriten-Spiele (z.B. München Spiel)!
def _oneoff_cfg(uid):
    try:
        s = load_settings(); return s.get(str(uid), {}).get("oneoff_live", {}) or {}
    except: return {}
def get_oneoff_live(uid, eid):
    d = _oneoff_cfg(uid).get(str(eid), {}) or {}
    return {"score": bool(d.get("score", False)), "period": bool(d.get("period", False)), "final": bool(d.get("final", False)), "crunch": bool(d.get("crunch", False)), "start": bool(d.get("start", False)), "breaking": bool(d.get("breaking", False)), "reminder": bool(d.get("reminder", False)), "lg": d.get("lg",""), "name": d.get("name","")}
def set_oneoff_live_toggle(uid, eid, kind):
    s = load_settings(); s.setdefault(str(uid), {}); s[str(uid)].setdefault("oneoff_live", {}).setdefault(str(eid), {})
    cur = bool(s[str(uid)]["oneoff_live"][str(eid)].get(kind, False))
    s[str(uid)]["oneoff_live"][str(eid)][kind] = not cur
    save_settings(s)
    return not cur

async def next_live_league_cmd(update, ctx):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏈 NFL", callback_data="next_live_list:NFL"), InlineKeyboardButton("🏒 NHL", callback_data="next_live_list:NHL")],
        [InlineKeyboardButton("⚾ MLB", callback_data="next_live_list:MLB"), InlineKeyboardButton("🏀 NBA", callback_data="next_live_list:NBA")],
        [InlineKeyboardButton("🎓 NCAAF", callback_data="next_live_list:NCAAF")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "🔴 Live für ein Spiel\n\nWelche Liga?\nDanach wählst du das Spiel und stellst ein wie bei Favoriten: Score / Perioden-Ende / Endstand / Crunch-Time!", kb)

async def next_live_list_cmd(update, ctx, league):
    # Heute + Morgen Spiele für Liga, nummeriert mit Buttons
    from datetime import date as _date
    today = _date.today()
    evs = []
    seen = set()
    for offset in (-1,0,1):  # V204: -1 dazu! Nach Mitternacht DE-Zeit liegen die 00:00-03:00-Spiele auf dem US-Gestern-Slate!
        d = today + timedelta(days=offset)
        ds = d.strftime("%Y%m%d")
        for ev in espn_scoreboard(league, dates=ds):
            eid = str(ev.get("id",""))
            if eid in seen: continue
            seen.add(eid)
            state = ev.get("status",{}).get("type",{}).get("state","")
            if state == "post": continue
            evs.append(ev)
    evs.sort(key=lambda e: (fmt_dt(e.get("date",""))[1] or datetime.now(BERLIN)))  # V204: Nach Anpfiff sortieren - Nacht-Spiele zuerst!
    evs = evs[:12]
    if not evs:
        await _cb_edit(update, f"🔴 Live für ein Spiel - {league}\n\nHeute / Morgen keine Spiele gefunden.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]]))
        return
    lines = [f"🔴 Live für ein Spiel - {LEAGUES[league]['emoji']} {league} (Heute / Morgen)\n"]
    # V110: Keine Buttons! Nur Zahl schicken wie bei Favoriten!
    try: ctx.user_data["next_live_list"] = [(league, str(ev.get("id",""))) for ev in evs]
    except: pass
    try: ctx.user_data["results_list"] = None
    except: pass
    for i, ev in enumerate(evs, start=1):
        try:
            _line = game_line(ev, league)
            lines.append(f"{i}. {_line}")
        except: continue
    lines.append("\n🔴 Einfach die Zahl schicken! z.B. 1 für Spiel 1")
    rows = [[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]]
    await _cb_edit(update, "\n".join(lines), InlineKeyboardMarkup(rows))

# V235: Wetter via Open-Meteo (gratis, ohne Key)! ESPN liefert kein Wetter - also ueber den Stadion-Ort! Gibt (wetter_zeile, stadion_tz) zurueck!
_WETTER235 = {0:"Klar", 1:"Überwiegend klar", 2:"Wechselhaft", 3:"Bedeckt", 45:"Nebel", 48:"Nebel mit Reif", 51:"Leichter Nieselregen", 53:"Nieselregen", 55:"Starker Nieselregen", 56:"Gefrierender Nieselregen", 57:"Gefrierender Nieselregen", 61:"Leichter Regen", 63:"Regen", 65:"Starker Regen", 66:"Gefrierender Regen", 67:"Gefrierender Regen", 71:"Leichter Schnee", 73:"Schnee", 75:"Starker Schnee", 77:"Schneekörner", 80:"Leichte Regenschauer", 81:"Regenschauer", 82:"Starke Regenschauer", 85:"Schneeschauer", 86:"Schneeschauer", 95:"Gewitter", 96:"Gewitter mit Hagel", 99:"Gewitter mit starkem Hagel"}
_WETTER_DEBUG238 = ""  # V238: Debug-Grund, warum Wetter nicht klappt (nur bis der Bug gefunden ist, dann fliegt die Zeile wieder raus)!
_WTTR239 = {"clear": "Klar", "sunny": "Sonnig", "partly cloudy": "Wechselhaft", "cloudy": "Bedeckt", "overcast": "Bedeckt", "mist": "Nebel", "fog": "Nebel", "light rain": "Leichter Regen", "moderate rain": "Regen", "heavy rain": "Starker Regen", "light snow": "Leichter Schnee", "moderate snow": "Schnee", "heavy snow": "Starker Schnee", "thunderstorm": "Gewitter", "thundery outbreaks possible": "Gewitter möglich", "patchy rain possible": "Regen möglich", "patchy snow possible": "Schnee möglich", "light drizzle": "Leichter Nieselregen", "drizzle": "Nieselregen", "freezing fog": "Nebel mit Reif", "blizzard": "Schneesturm", "blowing snow": "Schneetreiben"}  # V239: wttr.in sagt Wetter auf Englisch -> hier auf Deutsch!
def _game_weather235(city, dt_kickoff, state):
    # V239: ZWEITE Quelle als Fallback (wttr.in)! Open-Meteo liefert "Forecast leer" (Geo geht, Forecast kommt ohne Daten zurueck) - statt weiter zu raten, einfach zweite Quelle nehmen! + Explizite Stadion-Zeitzone statt auto!
    global _WETTER_DEBUG238
    _WETTER_DEBUG238 = ""
    _HDR238 = {"User-Agent": "Mozilla/5.0"}
    _om_reason = ""
    try:
        try:
            if getattr(dt_kickoff, "tzinfo", None) is None:
                dt_kickoff = dt_kickoff.replace(tzinfo=BERLIN)
        except: pass
        res = None
        for _q237 in (city, f"{city}, USA"):
            try:
                g = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": _q237, "count": 1, "language": "de", "format": "json"}, timeout=8, headers=_HDR238).json()
                res = (g.get("results") or [None])[0]
                if res: break
            except: continue
        if not res:
            _WETTER_DEBUG238 = "Geo leer"
            print(f"[WETTER] Geo nix gefunden: {city}")
            return "", None
        lat, lon = res.get("latitude"), res.get("longitude")
        tzname = res.get("timezone") or "America/New_York"
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tzname)
        except: tz = None
        if lat is None or lon is None: return "", tz
        temp = code = None
        # --- Quelle 1: Open-Meteo (V239: explizite Zeitzone statt auto!) ---
        try:
            if state == "in":
                f = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code", "timezone": tzname}, timeout=8, headers=_HDR238).json()
                cur = f.get("current") or {}
                temp, code = cur.get("temperature_2m"), cur.get("weather_code")
                _om_reason = str(f.get("reason") or "")[:60]
            else:
                f = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "hourly": "temperature_2m,weather_code", "current": "temperature_2m,weather_code", "timezone": tzname, "forecast_days": 3}, timeout=8, headers=_HDR238).json()
                _om_reason = str(f.get("reason") or "")[:60]
                off = f.get("utc_offset_seconds", 0) or 0
                from datetime import timezone as _tzmod235
                ko_local = dt_kickoff.astimezone(_tzmod235.utc) + timedelta(seconds=off)
                want = ko_local.strftime("%Y-%m-%dT%H:00")
                hours = ((f.get("hourly") or {}).get("time") or [])
                temps = ((f.get("hourly") or {}).get("temperature_2m") or [])
                codes = ((f.get("hourly") or {}).get("weather_code") or [])
                if want in hours:
                    idx = hours.index(want); temp, code = temps[idx], codes[idx]
                elif hours and len(temps) == len(hours) and len(codes) == len(hours):
                    try:
                        from datetime import datetime as _dt237
                        best = min(range(len(hours)), key=lambda i: abs((_dt237.strptime(hours[i], "%Y-%m-%dT%H:%M") - ko_local.replace(tzinfo=None)).total_seconds()))
                        temp, code = temps[best], codes[best]
                    except: pass
                if temp is None:
                    cur = f.get("current") or {}
                    temp, code = cur.get("temperature_2m"), cur.get("weather_code")
        except Exception as _e239:
            _om_reason = f"Abruf-Fehler: {str(_e239)[:50]}"
        if temp is not None and code is not None:
            fahr = round(float(temp) * 9/5 + 32)
            cond = _WETTER235.get(int(code), "Wechselhaft")
            return f"🌦️ Wetter: {cond}, {fahr}°F ({round(float(temp))}°C)", tz
        # --- Quelle 2: wttr.in (V239: falls Open-Meteo leer ist!) ---
        _wt_reason = ""
        try:
            w = requests.get(f"https://wttr.in/{city}", params={"format": "j1"}, timeout=8, headers=_HDR238).json()
            _cc = ((w.get("current_condition") or [None])[0] or {})
            _tf, _tc = _cc.get("temp_F"), _cc.get("temp_C")
            _desc = ((_cc.get("weatherDesc") or [{}])[0] or {}).get("value") or ""
            if _tf is not None and _tc is not None:
                _cond239 = _WTTR239.get(_desc.strip().lower(), _desc or "Wechselhaft")
                return f"🌦️ Wetter: {_cond239}, {round(float(_tf))}°F ({round(float(_tc))}°C)", tz
            _wt_reason = "wttr leer"
        except Exception as _e239b:
            _wt_reason = f"wttr-Fehler: {str(_e239b)[:50]}"
        _WETTER_DEBUG238 = f"OM: {_om_reason or 'leer'} | wttr: {_wt_reason or 'leer'}"
        print(f"[WETTER] Kein Wetter fuer: {city} (state={state}) -> {_WETTER_DEBUG238}")
        return "", tz
    except Exception as _e237:
        _WETTER_DEBUG238 = f"Fehler: {str(_e237)[:60]}"
        print(f"[WETTER] Fehler: {city} -> {_e237}")
        return "", None

async def next_live_pick_cmd(update, ctx, league, eid, num_mid=None, expanded235=False):
    # Spiel-Name finden
    _name = f"Spiel {eid}"
    _det230 = ""  # V230: Echte Details (Stadion + Sender + Anpfiff)!
    _wet235 = ""  # V235: Wetter-Zeile!
    _wetdbg238 = ""  # V238: Debug-Grund, falls Wetter nicht klappt!
    _tz235 = None  # V235: Stadion-Zeitzone fuer die Ami-Kickoff-Zeit!
    _post213 = False  # V213: Spiel schon vorbei?
    try:
        from datetime import date as _date
        today = _date.today()
        for offset in (-1,0,1,2):  # V204: -1 dazu (Nacht-Spiele!)
            d = today + timedelta(days=offset)
            for ev in espn_scoreboard(league, dates=d.strftime("%Y%m%d")):
                if str(ev.get("id","")) == str(eid):
                    _teams,_ = event_teams(ev)
                    _name = game_line(ev, league)
                    try: _post213 = (ev.get("status",{}).get("type",{}).get("state","") == "post")
                    except: pass
                    # V235: Doppelte Kickoff-Zeit raus! game_line hat schon "• ⏰ 22.11. 19:00 Uhr" - und unten steht Kickoff nochmal!
                    try:
                        if (ev.get("status",{}) or {}).get("type",{}).get("state","") == "pre":
                            _name = _name.split(" • ⏰ ")[0]
                    except: pass
                    # V230: Echte Details! Sonst luegt "Details + Benachrichtigungen" - da kamen ja nur Schalter!
                    try:
                        _comp230 = ev.get("competitions", [{}])[0]
                        _ven230 = _comp230.get("venue", {}) or {}
                        _ven230_s = _ven230.get("fullName", "") or ""
                        _city230 = ((_ven230.get("address", {}) or {}).get("city", "") or "")
                        _bc230 = broadcast_line(ev) or ""
                        _, _dt230 = fmt_dt(ev.get("date", ""))
                        _parts230 = []
                        _st230 = (ev.get("status", {}) or {}).get("type", {}).get("state", "")
                        # V235: Wetter holen (NFL/NCAAF only) - liefert auch die Stadion-Zeitzone fuer die Ami-Kickoff-Zeit!
                        if league in ("NFL", "NCAAF") and _st230 in ("pre", "in") and _city230 and _dt230:
                            try: _wet235, _tz235 = _game_weather235(_city230, _dt230, _st230)
                            except: _wet235, _tz235 = "", None
                            if not _wet235: _wetdbg238 = _WETTER_DEBUG238 or "Unbekannt"  # V238: Debug-Grund merken!
                        if _st230 == "pre" and _dt230:
                            _today230 = datetime.now(BERLIN).date()
                            _day230 = "heute" if _dt230.date() == _today230 else "morgen" if _dt230.date() == (_today230 + timedelta(days=1)) else _dt230.strftime("%d.%m.")
                            # V235: Kickoff mit Ami-Zeit zuerst! "🏈 Kickoff 13:00 ET (19:00 Uhr)" - Stadion-Zeit oder ET als Fallback!
                            try:
                                from zoneinfo import ZoneInfo as _ZI235
                                try: _tz235b = _tz235 or _ZI235("America/New_York")
                                except: _tz235b = None
                                if _tz235b is None:
                                    from datetime import timezone as _tzmod235
                                    _tz235b = _tzmod235(timedelta(hours=-5))
                                _ko235 = _dt230.astimezone(_tz235b)
                                _abbr235 = _ko235.strftime("%Z") or "ET"
                                _day235 = f"{_day230} " if _day230 != "heute" else ""
                                _parts230.append(f"🏈 Kickoff {_day235}{_ko235.strftime('%H:%M')} {_abbr235} ({_dt230.strftime('%H:%M')} Uhr)")
                            except:
                                _parts230.append(f"🏈 Kickoff {_day230} {_dt230.strftime('%H:%M')} Uhr")
                        if _ven230_s: _parts230.append(f"📍 {_ven230_s}" + (f", {_city230}" if _city230 else ""))
                        if _bc230: _parts230.append(f"📺 {_bc230}")
                        # V236: Jede Info eigene Zeile! Kickoff / Ort / Sender je eigene Zeile - 2 Zeilen mehr, aber endlich uebersichtlich!
                        _det230 = "\n".join(_parts230)
                    except: _det230 = ""
                    break
    except: pass
    # V213: Spiel schon vorbei? -> Keine Schalter mehr! Nur "Spiel vorbei" + Entfernen!
    if _post213:
        _rm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Aus Liste entfernen", callback_data=f"next_live_remove:{league}:{eid}")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        _win213 = await _cb_edit(update, f"📋 Spiel-Informationen\n\n{_name}" + (f"\n{_det230}" if _det230 else "") + "\n\n🏁 Spiel schon vorbei! Da gibt's nix mehr einzustellen! 😁", _rm_kb)
        # V213: Fenster -> Zahl mappen (wie V210), damit die getippte Zahl mitgeloescht wird!
        try:
            if num_mid and _win213 is not None and getattr(_win213, "message_id", None):
                _uid213 = update.effective_user.id if update.effective_user else 0
                _CLOSE_NUM_MAP[(int(_uid213), int(_win213.message_id))] = int(num_mid)
        except: pass
        return
    # In Settings speichern (Name + Liga), damit live_job es findet!
    try:
        s = load_settings(); s.setdefault(str(update.effective_user.id), {}); s[str(update.effective_user.id)].setdefault("oneoff_live", {}).setdefault(str(eid), {})
        s[str(update.effective_user.id)]["oneoff_live"][str(eid)]["lg"] = league
        s[str(update.effective_user.id)]["oneoff_live"][str(eid)]["name"] = _name
        save_settings(s)
    except: pass
    cfg = get_oneoff_live(update.effective_user.id, eid)
    # V235: Buttons zum AUFKLAPPEN! Erst nur 1 Button - drauf tippen -> alle Schalter!
    if expanded235:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{'✅' if cfg['score'] else '❌'} Jeder Score", callback_data=f"next_live_toggle:{league}:{eid}:score")],
            [InlineKeyboardButton(f"{'✅' if cfg['period'] else '❌'} {period_toggle_label(league)}", callback_data=f"next_live_toggle:{league}:{eid}:period")],
            [InlineKeyboardButton(f"{'✅' if cfg['final'] else '❌'} Endstand", callback_data=f"next_live_toggle:{league}:{eid}:final")],
            [InlineKeyboardButton(f"{'✅' if cfg.get('crunch') else '❌'} Crunch-Time (8 Min, knapp!)", callback_data=f"next_live_toggle:{league}:{eid}:crunch")],
            [InlineKeyboardButton(f"{'✅' if cfg.get('breaking') else '❌'} 🚨 Spiel-Breaking", callback_data=f"next_live_toggle:{league}:{eid}:breaking")],
            [InlineKeyboardButton(f"{'✅' if cfg.get('reminder') else '❌'} ⏰ Reminder", callback_data=f"next_live_toggle:{league}:{eid}:reminder")],
            [InlineKeyboardButton("🔼 Einklappen", callback_data=f"next_live_collapse:{league}:{eid}")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        _hint235 = "Tippe an / aus. Nur was du anmachst, schicke ich dir!\nNach dem Spiel wird es automatisch wieder aus!"
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Benachrichtigungen einstellen", callback_data=f"next_live_expand:{league}:{eid}")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        _hint235 = "🔔 Tippe auf 'Benachrichtigungen einstellen', um zu wählen, was ich dir schicke!\nNach dem Spiel wird es automatisch wieder aus!"
    _win210 = await _cb_edit(update, f"📋 Spiel-Informationen\n\n{_name}" + (f"\n{_det230}" if _det230 else "") + (f"\n{_wet235}" if _wet235 else "") + (f"\n🌦️ Wetter: konnte nicht laden (Debug: {_wetdbg238})" if _wetdbg238 else "") + f"\n\n{_hint235}", kb)
    # V210: Fenster -> Zahl mappen! Damit 'Fenster schliessen' die getippte Zahl mitloescht!
    try:
        if num_mid and _win210 is not None and getattr(_win210, "message_id", None):
            _uid210 = update.effective_user.id if update.effective_user else 0
            _CLOSE_NUM_MAP[(int(_uid210), int(_win210.message_id))] = int(num_mid)
    except: pass

_MLB_DIV={"Yankees":"AL East","Red Sox":"AL East","Rays":"AL East","Blue Jays":"AL East","Orioles":"AL East","Guardians":"AL Central","Tigers":"AL Central","Royals":"AL Central","Twins":"AL Central","White Sox":"AL Central","Astros":"AL West","Mariners":"AL West","Rangers":"AL West","Angels":"AL West","Athletics":"AL West","Braves":"NL East","Mets":"NL East","Phillies":"NL East","Marlins":"NL East","Nationals":"NL East","Brewers":"NL Central","Cubs":"NL Central","Reds":"NL Central","Pirates":"NL Central","Cardinals":"NL Central","Dodgers":"NL West","Padres":"NL West","Giants":"NL West","Diamondbacks":"NL West","Rockies":"NL West"}
def _mlb_div_for(team_full):
    try:
        for _k,_v in _MLB_DIV.items():
            if _k.lower() in (team_full or "").lower(): return _v
    except: pass
    return ""

def _myweek_kb(_has_ncaaf):
    _rows=[[InlineKeyboardButton("⏭️ Next Games", callback_data="next"), InlineKeyboardButton("📰 News", callback_data="news")]]
    if _has_ncaaf: _rows.append([InlineKeyboardButton("🏆 CFP Top 25", callback_data="cfp_top25:NCAAF")])
    _rows.append([InlineKeyboardButton("📊 Tabellen", callback_data="tables")])
    _rows.append([InlineKeyboardButton("🔄 Aktualisieren", callback_data="myweek_refresh")])
    _rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    return InlineKeyboardMarkup(_rows)

async def myweek_cmd(update, ctx, force=False):
    # V201 CACHE: Innerhalb von 5 Min sofort aus Cache, ohne neu zu laden! Stand-Zeit steht in Zeile 1! force=True via Aktualisieren-Knopf!
    try:
        _uid_c = update.effective_user.id if update.effective_user else 0
        if not force and _uid_c in _MYWEEK_CACHE:
            _ts_c, _lines_c, _ncaaf_c = _MYWEEK_CACHE[_uid_c]
            import time as _time_c
            if _time_c.time() - _ts_c < 300:
                _mw250 = await _cb_edit(update, "\n".join(_lines_c), _myweek_kb(_ncaaf_c))
                try:
                    if _mw250 is not None and getattr(_mw250, "message_id", None): _MYWEEK_MSG[int(_uid_c)] = int(_mw250.message_id)
                except: pass
                return
    except: pass
    # V201 MEINE WOCHE: Pro Liga das, was da zählt! Nur Ligen, die man als Favorit hat! + News pro Team! + Dynamische Knöpfe!
    try: _load=await _loading_start(update.callback_query.message if update.callback_query else update.message, "⏳ Ich hole deine Woche... einen Moment")
    except: _load=None
    user=update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs=favs_for(user.id) if user else []
    if not favs:
        _mw250 = await _cb_edit(update, "📅 Meine Woche\n\nNoch keine Favoriten!\nFüg erst Teams hinzu, dann siehst du hier alles auf einen Blick!", InlineKeyboardMarkup([[InlineKeyboardButton("➕ Favorit hinzufügen", callback_data="fav_add")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]]))
        try:
            if _mw250 is not None and getattr(_mw250, "message_id", None): _MYWEEK_MSG[int(_uid_c)] = int(_mw250.message_id)
        except: pass
        return
    _EMOJI={"NFL":"🏈","NHL":"🏒","NBA":"🏀","MLB":"⚾","NCAAF":"🎓"}
    lines=[f"📅 Meine Woche - Alle deine Favoriten auf einen Blick (Stand: {datetime.now(BERLIN).strftime(chr(37)+'H'+chr(58)+chr(37)+'M')})\n"]
    _has_ncaaf=False
    try:
        _rows,_=_espn_cfp_top25()
        _rank={_d.lower():_i for _i,(_d,_s,_r) in enumerate(_rows,1)}
        _cfbd=_cfbd_records()
    except:
        _rows=[]; _rank={}; _cfbd={}
    for _f in favs:
        _flg=_f.split(" (")[-1].replace(")","").strip() if " (" in _f else ""
        _name=_f.split(" (")[0].strip()
        _em=_EMOJI.get(_flg,"⭐")
        if _flg=="NCAAF":
            _has_ncaaf=True
            _short=_cfp_short(_name, "")
            _r=None
            for _cd,_ri in _rank.items():
                if _is_fav_team(_cd, [_f], "NCAAF"): _r=_ri; break
            _ov=_cfbd_overall_for(_name, _cfbd)
            _rec=f" {_ov[0]}-{_ov[1]}" if _ov else ""
            if _r and _r<=12: lines.append(f"{_em} {_short}{_rec} - CFP #{_r} - noch drin! ✅")
            elif _r: lines.append(f"{_em} {_short}{_rec} - CFP #{_r} - noch im Rennen!")
            elif _ov and _ov[1]>=3: lines.append(f"{_em} {_short}{_rec} - raus 😔")
            else: lines.append(f"{_em} {_short}{_rec} - noch im Rennen!")
        else:
            # V201: Pro Liga Ranking aus Tabelle! _standings_row_for = (Division, Platz in Division, W, L, T, Rows)!
            _row=None
            try: _row=_standings_row_for(_flg, _name)
            except: _row=None
            if _row:
                _div,_rk,_w,_l,_tt,_rows2=_row
                # V201 FIX 3: MLB gibt ESPN nur Liga-Gruppen (National League #7)! Division + Divisions-Rang selbst rechnen!
                if _flg=="MLB":
                    try:
                        _d2=_mlb_div_for(_name)
                        if _d2:
                            _div=_d2
                            _all=espn_standings("MLB") or {}
                            for _g,_rs in _all.items():
                                if any(_mlb_div_for(_r[0])==_d2 for _r in _rs):
                                    _drows=[_r for _r in _rs if _mlb_div_for(_r[0])==_d2]
                                    _drows.sort(key=lambda _x: (_x[3]/(_x[3]+_x[4]) if (_x[3]+_x[4]) else 0, _x[3]), reverse=True)
                                    for _idx,_r in enumerate(_drows,1):
                                        if _r[0].lower() in _name.lower() or _name.lower() in _r[0].lower() or _r[1].lower() in _name.lower():
                                            _rk=_idx; break
                                    break
                    except: pass
                _rec=f" {_w}-{_l}" + (f"-{_tt}" if _tt else "")
                _extra=""
                if _flg=="NHL": _extra=f" - {2*_w+(_tt or 0)} PTS"
                # Playoff-Kurs: nur wenn Saison spät ist! Sonst kein falsches "sicher"!
                _kurs=""
                try:
                    if _playoff_mode(_flg):
                        if _rk==1: _kurs=" - Playoff-Kurs! ✅"
                        elif _rk<=3: _kurs=" - noch im Rennen!"
                        else: _kurs=" - schwer!"
                except: pass
                # MLB: Season vorbei (162 Spiele) -> kein Kurs mehr!
                if _flg=="MLB" and (_w+_l)>=162:
                    _kurs=" - Season vorbei"
                    lines.append(f"{_em} {_name}{_rec} - {_div} #{_rk}{_extra}{_kurs}")
                else:
                    lines.append(f"{_em} {_name}{_rec} - {_div} #{_rk}{_extra}{_kurs}")
            else:
                lines.append(f"{_em} {_name} ({_flg})")
        # V201: KEINE Schlagzeile mehr im Teaser! Nur Zaehler + 24h-Verweis! Grund: Google-Blog-Schlagzeilen haben Meine Woche zugemuellt! Details gibt es erst bei News!
        # Neu = wirklich letzte 24 Std.! _news_is_fresh(pub, 1)! Ohne Datum = als neu zaehlen (ESPN liefert oft kein Datum)!
        try:
            _news_all,_src2=_team_news_all(_flg, _name, limit=8) or ([], "")
            _fresh=[]
            for _a in (_news_all or []):
                try:
                    if _news_is_fresh(_a.get("published",""), 1): _fresh.append(_a)
                except: _fresh.append(_a)
            if _fresh:
                lines.append(f"   📰 {len(_fresh)} neue News (24 Std.)")
            else:
                lines.append("   📰 Keine neuen News (24 Std.)")
        except:
            lines.append("   📰 Keine neuen News (24 Std.)")
        lines.append("")
    # V201: Verweis, was 'neu' heisst! Nur 1 Zeile, kein Knopf-Wahnsinn!
    lines.append("📰 Neu = letzte 24 Std. Details bei 📰 News!")
    # CFP-Zeile NUR wenn NCAAF-Favorit da ist!
    if _has_ncaaf:
        lines.append("📅 Nächstes CFP-Ranking: Di 24.11. 19:30 ET (01:30 bei uns)\n")
    try:
        if _load: await _loading_done(ctx, user.id if user else 0, _load)
    except: pass
    # V201: KB aus Helper (mit Aktualisieren-Knopf)!
    kb=_myweek_kb(_has_ncaaf)
    # V201: Frisch gebaut -> cachen!
    try:
        import time as _time_s
        _uid_s = update.effective_user.id if update.effective_user else 0
        if _uid_s: _MYWEEK_CACHE[_uid_s]=(_time_s.time(), list(lines), _has_ncaaf)
    except: pass
    _mw250 = await _cb_edit(update, "\n".join(lines), kb)
    try:
        if _mw250 is not None and getattr(_mw250, "message_id", None): _MYWEEK_MSG[int(_uid_c)] = int(_mw250.message_id)
    except: pass

# ===== V214: TEAM-FENSTER + KEY SPIELER + DRAFT-VORSCHAU =====
# Team-Fenster: Zahl in Tabellen tippen -> Detail-Fenster mit Platz, Bilanz, Punkten/GB, Heim/Auswaerts, Streak, Last 10, naechste 3, letzte 3, News-Zaehler, Key Spieler!
# Key Spieler: V223 DEDIZIERTER Leaders-Endpunkt /teams/{id}/leaders + Fallback eingebettete leaders (nur wenn ESPN sie liefert - sonst Zeile weg, nix erfunden)!
# Draft-Vorschau: NFL Draft 29.04.-01.05.2027 Washington D.C. - Reihenfolge nach aktuellem Tabellenstand (schlechtestes Team zuerst)!

def _v214_team_standings_detail(league, team_full):
    # ESPN Standings-Rohdaten fuer EIN Team: Punkte / GB / Heim / Auswaerts / Last 10!
    # Gleiche URL wie _espn_standings_raw, nur Stats-Dict statt Tupel! Fehlt ein Feld -> fehlt es im Fenster (nix erfunden)!
    try:
        sy = _season_year(league)
        urls = []
        if league == "NFL": urls = [f"https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season={sy}&seasontype=2&type=0&level=4"]
        elif league == "NBA": urls = [f"https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season={sy}"]
        elif league == "NHL": urls = [f"https://site.api.espn.com/apis/v2/sports/hockey/nhl/standings?season={sy}"]
        elif league == "MLB": urls = [f"https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings?season={sy}"]
        elif league == "NCAAF": urls = [f"https://site.api.espn.com/apis/v2/sports/football/college-football/standings?season={sy}"]
        tl = (team_full or "").lower()
        for u in urls:
            try:
                r = requests.get(u, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200: continue
                j = r.json()
                def walk(node):
                    if isinstance(node, dict):
                        st = node.get("standings") or {}
                        ents = st.get("entries") if isinstance(st, dict) else None
                        if isinstance(ents, list) and ents:
                            for e in ents:
                                if not isinstance(e, dict): continue
                                tm = e.get("team", {}) or {}
                                dn = str(tm.get("displayName", "") or "").lower()
                                sn = str(tm.get("shortDisplayName", "") or "").lower()
                                if tl and (tl in dn or dn in tl or tl in sn or sn in tl):
                                    vals = {}
                                    for s in e.get("stats", []) or []:
                                        if not isinstance(s, dict): continue
                                        n = (s.get("name", "") or "").lower()
                                        vals[n] = s.get("displayValue", s.get("value", ""))
                                    _v215_all_matches.append(vals)
                                    continue
                        for k, v in node.items():
                            if k == "standings": continue
                            out = walk(v)
                            if out: return out
                    elif isinstance(node, list):
                        for it in node:
                            out = walk(it)
                            if out: return out
                    return None
                _v215_all_matches = []
                walk(j)
                # V215: ESPN liefert pro Team MEHRERE Bloecke (Overall / vs Division / Heim / Auswaerts)!
                # Vorher: erster Treffer = oft falscher Block (z.B. Division-Record, "5.0 Punkte" bei NBA)!
                # Jetzt: Block mit overallwins/overalllosses bevorzugen, sonst erster Treffer!
                found = {}
                for _m in _v215_all_matches:
                    if "overallwins" in _m or "overalllosses" in _m:
                        found = _m; break
                if not found and _v215_all_matches:
                    found = _v215_all_matches[0]
                if found: return found
            except: continue
        return {}
    except: return {}

def _v214_team_next_games(league, team_full, n=3):
    # Naechste n Spiele des Teams (Scoreboard, naechste 14 Tage)!
    try:
        from datetime import date as _d214
        out = []
        _today = _d214.today()
        for _off in range(0, 15):
            _ds = (_today + timedelta(days=_off)).strftime("%Y%m%d")
            for _ev in espn_scoreboard(league, dates=_ds) or []:
                if _ev.get("status", {}).get("type", {}).get("state", "") == "post": continue
                _teams, _ = event_teams(_ev)
                _names = [x[0] for x in _teams]
                if team_full.lower() not in " ".join(_names).lower(): continue
                out.append(_ev)
                if len(out) >= n: return out
        return out
    except: return []

def _v214_team_last_results(league, team_full, n=3):
    # Letzte n Ergebnisse des Teams (Scoreboard, letzte 30 Tage)!
    try:
        from datetime import date as _d214
        out = []
        _today = _d214.today()
        for _off in range(1, 31):
            _ds = (_today - timedelta(days=_off)).strftime("%Y%m%d")
            for _ev in espn_scoreboard(league, dates=_ds) or []:
                if _ev.get("status", {}).get("type", {}).get("state", "") != "post": continue
                _teams, _ = event_teams(_ev)
                _names = [x[0] for x in _teams]
                if team_full.lower() not in " ".join(_names).lower(): continue
                out.append(_ev)
                if len(out) >= n: return out
        return out
    except: return []

_V223_LEADERS_CACHE = {}
def _v223_parse_leaders_cats(cats, _map):
    # Parst EINE Leaders-Kategorie-Liste (dedizierter Endpunkt UND eingebettete leaders haben dieselbe Form)!
    # Nur Kategorien aus _map, nur Top-1 pro Kategorie, max 4 Zeilen - sonst wirds zu lang!
    try:
        out = []
        for cat in (cats or []):
            if not isinstance(cat, dict): continue
            _cat_raw = str(cat.get("name", "") or cat.get("displayName", "") or cat.get("shortDisplayName", "") or "")
            nm = _cat_raw.lower().replace(" ", "").replace("_", "").replace("-", "")
            lbl = _map.get(nm)
            if not lbl: continue
            _lds = cat.get("leaders") or []
            if not _lds: continue
            _top = _lds[0] if isinstance(_lds, list) else {}
            if not isinstance(_top, dict): continue
            _ath_obj = _top.get("athlete") or _top.get("player") or {}
            if isinstance(_ath_obj, dict):
                _ath = _ath_obj.get("displayName", "") or _ath_obj.get("fullName", "") or ""
            else:
                _ath = str(_ath_obj or "")
            if not _ath:
                _ath = str(_top.get("displayName", "") or _top.get("athleteName", "") or "")
            _val = _top.get("displayValue", _top.get("value", "")) or ""
            if _ath and str(_val) != "":
                out.append((lbl, _ath, str(_val)))
            if len(out) >= 4: break
        return out
    except: return []

def _v214_team_leaders(league, team_full):
    # V223: Key Spieler via DEDIZIERTEM Endpunkt /teams/{id}/leaders! Der liefert oft Daten, wo die
    # eingebetteten leaders im Team-Endpunkt leer sind (genau das war Sache 2: "ESPN liefert iwie nicht")!
    # Fallback: eingebettete leaders aus Team-Endpunkt. Cache pro Tag + Team (1 Abruf pro Fenster)!
    # Keine Daten -> [] -> Zeile wird weggelassen (V215-Regel)! NIX erfunden!
    try:
        tid = _espn_team_id_for(league, team_full)
        if not tid: return []
        _today = datetime.now(BERLIN).date().isoformat()
        _ck = (league, str(tid), _today)
        if _ck in _V223_LEADERS_CACHE: return list(_V223_LEADERS_CACHE[_ck])
        sport = {"NFL": "football", "NCAAF": "football", "NBA": "basketball", "NHL": "hockey", "MLB": "baseball"}.get(league, "football")
        key = {"NFL": "nfl", "NCAAF": "college-football", "NBA": "nba", "NHL": "nhl", "MLB": "mlb"}.get(league, "nfl")
        _map = {
            "passingyards": "Passing", "rushingyards": "Rushing", "receivingyards": "Receiving",
            "tackles": "Tackles", "sacks": "Sacks", "interceptions": "Interceptions",
            "points": "Punkte", "rebounds": "Rebounds", "assists": "Assists",
            "steals": "Steals", "blocks": "Blocks",
            "goals": "Tore", "plusminus": "+/-",
            "battingaverage": "Batting Avg", "homeruns": "Homeruns", "runsbattedin": "RBI",
            "earnedrunaverage": "ERA", "strikeouts": "Strikeouts", "wins": "Wins",
        }
        out = []
        # 1) Dedizierter Leaders-Endpunkt!
        try:
            r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{key}/teams/{tid}/leaders", timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            d = r.json() or {}
            cats = d.get("categories") or d.get("leaders") or (d.get("team") or {}).get("leaders") or []
            if isinstance(cats, dict): cats = list(cats.values())
            out = _v223_parse_leaders_cats(cats, _map)
        except: out = []
        # 2) Fallback: eingebettete leaders aus Team-Endpunkt!
        if not out:
            try:
                r2 = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{key}/teams/{tid}", timeout=12, headers={"User-Agent": "Mozilla/5.0"})
                d2 = r2.json() or {}
                leaders = ((d2.get("team") or {}).get("leaders") or [])
                if isinstance(leaders, dict): leaders = list(leaders.values())
                out = _v223_parse_leaders_cats(leaders, _map)
            except: pass
        _V223_LEADERS_CACHE[_ck] = list(out)
        return out
    except: return []

def _v214_team_window_text(league, row, place, div_name, uid):
    # Baut Team-Fenster-Text + Buttons! Sync (HTTP via requests), damit Fav-Add neu rendern kann!
    try:
        disp, short, abbr, W, L, T, streak = row
    except:
        disp, short, abbr, W, L, T, streak = (str(row), str(row), "", 0, 0, 0, "")
    _em = LEAGUES.get(league, {}).get("emoji", "🏈")
    _div_short = (div_name or "").replace("American Football Conference", "AFC").replace("National Football Conference", "NFC").replace("American Football", "AFC").replace("National Football", "NFC").strip()
    lines = [f"{_em} {disp} ({league})", ""]
    # Platz + Division
    if _div_short:
        lines.append(f"🏆 Platz {place} – {_div_short}")
    else:
        lines.append(f"🏆 Platz {place}")
    # Bilanz + Punkte/GB/Heim/Auswaerts/Last 10 aus ESPN-Rohdaten!
    _det = _v214_team_standings_detail(league, disp)
    _rec = f"{W}-{L}" + (f"-{T}" if T else "")
    _pts = str(_det.get("points", "") or "").strip()
    _gb = str(_det.get("gamesbehind", "") or "").strip()
    _home = str(_det.get("home", "") or "").strip()
    _away = str(_det.get("away", "") or "").strip()
    _l10 = ""
    for _k in ("last10", "lastten", "last 10", "l10"):
        if str(_det.get(_k, "") or "").strip():
            _l10 = str(_det.get(_k, "") or "").strip(); break
    _bil = f"📊 Bilanz: {_rec}"
    # V215: "Punkte" gibt es NUR in der NHL! NBA/MLB/NFL/NCAAF haben keine Punkte -
    # ESPN-"points" dort ist was anderes (z.B. "5.0 Punkte" bei 76ers war falsch)!
    if league == "NHL" and _pts and _pts not in ("0", "-", ""):
        _bil += f" • {_pts} Punkte"
    lines.append(_bil)
    if _gb and _gb not in ("0", "0.0", "-", "", "—"):
        # V215: NHL-Rueckstand ist in PUNKTEN (gamesBehind = Punkte hinter Leader, z.B. Penguins 19 Punkte)!
        # Rest: Rueckstand in Spielen! Singular: "1 Spiel" statt "1 Spiele"!
        if league == "NHL":
            lines.append(f"↔️ Rückstand: {_gb} Punkte")
        else:
            try: _gb_f = float(str(_gb).replace(",", "."))
            except: _gb_f = 2
            _gb_w = "Spiel" if _gb_f == 1 else "Spiele"
            lines.append(f"↔️ Rückstand: {_gb} {_gb_w}")
    if _home or _away:
        _ha = []
        if _home: _ha.append(f"🏠 Heim: {_home}")
        if _away: _ha.append(f"✈️ Auswärts: {_away}")
        lines.append(" • ".join(_ha))
    if streak and str(streak) not in ("-", "0", ""):
        lines.append(f"🔥 Streak: {streak}")
    if _l10:
        lines.append(f"📅 Letzte 10: {_l10}")
    lines.append("")
    # Naechste 3 Spiele!
    _nx = _v214_team_next_games(league, disp, n=3)
    if _nx:
        lines.append("⏭️ Nächste Spiele:")
        for _ev in _nx:
            _ds, _dt = fmt_dt(_ev.get("date", ""))
            _teams, _ = event_teams(_ev)
            _opp = ""
            _ha2 = ""
            for _t in _teams:
                if (disp.lower() not in (_t[0] or "").lower()):
                    _opp = _t[0]
                else:
                    _ha2 = (_t[1] or "").lower()
            if _opp:
                if _ha2 == "home": lines.append(f"  • {_ds} – vs {_opp}")
                elif _ha2 == "away": lines.append(f"  • {_ds} – @ {_opp}")
                else: lines.append(f"  • {_ds} – vs {_opp}")
        lines.append("")
    # Letzte 3 Ergebnisse!
    _lr = _v214_team_last_results(league, disp, n=3)
    if _lr:
        lines.append("✅ Letzte Ergebnisse:")
        for _ev in _lr:
            _ds, _dt = fmt_dt(_ev.get("date", ""))
            _teams, _ = event_teams(_ev)
            _my = None; _op = None; _opp2 = ""
            for _t in _teams:
                try: _sc = int(str(_t[2])) if str(_t[2]).isdigit() else 0
                except: _sc = 0
                if disp.lower() in (_t[0] or "").lower(): _my = _sc
                else: _opp2 = _t[0]; _op = _sc
            if _my is not None and _op is not None:
                _w = "✅" if _my > _op else ("❌" if _my < _op else "➖")
                lines.append(f"  • {_ds} – vs {_opp2} {_my}:{_op} {_w}")
        lines.append("")
    # News-Zaehler (24 Std.) - gleiche Logik wie Meine Woche!
    try:
        _news_all, _src2 = _team_news_all(league, disp, limit=8) or ([], "")
        _fresh = []
        for _a in (_news_all or []):
            try:
                if _news_is_fresh(_a.get("published", ""), 1): _fresh.append(_a)
            except: _fresh.append(_a)
        if _fresh: lines.append(f"📰 {len(_fresh)} neue News (24 Std.)")
        else: lines.append("📰 Keine neuen News (24 Std.)")
    except:
        lines.append("📰 Keine neuen News (24 Std.)")
    lines.append("")
    # Key Spieler!
    _leaders = _v214_team_leaders(league, disp)
    if _leaders:
        lines.append("⭐ Key Spieler:")
        for _lbl, _ath, _val in _leaders:
            lines.append(f"  • {_ath} – {_val} {_lbl}")
    # V215: Keine Daten -> Zeile GANZ weglassen (statt "Keine Daten (ESPN)")! Nix erfunden!
    else:
        pass
    # Buttons!
    _is_fav = False
    try:
        _favs = favs_for(uid) if uid else []
        _favs_low = [(f.split(" (")[0].strip().lower()) for f in _favs]
        _is_fav = any((disp.lower() in fn or fn in disp.lower()) for fn in _favs_low)
    except: pass
    # Callback-Daten duerfen kein ":" im Team-Namen haben - Team-Namen haben kein ":"! Sicher!
    _rows = []
    _rows.append([InlineKeyboardButton("⏭️ Alle nächsten Spiele", callback_data=f"teamnext:{league}:{disp}"),
                  InlineKeyboardButton("📰 News", callback_data=f"teamnews:{league}:{disp}")])
    if not _is_fav:
        _rows.append([InlineKeyboardButton("⭐ Zu Favoriten", callback_data=f"teamfav:{league}:{disp}")])
    else:
        lines.append("")
        lines.append("⭐ Dein Favorit!")
    return "\n".join(lines), InlineKeyboardMarkup(_rows)

async def team_window_cmd(update, ctx, league, row, place, div_name, back_cb="", num_mid=None):
    # V214: Team-Fenster als NEUE Nachricht (wie Tabellen)! Zahl wird gemappt (Schliessen loescht Zahl mit)!
    try:
        target = update.message or update.callback_query.message
        uid = update.effective_user.id if update.effective_user else 0
        _load = None
        try: _load = await target.reply_text(f"⏳ Ich hol die Infos zu {row[0] if row else 'dem Team'}... einen Moment!")
        except: pass
        _txt, _kb = _v214_team_window_text(league, row, place, div_name, uid)
        if _load:
            try: await ctx.bot.delete_message(chat_id=uid, message_id=_load.message_id)
            except: pass
        _rows2 = [list(r) for r in _kb.inline_keyboard]
        if back_cb:
            _rows2.append([InlineKeyboardButton("⬅️ Zurück zur Tabelle", callback_data=back_cb)])
        _kb2 = InlineKeyboardMarkup(_rows2)
        _m = await target.reply_text(_txt, reply_markup=_with_close(_kb2))
        try: _chain_add(uid, _m.message_id)
        except: pass
        if num_mid:
            try: _CLOSE_NUM_MAP[(int(uid), int(_m.message_id))] = int(num_mid)
            except: pass
        return _m
    except Exception as _e:
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Team-Fenster konnte grad nicht geladen werden!\nVersuch es gleich nochmal!", reply_markup=small_kb())
        except: pass
        return None

async def team_next_cmd(update, ctx, league, team_full):
    # V214: Alle naechsten Spiele EINES Teams (naechste 30 Tage, max 8)!
    _load = None
    try:
        target = update.message or update.callback_query.message
        uid = update.effective_user.id if update.effective_user else 0
        _load = await _loading_start(target, "⏳ Ich hole die nächsten Spiele... einen Moment")
        from datetime import date as _d214
        out = []
        _today = _d214.today()
        for _off in range(0, 31):
            _ds = (_today + timedelta(days=_off)).strftime("%Y%m%d")
            for _ev in espn_scoreboard(league, dates=_ds) or []:
                if _ev.get("status", {}).get("type", {}).get("state", "") == "post": continue
                _teams, _ = event_teams(_ev)
                _names = [x[0] for x in _teams]
                if team_full.lower() not in " ".join(_names).lower(): continue
                out.append(_ev)
                if len(out) >= 8: break
            if len(out) >= 8: break
        try: await _loading_done(ctx, uid, _load)
        except: pass
        _em = LEAGUES.get(league, {}).get("emoji", "🏈")
        if not out:
            await target.reply_text(f"⏭️ Alle nächsten Spiele – {team_full}\n\nKeine kommenden Spiele gefunden.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]]))
            return
        lines = [f"⏭️ Alle nächsten Spiele – {_em} {team_full}", ""]
        for _ev in out:
            _ds, _dt = fmt_dt(_ev.get("date", ""))
            _teams, _ = event_teams(_ev)
            _opp = ""; _ha2 = ""
            for _t in _teams:
                if team_full.lower() not in (_t[0] or "").lower(): _opp = _t[0]
                else: _ha2 = (_t[1] or "").lower()
            if _ha2 == "home": lines.append(f"• {_ds} – vs {_opp}")
            elif _ha2 == "away": lines.append(f"• {_ds} – @ {_opp}")
            else: lines.append(f"• {_ds} – vs {_opp}")
        _kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        _m = await target.reply_text("\n".join(lines), reply_markup=_with_close(_kb))
        try: _chain_add(uid, _m.message_id)
        except: pass
    except Exception:
        try: await _loading_done(ctx, update.effective_user.id if update.effective_user else 0, _load)
        except: pass
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Nächste Spiele konnten grad nicht geladen werden!", reply_markup=small_kb())
        except: pass

async def team_news_cmd(update, ctx, league, team_full):
    # V214: News fuer EIN Team (auch wenn kein Favorit)! Headline + Link, gefiltert wie ueberall!
    _load = None
    try:
        target = update.message or update.callback_query.message
        _load = await _loading_start(target, "⏳ Ich hole die News... einen Moment")
        arts, _src = _team_news_all(league, team_full, limit=8)
        try: await _loading_done(ctx, update.effective_user.id if update.effective_user else 0, _load)
        except: pass
        arts = [a for a in arts if not _v136_is_scam_news(a.get("headline", ""), a.get("link", ""))]
        arts = _dedupe_news(arts)
        _em = LEAGUES.get(league, {}).get("emoji", "🏈")
        if not arts:
            await target.reply_text(f"📰 News – {team_full}\n\nGerade keine neuen {team_full}-News.\nCheck später nochmal!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]]))
            return
        import html as _html
        lines = [f"📰 News – {_em} {team_full}\n", f"Nur Headline + Link! Artikel auf Englisch! Quelle: {_src}!\n"]
        for i, a in enumerate(arts, 1):
            _hl = _html.escape(a['headline'])
            _link = (a.get("link") or "").replace('"', '')
            if _link: lines.append(f"{i}. {_hl} - <a href=\"{_link}\">🔗 Lesen</a>")
            else: lines.append(f"{i}. {_hl}")
        _kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        _txt = "\n".join(lines)
        try:
            q = update.callback_query
            if q and q.message:
                try: await q.message.edit_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True)
                except Exception: _m = await q.message.reply_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True); _chain_add(update.effective_user.id if update.effective_user else 0, _m.message_id)
            else:
                _m = await update.message.reply_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True); _chain_add(update.effective_user.id if update.effective_user else 0, _m.message_id)
        except Exception:
            await _cb_edit(update, "\n".join([f"📰 News – {team_full}\n"] + [f"{i}. {a['headline']}" for i, a in enumerate(arts, 1)]), _kb)
    except Exception:
        try: await _loading_done(ctx, update.effective_user.id if update.effective_user else 0, _load)
        except: pass
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 News konnten grad nicht geladen werden!", reply_markup=small_kb())
        except: pass

def _v215_nfl_overall_records():
    # V215: NFL Overall-Records aus EINEM Standings-Fetch (ohne level=4-Division-Bloecke)!
    # Sammelt pro Team den Block mit overallwins -> sonst wuerde der Division-Block falsche Bilanzen liefern!
    try:
        sy = _season_year("NFL")
        u = f"https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season={sy}"
        r = requests.get(u, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return {}
        j = r.json() or {}
        best, fallback = {}, {}
        def walk(node):
            if isinstance(node, dict):
                st = node.get("standings") or {}
                ents = st.get("entries") if isinstance(st, dict) else None
                if isinstance(ents, list) and ents:
                    for e in ents:
                        if not isinstance(e, dict): continue
                        tm = e.get("team", {}) or {}
                        disp = tm.get("displayName", "") or tm.get("shortDisplayName", "") or ""
                        if not disp: continue
                        vals = {}
                        for s in e.get("stats", []) or []:
                            if not isinstance(s, dict): continue
                            vals[(s.get("name", "") or "").lower()] = s.get("displayValue", s.get("value", ""))
                        def _iv(*names):
                            for n in names:
                                if n in vals:
                                    try: return int(float(str(vals[n])))
                                    except: pass
                            return None
                        W = _iv("overallwins", "wins")
                        L = _iv("overalllosses", "losses")
                        if W is None or L is None: continue
                        if "overallwins" in vals or "overalllosses" in vals:
                            best[disp] = (W, L)
                        elif disp not in fallback:
                            fallback[disp] = (W, L)
                    return
                for k, v in node.items():
                    if k == "standings": continue
                    walk(v)
            elif isinstance(node, list):
                for it in node: walk(it)
        walk(j)
        out = dict(fallback); out.update(best)
        return out
    except: return {}


# ===== V242: NERD-MODUS (Phase 1: NFL) - alle Fakten kuratiert & geprueft! =====
NFL_RULES_TEXT = """📖 NFL – Die Regeln (kurz & knackig)

⏱️ Spielzeit: 4 Viertel à 15 Minuten = 60 Minuten. Bei Gleichstand: Overtime!
👥 Spieler: 11 pro Team auf dem Feld – Offense, Defense & Special Teams.
🏈 Downs: Die Offense hat 4 Versuche für 10 Yards. Schafft sie's → 4 neue Versuche. Sonst → Ballbesitz wechselt!
🎯 Punkte: Touchdown 6, Extrapunkt 1 (Kick) oder 2 (Conversion), Field Goal 3, Safety 2
🔄 Ballverlust: Interception (abgefangener Pass) oder Fumble (verlorener Ball) = Gegner bekommt den Ball!
⏱️ Overtime: Regular Season 10 Min – danach kann's Unentschieden geben. Playoffs: Bis zur Entscheidung, beide Teams bekommen den Ball!
🏆 Playoffs: 7 Teams pro Conference → Wild Card → Divisional → Conference Championship → Super Bowl!"""

# V242: Alle 32 NFL-Teams - Reihenfolge = Anzeige-Reihenfolge (AFC East/North/South/West, NFC East/North/South/West)!
NFL_TEAMS_NERD = {
    "bills": {"name": "Buffalo Bills", "city": "Buffalo", "stadion": "Highmark Stadium", "gegr": "1960", "div": "AFC East", "farben": "Blau-Rot-Weiß", "titel": "0× Super-Bowl-Champion", "geschichte": "1960 in der AFL gegründet. Anfang der 90er 4× in Folge im Super Bowl – alle 4 verloren. Seit 2020 wieder ein Top-Team um Josh Allen."},
    "dolphins": {"name": "Miami Dolphins", "city": "Miami Gardens", "stadion": "Hard Rock Stadium", "gegr": "1966", "div": "AFC East", "farben": "Türkis-Orange-Weiß", "titel": "2× Super-Bowl-Champion (VII, VIII)", "geschichte": "Die einzige perfekte Saison der NFL: 1972 mit 17-0! Unter Don Shula das Team der 70er."},
    "patriots": {"name": "New England Patriots", "city": "Foxborough", "stadion": "Gillette Stadium", "gegr": "1959 (als Boston Patriots)", "div": "AFC East", "farben": "Marineblau-Silber-Rot", "titel": "6× Super-Bowl-Champion", "geschichte": "Die Dynastie der 2000er/2010er: 6 Super Bowls mit Brady & Belichick. 2017 der legendäre 28-3-Comeback-Sieg im Super Bowl LI."},
    "jets": {"name": "New York Jets", "city": "East Rutherford", "stadion": "MetLife Stadium", "gegr": "1959 (als Titans of New York)", "div": "AFC East", "farben": "Grün-Weiß", "titel": "1× Super-Bowl-Champion (III)", "geschichte": "Super Bowl III 1969: Joe Namath garantierte den Sieg gegen die Colts – und hielt Wort! Seitdem warten die Jets auf den nächsten Titel."},
    "ravens": {"name": "Baltimore Ravens", "city": "Baltimore", "stadion": "M&T Bank Stadium", "gegr": "1996", "div": "AFC North", "farben": "Lila-Schwarz-Gold", "titel": "2× Super-Bowl-Champion (XXXV, XLVII)", "geschichte": "1996 nach Baltimore gezogen. Harte Defense-Tradition: Ray Lewis & Ed Reed. Super-Bowl-Sieg 2013 im 'Harbaugh-Bowl' gegen die 49ers."},
    "bengals": {"name": "Cincinnati Bengals", "city": "Cincinnati", "stadion": "Paycor Stadium", "gegr": "1968", "div": "AFC North", "farben": "Orange-Schwarz", "titel": "0× Super-Bowl-Champion", "geschichte": "3× im Super Bowl (1981, 1988, 2021) – 3× verloren. Joe Burrow führte sie Anfang 2022 zurück in den Super Bowl."},
    "browns": {"name": "Cleveland Browns", "city": "Cleveland", "stadion": "Huntington Bank Field", "gegr": "1946", "div": "AFC North", "farben": "Orange-Braun-Weiß", "titel": "0× Super-Bowl-Champion (4 NFL-Meisterschaften vor dem Super Bowl)", "geschichte": "Eines der ältesten Teams (1946). 4 NFL-Titel in den 50ern, aber noch nie im Super Bowl. 'The Dawg Pound' – eine der lautesten Fankurven der Liga."},
    "steelers": {"name": "Pittsburgh Steelers", "city": "Pittsburgh", "stadion": "Acrisure Stadium", "gegr": "1933", "div": "AFC North", "farben": "Schwarz-Gold", "titel": "6× Super-Bowl-Champion (IX, X, XIII, XIV, XL, XLIII)", "geschichte": "Die 70er-Dynastie: 4 Super Bowls in 6 Jahren mit der 'Steel Curtain'-Defense. 6 Titel – zusammen mit den Patriots die meisten der Liga. 'Terrible Towel' & Steeler Nation!"},
    "texans": {"name": "Houston Texans", "city": "Houston", "stadion": "NRG Stadium", "gegr": "2002", "div": "AFC South", "farben": "Dunkelblau-Rot-Weiß", "titel": "0× Super-Bowl-Champion", "geschichte": "Jüngstes NFL-Team (2002). Das erste Team in Houston nach den Oilers. Wartet noch auf den ersten Super-Bowl-Einzug."},
    "colts": {"name": "Indianapolis Colts", "city": "Indianapolis", "stadion": "Lucas Oil Stadium", "gegr": "1953 (als Baltimore Colts)", "div": "AFC South", "farben": "Blau-Weiß", "titel": "2× Super-Bowl-Champion (V, XLI)", "geschichte": "Peyton Manning machte Indy groß – Super-Bowl-Sieg 2007. 'The Greatest Game Ever Played': NFL-Meisterschaft 1958 gegen die Giants."},
    "jaguars": {"name": "Jacksonville Jaguars", "city": "Jacksonville", "stadion": "EverBank Stadium", "gegr": "1995", "div": "AFC South", "farben": "Türkis-Schwarz-Gold", "titel": "0× Super-Bowl-Champion", "geschichte": "Seit 1995 dabei. 2017 kurz vor dem Super Bowl (AFC-Finale vs. Patriots). 'DUUUVAL!' – der berühmteste Schlachtruf der Liga."},
    "titans": {"name": "Tennessee Titans", "city": "Nashville", "stadion": "Nissan Stadium", "gegr": "1960 (als Houston Oilers)", "div": "AFC South", "farben": "Marineblau-Hellblau", "titel": "0× Super-Bowl-Champion", "geschichte": "Als Houston Oilers gegründet, seit 1997 in Tennessee. Super Bowl XXXIV 2000: 1 Yard vor dem Ausgleich gestoppt ('One Yard Short')!"},
    "broncos": {"name": "Denver Broncos", "city": "Denver", "stadion": "Empower Field at Mile High", "gegr": "1960", "div": "AFC West", "farben": "Orange-Marineblau", "titel": "3× Super-Bowl-Champion (XXXII, XXXIII, 50)", "geschichte": "John Elway & der 'Mile High'-Vorteil (über 1.600 m Höhe!). Super-Bowl-Sieg 2016 mit der besten Defense der Liga."},
    "chiefs": {"name": "Kansas City Chiefs", "city": "Kansas City", "stadion": "GEHA Field at Arrowhead Stadium", "gegr": "1960 (als Dallas Texans)", "div": "AFC West", "farben": "Rot-Gold", "titel": "4× Super-Bowl-Champion (IV, LIV, LVII, LVIII)", "geschichte": "Arrowhead ist das lauteste Stadion der Welt (142,2 dB Weltrekord). Die Mahomes-Ära: 3 Super-Bowl-Siege in 5 Jahren."},
    "chargers": {"name": "Los Angeles Chargers", "city": "Inglewood", "stadion": "SoFi Stadium", "gegr": "1960", "div": "AFC West", "farben": "Pulverblau-Gelb-Weiß", "titel": "0× Super-Bowl-Champion", "geschichte": "1960 in L.A. gegründet, lange in San Diego, seit 2017 zurück in L.A. 'Air Coryell' – die Pass-Offense der 80er. Noch ohne Super-Bowl-Titel."},
    "raiders": {"name": "Las Vegas Raiders", "city": "Las Vegas", "stadion": "Allegiant Stadium", "gegr": "1960", "div": "AFC West", "farben": "Silber-Schwarz", "titel": "3× Super-Bowl-Champion (XI, XV, XVIII)", "geschichte": "Die 'Silver & Black' – das Bad-Boy-Image der Liga. 'Just Win, Baby!' (Al Davis). 3 Super-Bowl-Titel, seit 2020 in Las Vegas."},
    "cowboys": {"name": "Dallas Cowboys", "city": "Arlington", "stadion": "AT&T Stadium", "gegr": "1960", "div": "NFC East", "farben": "Marineblau-Silber-Weiß", "titel": "5× Super-Bowl-Champion (VI, XII, XXVII, XXVIII, XXX)", "geschichte": "'America's Team'! 5 Super-Bowl-Titel, die 90er-Dynastie um Aikman, Smith & Irvin. AT&T Stadium – Platz für über 100.000 Fans."},
    "giants": {"name": "New York Giants", "city": "East Rutherford", "stadion": "MetLife Stadium", "gegr": "1925", "div": "NFC East", "farben": "Blau-Rot-Weiß", "titel": "4× Super-Bowl-Champion (XXI, XXV, XLII, XLVI)", "geschichte": "Seit 1925 dabei – eines der ältesten Teams. 2008 & 2012: Zwei Super-Bowl-Siege gegen die favorisierten Patriots (David vs. Goliath!)."},
    "eagles": {"name": "Philadelphia Eagles", "city": "Philadelphia", "stadion": "Lincoln Financial Field", "gegr": "1933", "div": "NFC East", "farben": "Mitternachtsgrün-Silber", "titel": "2× Super-Bowl-Champion (LII, LIX)", "geschichte": "'Fly, Eagles, Fly!' – und 'E-A-G-L-E-S'! Erster Super-Bowl-Titel 2018 (Philly Special!), zweiter 2025 gegen die Chiefs."},
    "commanders": {"name": "Washington Commanders", "city": "Landover", "stadion": "Northwest Stadium", "gegr": "1932 (als Boston Braves)", "div": "NFC East", "farben": "Burgunder-Gold", "titel": "3× Super-Bowl-Champion (XVII, XXII, XXVI)", "geschichte": "3 Super-Bowl-Titel unter Joe Gibbs (80er/90er). Früher Redskins, seit 2022 Commanders. 'Hail to the Commanders!'"},
    "bears": {"name": "Chicago Bears", "city": "Chicago", "stadion": "Soldier Field", "gegr": "1920 (als Decatur Staleys)", "div": "NFC North", "farben": "Marineblau-Orange", "titel": "1× Super-Bowl-Champion (XX)", "geschichte": "Gründungsmitglied der NFL (1920). Die 'Monsters of the Midway'. Die 85er-Bears mit der besten Defense aller Zeiten – Super-Bowl-Sieg 1986."},
    "lions": {"name": "Detroit Lions", "city": "Detroit", "stadion": "Ford Field", "gegr": "1930 (als Portsmouth Spartans)", "div": "NFC North", "farben": "Honolulu-Blau-Silber", "titel": "0× Super-Bowl-Champion (4 NFL-Meisterschaften)", "geschichte": "4 NFL-Titel in den 50ern, aber noch nie im Super Bowl. Längste Playoff-Sieg-Durststrecke der Liga – Anfang 2024 endlich wieder im NFC-Finale!"},
    "packers": {"name": "Green Bay Packers", "city": "Green Bay", "stadion": "Lambeau Field", "gegr": "1919", "div": "NFC North", "farben": "Grün-Gold", "titel": "4× Super-Bowl-Champion (I, II, XXXI, XLV)", "geschichte": "Das einzige Team, das den Fans gehört (Non-Profit)! 'Titletown USA' – 13 NFL-Meisterschaften insgesamt. Lambeau Field – das älteste Stadion der NFL."},
    "vikings": {"name": "Minnesota Vikings", "city": "Minneapolis", "stadion": "U.S. Bank Stadium", "gegr": "1961", "div": "NFC North", "farben": "Lila-Gold", "titel": "0× Super-Bowl-Champion", "geschichte": "4× im Super Bowl (70er) – 4× verloren. 'Skol!' – der berühmteste Schlachtruf. Die 'Purple People Eaters'-Defense der 70er."},
    "falcons": {"name": "Atlanta Falcons", "city": "Atlanta", "stadion": "Mercedes-Benz Stadium", "gegr": "1966", "div": "NFC South", "farben": "Rot-Schwarz", "titel": "0× Super-Bowl-Champion", "geschichte": "2× im Super Bowl – 1999 und 2017. 2017: 28-3-Führung gegen die Patriots verspielt – das berühmteste Comeback der NFL-Geschichte."},
    "panthers": {"name": "Carolina Panthers", "city": "Charlotte", "stadion": "Bank of America Stadium", "gegr": "1995", "div": "NFC South", "farben": "Schwarz-Blau-Silber", "titel": "0× Super-Bowl-Champion", "geschichte": "Seit 1995 dabei. 2× im Super Bowl (2004, 2016) – beide verloren. 'Keep Pounding!' – der Schlachtruf, benannt nach Sam Mills."},
    "saints": {"name": "New Orleans Saints", "city": "New Orleans", "stadion": "Caesars Superdome", "gegr": "1967", "div": "NFC South", "farben": "Schwarz-Gold", "titel": "1× Super-Bowl-Champion (XLIV)", "geschichte": "1967 gegründet. Nach Hurricane Katrina 2005 wurde das Team zum Symbol für den Wiederaufbau – 2010 der erste Super-Bowl-Titel!"},
    "buccaneers": {"name": "Tampa Bay Buccaneers", "city": "Tampa", "stadion": "Raymond James Stadium", "gegr": "1976", "div": "NFC South", "farben": "Rot-Zinn", "titel": "2× Super-Bowl-Champion (XXXVII, LV)", "geschichte": "1976 gestartet – mit 26 Niederlagen in Folge! Dann 2 Super-Bowl-Titel (2003 & 2021). Das Piratenschiff im Stadion feuert bei jedem TD die Kanonen ab!"},
    "cardinals": {"name": "Arizona Cardinals", "city": "Glendale", "stadion": "State Farm Stadium", "gegr": "1898 (als Morgan Athletic Club)", "div": "NFC West", "farben": "Kardinalrot-Weiß", "titel": "0× Super-Bowl-Champion (2 NFL-Meisterschaften)", "geschichte": "Ältestes Profi-Team der USA (1898)! Von Chicago über St. Louis nach Arizona. 2009 knapp im Super Bowl verloren."},
    "rams": {"name": "Los Angeles Rams", "city": "Inglewood", "stadion": "SoFi Stadium", "gegr": "1936 (als Cleveland Rams)", "div": "NFC West", "farben": "Blau-Gelb", "titel": "2× Super-Bowl-Champion (XXXIV, LVI)", "geschichte": "3 Städte: Cleveland → L.A. → St. Louis → zurück nach L.A. 2000 'Greatest Show on Turf', 2022 Super-Bowl-Sieg im eigenen Stadion!"},
    "49ers": {"name": "San Francisco 49ers", "city": "Santa Clara", "stadion": "Levi's Stadium", "gegr": "1946", "div": "NFC West", "farben": "Scharlachrot-Gold", "titel": "5× Super-Bowl-Champion (XVI, XIX, XXIII, XXIV, XXIX)", "geschichte": "Die 80er-Dynastie: Montana → Rice, 4 Super Bowls. 5 Titel insgesamt. 'The Catch' (1982) – einer der berühmtesten Spielzüge aller Zeiten."},
    "seahawks": {"name": "Seattle Seahawks", "city": "Seattle", "stadion": "Lumen Field", "gegr": "1976", "div": "NFC West", "farben": "Marineblau-Grün-Grau", "titel": "1× Super-Bowl-Champion (XLVIII)", "geschichte": "Seit 1976 dabei. Die '12s' – die lautesten Fans der Liga. Super-Bowl-Sieg 2014 mit der 'Legion of Boom'-Defense."},
}


# V242: Hall of Famers pro Team - NUR Top-Legenden (kuratiert, nicht alle 30-40 Namen)! Format: (Name, Position)!
NFL_HOF = {
    "bills": [("Jim Kelly", "QB"), ("Thurman Thomas", "RB"), ("Bruce Smith", "DE"), ("Andre Reed", "WR"), ("Marv Levy", "Trainer")],
    "dolphins": [("Dan Marino", "QB"), ("Don Shula", "Trainer"), ("Bob Griese", "QB"), ("Larry Csonka", "RB"), ("Jason Taylor", "DE"), ("Zach Thomas", "LB"), ("Dwight Stephenson", "C")],
    "patriots": [("John Hannah", "G"), ("Andre Tippett", "LB"), ("Ty Law", "CB"), ("Richard Seymour", "DT"), ("Mike Haynes", "CB")],
    "jets": [("Joe Namath", "QB"), ("Curtis Martin", "RB"), ("Don Maynard", "WR"), ("Joe Klecko", "DT"), ("Darrelle Revis", "CB"), ("Kevin Mawae", "C"), ("Winston Hill", "T")],
    "ravens": [("Ray Lewis", "LB"), ("Ed Reed", "S"), ("Jonathan Ogden", "T")],
    "bengals": [("Anthony Muñoz", "T"), ("Ken Riley", "CB")],
    "browns": [("Jim Brown", "RB"), ("Otto Graham", "QB"), ("Paul Brown", "Trainer"), ("Ozzie Newsome", "TE"), ("Joe Thomas", "T"), ("Lou Groza", "K"), ("Marion Motley", "FB")],
    "steelers": [("Joe Greene", "DT"), ("Terry Bradshaw", "QB"), ("Franco Harris", "RB"), ("Jack Lambert", "LB"), ("Jack Ham", "LB"), ("Mel Blount", "CB"), ("Lynn Swann", "WR"), ("John Stallworth", "WR"), ("Troy Polamalu", "S"), ("Jerome Bettis", "RB"), ("Rod Woodson", "CB"), ("Chuck Noll", "Trainer")],
    "texans": [("Andre Johnson", "WR")],
    "colts": [("Peyton Manning", "QB"), ("Marvin Harrison", "WR"), ("Johnny Unitas", "QB"), ("Dwight Freeney", "DE"), ("Edgerrin James", "RB"), ("Tony Dungy", "Trainer"), ("Lenny Moore", "RB"), ("Gino Marchetti", "DE"), ("Jim Parker", "T"), ("Raymond Berry", "WR"), ("John Mackey", "TE")],
    "jaguars": [("Tony Boselli", "T")],
    "titans": [("Bruce Matthews", "G"), ("Warren Moon", "QB"), ("Earl Campbell", "RB"), ("Elvin Bethea", "DE"), ("Mike Munchak", "G"), ("Curley Culp", "DT")],
    "broncos": [("John Elway", "QB"), ("Terrell Davis", "RB"), ("Shannon Sharpe", "TE"), ("Champ Bailey", "CB"), ("Steve Atwater", "S"), ("Randy Gradishar", "LB"), ("Floyd Little", "RB"), ("Gary Zimmerman", "T")],
    "chiefs": [("Len Dawson", "QB"), ("Derrick Thomas", "LB"), ("Tony Gonzalez", "TE"), ("Bobby Bell", "LB"), ("Buck Buchanan", "DT"), ("Willie Lanier", "LB"), ("Jan Stenerud", "K"), ("Emmitt Thomas", "CB"), ("Hank Stram", "Trainer"), ("Will Shields", "G")],
    "chargers": [("Dan Fouts", "QB"), ("LaDainian Tomlinson", "RB"), ("Junior Seau", "LB"), ("Kellen Winslow", "TE"), ("Lance Alworth", "WR"), ("Charlie Joiner", "WR"), ("Ron Mix", "T"), ("Don Coryell", "Trainer"), ("Antonio Gates", "TE")],
    "raiders": [("Howie Long", "DE"), ("Marcus Allen", "RB"), ("Tim Brown", "WR"), ("Gene Upshaw", "G"), ("Art Shell", "T"), ("Ted Hendricks", "LB"), ("Ken Stabler", "QB"), ("Fred Biletnikoff", "WR"), ("Charles Woodson", "CB"), ("Cliff Branch", "WR")],
    "cowboys": [("Roger Staubach", "QB"), ("Troy Aikman", "QB"), ("Emmitt Smith", "RB"), ("Michael Irvin", "WR"), ("Bob Lilly", "DT"), ("Randy White", "DT"), ("DeMarcus Ware", "LB"), ("Tony Dorsett", "RB"), ("Mel Renfro", "CB"), ("Rayfield Wright", "T"), ("Tom Landry", "Trainer"), ("Drew Pearson", "WR"), ("Chuck Howley", "LB")],
    "giants": [("Lawrence Taylor", "LB"), ("Michael Strahan", "DE"), ("Harry Carson", "LB"), ("Frank Gifford", "RB"), ("Sam Huff", "LB"), ("Mel Hein", "C"), ("Y.A. Tittle", "QB"), ("Andy Robustelli", "DE"), ("Emlen Tunnell", "S"), ("Roosevelt Brown", "T")],
    "eagles": [("Reggie White", "DE"), ("Brian Dawkins", "S"), ("Chuck Bednarik", "C"), ("Steve Van Buren", "RB"), ("Tommy McDonald", "WR"), ("Pete Pihos", "E"), ("Harold Carmichael", "WR"), ("Eric Allen", "CB")],
    "commanders": [("Sammy Baugh", "QB"), ("Darrell Green", "CB"), ("Art Monk", "WR"), ("John Riggins", "RB"), ("Sonny Jurgensen", "QB"), ("Russ Grimm", "G"), ("Joe Gibbs", "Trainer"), ("Charley Taylor", "WR"), ("Chris Hanburger", "LB"), ("Bobby Mitchell", "WR")],
    "bears": [("Walter Payton", "RB"), ("Dick Butkus", "LB"), ("Mike Singletary", "LB"), ("Gale Sayers", "RB"), ("Sid Luckman", "QB"), ("George Halas", "Trainer"), ("Bronko Nagurski", "FB"), ("Red Grange", "RB"), ("Mike Ditka", "TE"), ("Brian Urlacher", "LB"), ("Devin Hester", "KR"), ("Richard Dent", "DE"), ("Dan Hampton", "DT"), ("Steve McMichael", "DT")],
    "lions": [("Barry Sanders", "RB"), ("Calvin Johnson", "WR"), ("Dick LeBeau", "CB"), ("Lem Barney", "CB"), ("Joe Schmidt", "LB"), ("Alex Karras", "DT"), ("Charlie Sanders", "TE"), ("Bobby Layne", "QB"), ("Doak Walker", "RB")],
    "packers": [("Bart Starr", "QB"), ("Brett Favre", "QB"), ("Forrest Gregg", "T"), ("Ray Nitschke", "LB"), ("Willie Davis", "DE"), ("Paul Hornung", "RB"), ("Herb Adderley", "CB"), ("Jim Taylor", "FB"), ("Curly Lambeau", "Trainer"), ("Vince Lombardi", "Trainer"), ("Jerry Kramer", "G"), ("Dave Robinson", "LB"), ("LeRoy Butler", "S"), ("Sterling Sharpe", "WR")],
    "vikings": [("Fran Tarkenton", "QB"), ("Randy Moss", "WR"), ("John Randle", "DT"), ("Cris Carter", "WR"), ("Alan Page", "DT"), ("Jared Allen", "DE"), ("Mick Tingelhoff", "C"), ("Bud Grant", "Trainer"), ("Carl Eller", "DE"), ("Paul Krause", "S"), ("Ron Yary", "T")],
    "falcons": [("Deion Sanders", "CB"), ("Claude Humphrey", "DE")],
    "panthers": [("Julius Peppers", "DE")],
    "saints": [("Rickey Jackson", "LB"), ("Willie Roaf", "T"), ("Morten Andersen", "K"), ("Sam Mills", "LB")],
    "buccaneers": [("Derrick Brooks", "LB"), ("Warren Sapp", "DT"), ("John Lynch", "S"), ("Lee Roy Selmon", "DE"), ("Ronde Barber", "CB")],
    "cardinals": [("Roger Wehrli", "CB"), ("Dan Dierdorf", "T"), ("Aeneas Williams", "CB"), ("Jackie Smith", "TE")],
    "rams": [("Kurt Warner", "QB"), ("Marshall Faulk", "RB"), ("Eric Dickerson", "RB"), ("Deacon Jones", "DE"), ("Merlin Olsen", "DT"), ("Jack Youngblood", "DE"), ("Tom Mack", "G"), ("Norm Van Brocklin", "QB"), ("Isaac Bruce", "WR"), ("Orlando Pace", "T"), ("Kevin Greene", "LB")],
    "49ers": [("Joe Montana", "QB"), ("Jerry Rice", "WR"), ("Steve Young", "QB"), ("Ronnie Lott", "S"), ("Charles Haley", "LB"), ("Dave Wilcox", "LB"), ("Leo Nomellini", "DT"), ("Bob St. Clair", "T"), ("Hugh McElhenny", "RB"), ("Patrick Willis", "LB")],
    "seahawks": [("Steve Largent", "WR"), ("Cortez Kennedy", "DT"), ("Walter Jones", "T"), ("Kenny Easley", "S")],
}

# V242: HOF-Detailseiten - Phase 1: Steelers (alle 12) + groesste Legenden der Liga! Rest folgt in Phase 2!
NFL_HOF_DETAILS = {
    "Joe Greene": "Position: DT | Steelers 1969–1981 | Aufnahme: 1987\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 10× Pro Bowl, 2× Defensive Player of the Year\n🔥 Der Anker der 'Steel Curtain'-Defense\n→ Der Anführer der besten Defense aller Zeiten.",
    "Terry Bradshaw": "Position: QB | Steelers 1970–1983 | Aufnahme: 1989\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 2× Super-Bowl-MVP, NFL MVP 1978\n🔥 27.989 Passing Yards, 212 TDs\n→ Vom viel kritisierten Rookie zum 4-fachen Champion.",
    "Franco Harris": "Position: RB | Steelers 1972–1983 | Aufnahme: 1990\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 9× Pro Bowl, 12.120 Rushing Yards\n🔥 'Immaculate Reception' 1972 – der berühmteste Spielzug der NFL-Geschichte\n→ Der Mann vom Wunder-Catch.",
    "Jack Lambert": "Position: LB | Steelers 1974–1984 | Aufnahme: 1990\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 9× Pro Bowl, 6× First-Team All-Pro\n🔥 Defensive Player of the Year 1976, 28 Interceptions\n→ Das furchtlose Herz der Steel Curtain.",
    "Jack Ham": "Position: LB | Steelers 1971–1982 | Aufnahme: 1988\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 8× Pro Bowl, 8× First-Team All-Pro\n🔥 32 Interceptions als Linebacker!\n→ Einer der komplettesten Linebacker aller Zeiten.",
    "Mel Blount": "Position: CB | Steelers 1970–1983 | Aufnahme: 1989\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 5× Pro Bowl, Defensive Player of the Year 1975\n🔥 57 Interceptions\n→ So dominant, dass die NFL wegen ihm die Regeln änderte (5-Yard-Regel)!",
    "Lynn Swann": "Position: WR | Steelers 1974–1982 | Aufnahme: 2001\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ Super-Bowl-MVP (X), 3× Pro Bowl\n🔥 Legendäre Catches im Super Bowl X\n→ Der eleganteste Receiver seiner Zeit.",
    "John Stallworth": "Position: WR | Steelers 1974–1987 | Aufnahme: 2002\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 3× Pro Bowl, 8.723 Receiving Yards, 63 TDs\n🔥 Big-Game-Receiver: In den Super Bowls immer da\n→ Bradshaws Lieblingsziel in den großen Spielen.",
    "Troy Polamalu": "Position: S | Steelers 2003–2014 | Aufnahme: 2020\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion\n⭐ 8× Pro Bowl, 4× First-Team All-Pro\n🔥 Defensive Player of the Year 2010, 32 Interceptions\n→ Der Safety, der den Spielzug roch, bevor er passierte.",
    "Jerome Bettis": "Position: RB | Steelers 1996–2005 | Aufnahme: 2015\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XL – in seiner Heimatstadt Detroit!)\n⭐ 6× Pro Bowl, 13.662 Rushing Yards\n🔥 Spitzname: 'The Bus'\n→ Der Bus rollte bis nach Hause – Super Bowl in Detroit zum Abschied.",
    "Rod Woodson": "Position: CB/S | Steelers 1987–1996 | Aufnahme: 2021\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XXXV mit den Ravens)\n⭐ 11× Pro Bowl, 6× First-Team All-Pro\n🔥 Defensive Player of the Year 1993, 71 Interceptions, 12 Defensive TDs (Rekord!)\n→ Der vielseitigste Defensive Back der Geschichte.",
    "Chuck Noll": "Position: Trainer | Steelers 1969–1991 | Aufnahme: 1993\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 4 Titel in 6 Jahren – die 70er-Dynastie\n🔥 209 Siege als Head Coach\n→ Der Architekt der Dynastie – 'The Emperor'.",
    "Joe Montana": "Position: QB | 49ers 1979–1992 | Aufnahme: 2000\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 3× Super-Bowl-MVP, 2× NFL MVP\n🔥 0 Interceptions in 4 Super Bowls!\n→ 'Joe Cool' – eiskalt in den größten Spielen.",
    "Jerry Rice": "Position: WR | 49ers 1985–2000 | Aufnahme: 2010\n\nWarum Hall of Fame?\n🏆 3× Super-Bowl-Champion\n⭐ 13× Pro Bowl, Super-Bowl-MVP\n🔥 22.895 Receiving Yards – NFL-REKORD!\n→ Der beste Receiver aller Zeiten. Punkt.",
    "Steve Young": "Position: QB | 49ers 1987–1999 | Aufnahme: 2005\n\nWarum Hall of Fame?\n🏆 3× Super-Bowl-Champion (1× als Starter, SB XXIX)\n⭐ 2× NFL MVP, Super-Bowl-MVP, 7× Pro Bowl\n🔥 33.124 Passing Yards + 4.239 Rushing Yards\n→ Der beste linkshändige QB der Geschichte.",
    "Ronnie Lott": "Position: S | 49ers 1981–1990 | Aufnahme: 2000\n\nWarum Hall of Fame?\n🏆 4× Super-Bowl-Champion\n⭐ 10× Pro Bowl, 63 Interceptions\n🔥 Ließ sich einen Finger amputieren, um weiterzuspielen!\n→ Härtester Safety aller Zeiten.",
    "Walter Payton": "Position: RB | Bears 1975–1987 | Aufnahme: 1993\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XX)\n⭐ 9× Pro Bowl, NFL MVP 1977\n🔥 16.726 Rushing Yards (damals Rekord!)\n→ 'Sweetness' – der kompletteste Running Back aller Zeiten.",
    "Dick Butkus": "Position: LB | Bears 1965–1973 | Aufnahme: 1979\n\nWarum Hall of Fame?\n⭐ 8× Pro Bowl, 2× Defensive Player of the Year\n🔥 22 Interceptions, 27 Fumble Recoveries\n→ Der furchteinflößendste Linebacker der Geschichte.",
    "Mike Singletary": "Position: LB | Bears 1981–1992 | Aufnahme: 1998\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XX)\n⭐ 10× Pro Bowl, 2× Defensive Player of the Year\n🔥 Das Herz der 85er-Bears\n→ 'Samurai Mike' – der Anführer der besten Defense aller Zeiten.",
    "Gale Sayers": "Position: RB | Bears 1965–1971 | Aufnahme: 1977\n\nWarum Hall of Fame?\n⭐ 4× Pro Bowl, Rookie of the Year 1965\n🔥 6 Touchdowns in EINEM Spiel (als Rookie!)\n→ Der 'Kansas Comet' – kurze Karriere, ewige Legende.",
    "Jim Brown": "Position: RB | Browns 1957–1965 | Aufnahme: 1971\n\nWarum Hall of Fame?\n⭐ 3× NFL MVP, 9× Pro Bowl\n🔥 8× Rushing-Titel in 9 Jahren, 12.312 Yards\n→ Von vielen der beste Footballer aller Zeiten – ging mit 29 in Rente.",
    "Otto Graham": "Position: QB | Browns 1946–1955 | Aufnahme: 1965\n\nWarum Hall of Fame?\n🏆 7× Meister (4 AAFC + 3 NFL)\n⭐ 5× Pro Bowl\n🔥 10 Endspiele in 10 Jahren – 7 gewonnen!\n→ Der erfolgreichste QB der Anfangszeit.",
    "Dan Marino": "Position: QB | Dolphins 1983–1999 | Aufnahme: 2005\n\nWarum Hall of Fame?\n⭐ 9× Pro Bowl, NFL MVP 1984\n🔥 5.084 Passing Yards 1984 – damals unglaublich! 61.361 Yards insgesamt\n→ Der beste reine Passer aller Zeiten – ohne Super-Bowl-Ring.",
    "Don Shula": "Position: Trainer | Dolphins 1970–1995 | Aufnahme: 1997\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion\n⭐ 347 Siege – NFL-REKORD!\n🔥 Perfekte Saison 1972 (17-0)!\n→ Der siegreichste Trainer der NFL-Geschichte.",
    "John Elway": "Position: QB | Broncos 1983–1998 | Aufnahme: 2004\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion\n⭐ Super-Bowl-MVP, 9× Pro Bowl\n🔥 'The Drive' 1987 – 98 Yards zum Ausgleich!\n→ Der Arm, der Denver groß machte.",
    "Terrell Davis": "Position: RB | Broncos 1995–2001 | Aufnahme: 2017\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion\n⭐ Super-Bowl-MVP, NFL MVP 1998\n🔥 2.008 Rushing Yards 1998 – die 2.000er-Marke!\n→ Migräne-Spiel im Super Bowl – trotzdem MVP. Legende.",
    "Barry Sanders": "Position: RB | Lions 1989–1998 | Aufnahme: 2004\n\nWarum Hall of Fame?\n⭐ 10× Pro Bowl, NFL MVP 1997\n🔥 15.269 Rushing Yards, 2.053 Yards 1997\n→ Der spektakulärste Läufer aller Zeiten – ging mit 30 in Rente.",
    "Calvin Johnson": "Position: WR | Lions 2007–2015 | Aufnahme: 2021\n\nWarum Hall of Fame?\n⭐ 6× Pro Bowl, 3× First-Team All-Pro\n🔥 1.964 Receiving Yards 2012 – NFL-REKORD!\n→ 'Megatron' – der körperlich dominanteste Receiver aller Zeiten.",
    "Brett Favre": "Position: QB | Packers 1992–2007 | Aufnahme: 2016\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XXXI)\n⭐ 3× NFL MVP in Folge (1995–97!), 11× Pro Bowl\n🔥 297 Spiele in Folge – der Eisenmann-Rekord!\n→ Der Gunslinger – 3 MVPs in Folge, das schafft keiner mehr.",
    "Bart Starr": "Position: QB | Packers 1956–1971 | Aufnahme: 1977\n\nWarum Hall of Fame?\n🏆 5× NFL-Meister, 2× Super-Bowl-Champion\n⭐ 2× Super-Bowl-MVP, 4× Pro Bowl\n🔥 Playoff-Bilanz: 9-1!\n→ Lombardis verlängerter Arm auf dem Feld.",
    "Vince Lombardi": "Position: Trainer | Packers 1959–1967 | Aufnahme: 1971\n\nWarum Hall of Fame?\n🏆 5× NFL-Meister, 2× Super-Bowl-Champion\n⭐ Die Trophäe trägt seinen Namen!\n🔥 'Winning isn't everything – it's the only thing.'\n→ Der Super-Bowl-Pokal heißt nach ihm – mehr muss man nicht sagen.",
    "Roger Staubach": "Position: QB | Cowboys 1969–1979 | Aufnahme: 1985\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion\n⭐ Super-Bowl-MVP, 6× Pro Bowl\n🔥 'Captain America' – der erste große Comeback-QB\n→ Durch ihn wurde der 'Hail Mary'-Pass berühmt.",
    "Troy Aikman": "Position: QB | Cowboys 1989–2000 | Aufnahme: 2006\n\nWarum Hall of Fame?\n🏆 3× Super-Bowl-Champion\n⭐ Super-Bowl-MVP, 6× Pro Bowl\n🔥 32.942 Passing Yards\n→ Der ruhige Anführer der 90er-Dynastie.",
    "Emmitt Smith": "Position: RB | Cowboys 1990–2002 | Aufnahme: 2010\n\nWarum Hall of Fame?\n🏆 3× Super-Bowl-Champion\n⭐ Super-Bowl-MVP, NFL MVP 1993, 8× Pro Bowl\n🔥 18.355 Rushing Yards – NFL-REKORD!\n→ Der ewige Rushing-König der NFL.",
    "Tom Landry": "Position: Trainer | Cowboys 1960–1988 | Aufnahme: 1990\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion\n⭐ 20 Saisons in Folge mit positiver Bilanz!\n🔥 29 Jahre Cowboys – der Mann mit dem Hut\n→ Der Architekt von 'America's Team'.",
    "Lawrence Taylor": "Position: LB | Giants 1981–1993 | Aufnahme: 1999\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion\n⭐ 3× Defensive Player of the Year, NFL MVP 1986 (als Verteidiger!)\n🔥 132,5 Sacks, 10× Pro Bowl\n→ Der einzige Verteidiger, der die Offense komplett verändert hat.",
    "Peyton Manning": "Position: QB | Colts 1998–2011 | Aufnahme: 2021\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion (1× Colts)\n⭐ 5× NFL MVP – REKORD!, 14× Pro Bowl\n🔥 71.940 Passing Yards\n→ 'Der Sheriff' – 5 MVPs, so viele wie kein anderer.",
    "Marvin Harrison": "Position: WR | Colts 1996–2008 | Aufnahme: 2016\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XLI)\n⭐ 8× Pro Bowl, 143 Catches 2002 (damals Rekord!)\n🔥 14.580 Receiving Yards\n→ Der zuverlässigste Receiver der Manning-Ära.",
    "Johnny Unitas": "Position: QB | Colts 1956–1972 | Aufnahme: 1979\n\nWarum Hall of Fame?\n🏆 3× NFL-Meister, 1× Super-Bowl-Champion (V)\n⭐ 3× NFL MVP, 10× Pro Bowl\n🔥 47 Spiele in Folge mit TD-Pass (damals Rekord!)\n→ Der Urvater des modernen Quarterbacks.",
    "Reggie White": "Position: DE | Eagles 1985–1992 | Aufnahme: 2006\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XXXI mit den Packers)\n⭐ 13× Pro Bowl, 2× Defensive Player of the Year\n🔥 198 Sacks!\n→ Der 'Minister of Defense' – der dominanteste Pass-Rusher seiner Zeit.",
    "Brian Dawkins": "Position: S | Eagles 1996–2008 | Aufnahme: 2018\n\nWarum Hall of Fame?\n⭐ 9× Pro Bowl, 4× First-Team All-Pro\n🔥 37 Interceptions, 26 Sacks – als Safety!\n→ 'Weapon X' – das Herz der Eagles-Defense.",
    "Deion Sanders": "Position: CB | Falcons 1989–1993 | Aufnahme: 2011\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion (mit 49ers & Cowboys)\n⭐ 8× Pro Bowl, Defensive Player of the Year 1994\n🔥 53 Interceptions + Return-TDs en masse\n→ 'Prime Time' – spielte sogar in Super Bowl UND World Series!",
    "Randy Moss": "Position: WR | Vikings 1998–2004 | Aufnahme: 2018\n\nWarum Hall of Fame?\n⭐ 6× Pro Bowl, 4× First-Team All-Pro\n🔥 23 Touchdowns 2007 – NFL-REKORD!\n→ 'You got Mossed!' – der spektakulärste Deep-Ball-Receiver aller Zeiten.",
    "Ray Lewis": "Position: LB | Ravens 1996–2012 | Aufnahme: 2018\n\nWarum Hall of Fame?\n🏆 2× Super-Bowl-Champion\n⭐ Super-Bowl-MVP, 2× Defensive Player of the Year\n🔥 13× Pro Bowl, 1.562 Tackles\n→ Der Anführer – die beste Defense der 2000er.",
    "Ed Reed": "Position: S | Ravens 2002–2012 | Aufnahme: 2019\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XLVII)\n⭐ Defensive Player of the Year 2004, 9× Pro Bowl\n🔥 64 Interceptions, 1.590 INT-Return-Yards (Rekord!)\n→ Der Ballhawk – keiner las den QB besser.",
    "Joe Namath": "Position: QB | Jets 1965–1976 | Aufnahme: 1985\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (III)\n⭐ Super-Bowl-MVP\n🔥 'Broadway Joe' – der erste Football-Superstar\n→ 'Wir werden den Super Bowl gewinnen!' – und er hielt Wort.",
    "LaDainian Tomlinson": "Position: RB | Chargers 2001–2009 | Aufnahme: 2017\n\nWarum Hall of Fame?\n⭐ NFL MVP 2006, 5× Pro Bowl\n🔥 31 Touchdowns 2006 – NFL-REKORD!\n→ 'LT' – 31 TDs in einer Saison, das schafft keiner mehr.",
    "Junior Seau": "Position: LB | Chargers 1990–2002 | Aufnahme: 2015\n\nWarum Hall of Fame?\n⭐ 12× Pro Bowl, 6× First-Team All-Pro\n🔥 1.846 Tackles\n→ Das Herz von San Diego – über ein Jahrzehnt der Anführer.",
    "Howie Long": "Position: DE | Raiders 1981–1993 | Aufnahme: 2000\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XVIII)\n⭐ 8× Pro Bowl, 84 Sacks\n🔥 Danach als TV-Experte genauso erfolgreich\n→ Der Dominator der Raiders-Line.",
    "Marcus Allen": "Position: RB | Raiders 1982–1992 | Aufnahme: 2003\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XVIII)\n⭐ Super-Bowl-MVP, NFL MVP 1985\n🔥 12.279 Rushing Yards, 145 TDs\n→ Der eleganteste Läufer der Raiders.",
    "Bruce Smith": "Position: DE | Bills 1985–1999 | Aufnahme: 2009\n\nWarum Hall of Fame?\n⭐ 11× Pro Bowl, 2× Defensive Player of the Year\n🔥 200 Sacks – NFL-REKORD!\n→ Der ewige Sack-König.",
    "Jim Kelly": "Position: QB | Bills 1986–1996 | Aufnahme: 2002\n\nWarum Hall of Fame?\n⭐ 5× Pro Bowl, 'K-Gun'-Offense\n🔥 4× Super-Bowl-Teilnahmen in Folge!\n→ 4× in Folge im Super Bowl – das schafft nie wieder einer.",
    "Kurt Warner": "Position: QB | Rams 1998–2003 | Aufnahme: 2017\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XXXIV)\n⭐ 2× NFL MVP, Super-Bowl-MVP\n🔥 Vom Supermarkt in den Super Bowl!\n→ Die größte Underdog-Story der NFL.",
    "Marshall Faulk": "Position: RB | Rams 1999–2005 | Aufnahme: 2011\n\nWarum Hall of Fame?\n🏆 Super-Bowl-Champion (XXXIV)\n⭐ NFL MVP 2000, 3× Offensive Player of the Year\n🔥 19.154 Yards from Scrimmage\n→ Das Schweizer Taschenmesser der 'Greatest Show on Turf'.",
    "Tony Gonzalez": "Position: TE | Chiefs 1997–2008 | Aufnahme: 2019\n\nWarum Hall of Fame?\n⭐ 14× Pro Bowl, 6× First-Team All-Pro\n🔥 15.127 Receiving Yards – Rekord für Tight Ends!\n→ Der beste Tight End aller Zeiten.",
}

# V241: Top Prospects 2027 - Konsens aus Kiper (ESPN), Brugler, Athlon & DraftCountdown (Stand Nov 2026)!
# Keine Live-API dafuer: ESPNs Draft-Endpunkt liefert nur Picks vom letzten Draft, keine Prospects! Darum kuratierter Snapshot - bei neuen Boards einfach hier updaten!
_TOP_PROSPECTS_2027 = [
    ("Jeremiah Smith", "WR", "Ohio State"),
    ("Drew Mestemaker", "QB", "Oklahoma State"),
    ("Colin Simmons", "EDGE", "Texas"),
    ("Leonard Moore", "CB", "Notre Dame"),
    ("Dylan Stewart", "EDGE", "South Carolina"),
    ("Darian Mensah", "QB", "Miami (FL)"),
    ("CJ Carr", "QB", "Notre Dame"),
    ("Chris Cole", "LB", "Georgia"),
    ("Charlie Becker", "WR", "Indiana"),
    ("Xavier Gilliam", "DT", "Tennessee"),
]
async def draft_preview_cmd(update, ctx):
    # V214: NFL Draft-Vorschau! Reihenfolge nach AKTUELLEM Tabellenstand (schlechtestes Team zuerst)!
    # NFL Draft 2027: 29.04.-01.05.2027, Washington D.C. (National Mall)!
    try:
        target = update.message or update.callback_query.message
        uid = update.effective_user.id if update.effective_user else 0
        from datetime import date as _d214
        _today = _d214.today()
        _draft = _d214(2027, 4, 29)
        _days = (_draft - _today).days
        _is_live = _days <= 28  # 4 Wochen vorher = "echt", sonst Vorschau!
        _title = "🏆 NFL Draft 2027" if _is_live else "🏆 NFL Draft 2027 – Vorschau 👀"
        lines = [_title, "", "📍 Washington D.C. – National Mall", "📅 29. April – 1. Mai 2027"]
        if _days > 0:
            lines.append(f"⏳ Noch {_days} Tage bis zum Draft!")
        elif _days == 0:
            lines.append("⏳ Draft ist HEUTE! 🎉")
        else:
            lines.append("⏳ Draft läuft / vorbei!")
        lines.append("")
        if not _is_live:
            lines.append("👀 Vorschau-Modus: Reihenfolge nach aktuellem Tabellenstand!")
            lines.append("Echte Reihenfolge steht erst nach Saisonende + Playoffs fest")
            lines.append("(Playoff-Teams picken hinten, Super-Bowl-Sieger zuletzt)!")
            lines.append("")
        # Draft-Reihenfolge: alle NFL-Teams, schlechtestes zuerst!
        # V215: NICHT mehr aus espn_standings (Division-Bloecke! -> Eagles "2-7", Chargers "1-8" waren falsch)!
        # Jetzt: EIN Fetch der reinen Standings, nur Overall-Block (overallwins/overalllosses)!
        _order = []
        try:
            _recs = _v215_nfl_overall_records() or {}
            for _disp, (_W, _L) in _recs.items():
                _short = _disp
                _order.append((_disp, _short, "", _W, _L, 0, ""))
            # Sort: wenigste Wins zuerst, dann meiste Losses! Gleichstand = noch nicht fix!
            _order.sort(key=lambda x: (x[3], -x[4]))
        except: _order = []
        if not _order:
            try:
                _divs = espn_standings("NFL") or {}
                for _dv, _rows in _divs.items():
                    for _r in _rows:
                        _order.append(_r)
                _order.sort(key=lambda x: (x[3], -x[4]))
            except: _order = []
        if _order:
            lines.append("📋 Draft-Reihenfolge (Top 10, aktuell):")
            for i, (disp, short, abbr, W, L, T, streak) in enumerate(_order[:10], 1):
                _rec = f"{W}-{L}" + (f"-{T}" if T else "")
                lines.append(f"{i}. {short} ({_rec})")
            lines.append("")
            # Favoriten-Pick: Wo picken DEINE NFL-Favoriten?
            try:
                _favs = favs_for(uid) if uid else []
                for _f in _favs:
                    if " (" not in _f: continue
                    _nm = _f.split(" (")[0].strip()
                    _lg2 = _f.split(" (")[-1].replace(")", "").strip()
                    if _lg2 != "NFL": continue
                    for i, (disp2, short2, abbr2, W2, L2, T2, streak2) in enumerate(_order, 1):
                        _dl = (disp2 or "").lower()
                        if _nm.lower() in _dl or _dl in _nm.lower() or (short2 or "").lower() in _nm.lower():
                            lines.append(f"⭐ Dein Pick: {_nm} – aktuell Position {i}!")
                            break
            except: pass
        else:
            lines.append("😅 Draft-Reihenfolge grad nicht verfügbar (ESPN)!")
        # V241: Top Prospects 2027! Wer sind die heissen Namen fuer den Draft?
        lines.append("🌟 Top Prospects 2027 (Top 10):")
        for _i241, (_nm241, _pos241, _sch241) in enumerate(_TOP_PROSPECTS_2027, 1):
            lines.append(f"{_i241}. {_nm241} – {_pos241}, {_sch241}")
        lines.append("Stand: Nov 2026 (Konsens: Kiper, Brugler & Co.) – Ranglisten ändern sich bis zum Draft noch!")
        lines.append("")
        _kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        _m = await target.reply_text("\n".join(lines), reply_markup=_with_close(_kb))
        try: _chain_add(uid, _m.message_id)
        except: pass
    except Exception:
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Draft-Vorschau konnte grad nicht geladen werden!", reply_markup=small_kb())
        except: pass



# ===== V243: NERD-MODUS Handler - Option 1: EIN Fenster, das sich umbaut! =====
def _nerd_clear_lists(ctx):
    # V242: Nerd-Zahlenlisten sind exklusiv! Sonst klaut eine alte Liste (Next Games etc.) die getippte Zahl!
    for _k in ("my_live_list", "next_live_list", "next_games_list", "results_list", "live_finals_list", "top10_list", "tables_team_list", "await_live_stats_pick", "nerd_teams_list", "nerd_hof_list"):
        try: ctx.user_data[_k] = None
        except: pass

async def _nerd_show(update, ctx, text, kb):
    # V243: Option 1 - EIN Nerd-Fenster, das sich umbaut!
    # Button-Tap -> _cb_edit (Hauptmenue = neues Fenster, sonst gleiches Fenster umbauen - wie bei allen anderen Flows)!
    # Getippte Zahl -> letztes Nerd-Fenster umbauen + Zahl loeschen (Chat bleibt sauber)!
    try:
        if update.callback_query is not None:
            _m = await _cb_edit(update, text, kb)
            try:
                if _m is not None: ctx.user_data["nerd_window_id"] = _m.message_id
            except: pass
            return True
    except Exception:
        pass
    try:
        if update.message is not None:
            _uid = update.effective_user.id if update.effective_user else 0
            _wid = None
            try: _wid = ctx.user_data.get("nerd_window_id")
            except: pass
            if _wid:
                try:
                    await ctx.bot.edit_message_text(chat_id=_uid, message_id=int(_wid), text=text, reply_markup=_with_close(kb))
                    try: await ctx.bot.delete_message(chat_id=_uid, message_id=update.message.message_id)
                    except: pass
                    return True
                except Exception as _e243:
                    if "not modified" in str(_e243).lower():
                        try: await ctx.bot.delete_message(chat_id=_uid, message_id=update.message.message_id)
                        except: pass
                        return True
            # Fallback: altes Fenster weg/geloescht -> neues Fenster + Zahl loeschen!
            try:
                _m2 = await _cb_edit(update, text, kb)
                try:
                    if _m2 is not None: ctx.user_data["nerd_window_id"] = _m2.message_id
                except: pass
                try: await ctx.bot.delete_message(chat_id=_uid, message_id=update.message.message_id)
                except: pass
                return True
            except Exception:
                pass
    except Exception:
        pass
    return False

async def nerd_cmd(update, ctx):
    try:
        _kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 NFL Regeln", callback_data="nerd_rules")],
            [InlineKeyboardButton("🏈 NFL Teams", callback_data="nerd_teams")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        await _nerd_show(update, ctx, "🧠 Nerd-Modus\nDein Lexikon für US-Sport – Regeln, Teams & Legenden!\n\n📖 NFL Regeln – so funktioniert Football\n🏈 NFL Teams – alle 32 Teams + Hall of Famers\n\nNBA, NHL, MLB & NCAAF kommen in Phase 2!", _kb)
    except Exception:
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Nerd-Modus konnte grad nicht geladen werden!", reply_markup=small_kb())
        except: pass

async def nerd_rules_cmd(update, ctx):
    try:
        _kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏈 NFL Teams", callback_data="nerd_teams")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        await _nerd_show(update, ctx, NFL_RULES_TEXT, _kb)
    except Exception:
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Regeln konnten grad nicht geladen werden!", reply_markup=small_kb())
        except: pass

async def nerd_teams_cmd(update, ctx):
    try:
        _nerd_clear_lists(ctx)
        _keys = list(NFL_TEAMS_NERD.keys())
        ctx.user_data["nerd_teams_list"] = _keys
        lines = ["🏈 NFL Teams – alle 32!", "Tippe die Zahl für dein Team!", ""]
        _last_div = ""
        for _i, _k in enumerate(_keys, 1):
            _t = NFL_TEAMS_NERD[_k]
            if _t["div"] != _last_div:
                _last_div = _t["div"]
                lines.append(f"{_last_div}:")
            lines.append(f"{_i}. {_t['name']}")
        _kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧠 Nerd-Modus", callback_data="nerd")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        await _nerd_show(update, ctx, "\n".join(lines), _kb)
    except Exception:
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Team-Liste konnte grad nicht geladen werden!", reply_markup=small_kb())
        except: pass

async def nerd_team_cmd(update, ctx, key):
    try:
        _t = NFL_TEAMS_NERD.get(key)
        if not _t:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Team nicht gefunden!", reply_markup=small_kb()); return
        lines = [f"🏈 {_t['name']}", f"📍 {_t['city']} | 🏟️ {_t['stadion']}", f"📅 Gegründet: {_t['gegr']}", f"🏆 {_t['titel']}", f"🎨 Farben: {_t['farben']}", f"📂 Division: {_t['div']}", "", "📖 Geschichte:", _t["geschichte"]]
        _kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Hall of Famers", callback_data=f"nerd_hof:{key}")],
            [InlineKeyboardButton("🏈 Alle Teams", callback_data="nerd_teams")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        await _nerd_show(update, ctx, "\n".join(lines), _kb)
    except Exception:
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Team-Seite konnte grad nicht geladen werden!", reply_markup=small_kb())
        except: pass

async def nerd_hof_cmd(update, ctx, key):
    try:
        _nerd_clear_lists(ctx)
        _t = NFL_TEAMS_NERD.get(key)
        _names = NFL_HOF.get(key) or []
        if not _t or not _names:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Für dieses Team gibt's noch keine HOF-Liste!", reply_markup=small_kb()); return
        ctx.user_data["nerd_hof_list"] = {"team": key, "names": [n for n, p in _names]}
        lines = [f"⭐ Hall of Famers – {_t['name']}", "Tippe die Zahl für die Story!", ""]
        for _i, (_nm, _pos) in enumerate(_names, 1):
            lines.append(f"{_i}. {_nm} – {_pos}")
        _kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏈 Team-Seite", callback_data=f"nerd_team:{key}")],
            [InlineKeyboardButton("🏈 Alle Teams", callback_data="nerd_teams")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        await _nerd_show(update, ctx, "\n".join(lines), _kb)
    except Exception:
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 HOF-Liste konnte grad nicht geladen werden!", reply_markup=small_kb())
        except: pass

async def nerd_hof_detail_cmd(update, ctx, key, idx):
    try:
        _t = NFL_TEAMS_NERD.get(key)
        _names = NFL_HOF.get(key) or []
        if idx < 0 or idx >= len(_names):
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Legende nicht gefunden!", reply_markup=small_kb()); return
        _nm, _pos = _names[idx]
        _det = NFL_HOF_DETAILS.get(_nm)
        if _det:
            _txt = f"⭐ {_nm} – Hall of Fame\n{_det}"
        else:
            _txt = f"⭐ {_nm} – Hall of Fame\nPosition: {_pos} | {_t['name'] if _t else ''}\n\nAusführliche Story folgt in Phase 2!"
        _kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Alle Hall of Famers", callback_data=f"nerd_hof:{key}")],
            [InlineKeyboardButton("🏈 Team-Seite", callback_data=f"nerd_team:{key}")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        await _nerd_show(update, ctx, _txt, _kb)
    except Exception:
        try:
            target = update.message or update.callback_query.message
            await target.reply_text("😅 Legenden-Story konnte grad nicht geladen werden!", reply_markup=small_kb())
        except: pass


async def on_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data=q.data
    # V249: Auto-Schliessen FIX - zentral hier, weil die meisten Listen per reply_text direkt schicken und den _cb_edit-Hook aus V248 nie sehen! Klick aus Hauptmenue -> alte Fenster zu! Klick aus Meine Woche (News/Next/Tabellen/CFP) -> alte Fenster zu, Meine Woche bleibt! Detail-Fenster per Zahl + Back bleiben unberuehrt (kein Callback aus Hauptmenue)!
    try:
        if data not in ("close", "close_all", "back"):
            _qm249 = q.message if q else None
            _qt249 = (_qm249.text or "") if _qm249 is not None and getattr(_qm249, "text", None) else ""
            _uid249 = update.effective_user.id if update.effective_user else 0
            if _qt249.startswith("Willkommen beim USA Sport Radar"):
                await _autoclose_prev(ctx, _uid249)
            elif _qt249.startswith("📅 Meine Woche") and (data.split(":")[0] if data else "") in ("news", "next", "tables", "cfp_top25"):
                await _autoclose_prev(ctx, _uid249, keep_mid=_qm249.message_id)
    except: pass
    if data=="myweek":
        await myweek_cmd(update, ctx); return
    if data=="myweek_refresh":
        await myweek_cmd(update, ctx, force=True); return
    # V94: Merken, in welcher Funktion man grade ist - damit Hilfe passend dazu kommt!
    try:
        _sec_map = {"top10": "top10", "tables": "tables", "next": "next", "live": "live", "results": "results", "settings": "settings", "notif": "notif", "fav": "fav", "injur": "injuries", "game_info": "game_info"}
        for _k, _v in _sec_map.items():
            if data.startswith(_k): ctx.user_data["last_section"] = _v; break
        if data == "back": ctx.user_data["last_section"] = "main"
    except: pass
    if data=="close_all":
        # V167: BEWUSST alles zu! Nur aus Hauptmenue erreichbar! Hauptmenue selbst bleibt IMMER da!
        try:
            _uid_c = update.effective_user.id if update.effective_user else 0
            await _chain_delete_all(ctx, _uid_c, None)
        except: pass
        try: await q.answer("🧹 Alle Fenster geschlossen!")
        except: pass
        return
    if data=="close":
        # V95: Hauptmenue nach /start bleibt IMMER da - nie loeschen!
        try:
            if _is_main_msg(q.message): return
        except: pass
        # V167: NUR dieses Fenster zu! Nicht die ganze Kette!
        # Vorher: _chain_delete_all hat Next Games + Top 10 + alles dazwischen mit geloescht!
        # Jetzt: nur geklickte Nachricht loeschen, Rest bleibt offen!
        try:
            _uid_c = update.effective_user.id if update.effective_user else 0
            _chain_remove(_uid_c, q.message.message_id if q.message else None)
        except: pass
        # V243: Nerd-Fenster-ID loeschen, damit eine spaeter getippte Zahl nicht ins tote Fenster editiert!
        try:
            if ctx.user_data.get("nerd_window_id") == (q.message.message_id if q.message else None):
                ctx.user_data["nerd_window_id"] = None
        except: pass
        try: await q.message.delete()
        except:
            try: await q.message.edit_text("✖️ Fenster geschlossen!\n\nDein Hauptmenü nach /start ist noch da! 👆", reply_markup=None)
            except: pass
        # V201: Zahl zum Fenster mitloeschen! Wenn das Fenster per Zahl geoeffnet wurde (z.B. '1' -> Final Stats), fliegt die Zahl gleich mit weg!
        try:
            _mid_c = q.message.message_id if q.message else None
            _num_mid = _CLOSE_NUM_MAP.pop((_uid_c, int(_mid_c)), None) if _mid_c else None
            if _num_mid:
                try: await ctx.bot.delete_message(chat_id=_uid_c, message_id=int(_num_mid))
                except: pass
        except: pass
    elif data.startswith("finalstats:"):
        # V106: Final Stats Button!
        try:
            _parts = data.split(":"); _eid = _parts[1]; _lg = _parts[2] if len(_parts)>2 else ""
            _uid = update.effective_user.id if update.effective_user else 0
            _load = await ctx.bot.send_message(chat_id=_uid, text="⏳ Spiel wird zusammengefasst...\nEinen Moment, ich hol die Stats von ESPN!")
            _txt = get_final_stats_text(_eid, _lg) if _lg in LEAGUES else ""
            if _txt:
                try: await ctx.bot.delete_message(chat_id=_uid, message_id=_load.message_id)
                except: pass
                _fs_rows = []
                if _lg in LEAGUES:
                    _fs_rows.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{_eid}:{_lg}")])
                _fs_rows.extend(_yt_buttons_for_game(_eid, _lg, _txt))
                _fs_rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
                _fs_del_kb = InlineKeyboardMarkup(_fs_rows)
                await ctx.bot.send_message(chat_id=_uid, text=_txt, reply_markup=_fs_del_kb)
            else:
                # Keine Stats da -> fragen, ob in 5 Min nochmal schauen!
                _kb2 = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, nochmal schauen!", callback_data=f"finalstats_retry:{_eid}:{_lg}"), InlineKeyboardButton("❌ Nein, danke!", callback_data=f"finalstats_no:{_eid}:{_lg}")]])
                try: await ctx.bot.edit_message_text(chat_id=_uid, message_id=_load.message_id, text="😅 Grad noch keine Stats vorhanden!\nESPN ist noch langsam!\nSoll ich in 5 Min nochmal schauen?", reply_markup=_kb2)
                except: pass
        except: pass
    elif data.startswith("expert_stats:"):
        # V201: Experten-Stats fuer alle Ligen!
        try:
            _parts = data.split(":"); _eid = _parts[1]; _lg = _parts[2] if len(_parts)>2 else ""
            _uid = update.effective_user.id if update.effective_user else 0
            # V201: Experten-Stats jetzt fuer alle Ligen!
            _load = await ctx.bot.send_message(chat_id=_uid, text="🧠 Experten-Stats werden berechnet...\nEinen Moment, ich hol die Stats von ESPN!")
            _txt = get_expert_stats_text(_eid, _lg)
            if _txt:
                # V162-FIX: _ekb war in V161 versehentlich mitgeloescht worden (Nachrichten-loeschen-Zeile) -> NameError -> Lade-Nachricht weg, nix kam! Jetzt wieder definiert, nur Fenster schliessen!
                _ekb = InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
                try: await ctx.bot.delete_message(chat_id=_uid, message_id=_load.message_id)
                except: pass
                try:
                    _me = await ctx.bot.send_message(chat_id=_uid, text=_txt, reply_markup=_ekb)
                    # V201: Experten-Fenster in Kette, sonst bleibt es bei 'Alle schliessen' stehen!
                    try: _chain_add(_uid, _me.message_id)
                    except: pass
                except Exception as _e:
                    # Nie lautlos verschwinden: wenn Senden klappt nicht, Lade-Nachricht editieren statt loeschen!
                    try: await ctx.bot.edit_message_text(chat_id=_uid, message_id=_load.message_id, text=_txt, reply_markup=_ekb)
                    except: pass
                    logger.warning(f"Expert-Stats send failed: {_e}")
            else:
                try: await ctx.bot.edit_message_text(chat_id=_uid, message_id=_load.message_id, text="😅 Grad keine Experten-Stats da!\nESPN hat noch keine Drives für das Spiel!\nVersuch es nach dem Spiel nochmal!")
                except: pass
        except Exception as _e2:
            logger.warning(f"Expert-Stats handler failed: {_e2}")
            try: await ctx.bot.edit_message_text(chat_id=_uid, message_id=_load.message_id, text="😅 Experten-Stats konnten grad nicht geladen werden!\nVersuch es gleich nochmal!")
            except: pass
    elif data.startswith("finalstats_retry:"):
        try:
            _parts = data.split(":"); _eid = _parts[1]; _lg = _parts[2] if len(_parts)>2 else ""
            _uid = update.effective_user.id if update.effective_user else 0
            # Alte Frage löschen!
            try: await q.message.delete()
            except: pass
            _load2 = await ctx.bot.send_message(chat_id=_uid, text="⏳ Alles klar, ich schau in 5 Min nochmal!")
            # In 5 Min nochmal: Job planen!
            try:
                if ctx.job_queue:
                    ctx.job_queue.run_once(finalstats_retry_job, 300, data={"uid": _uid, "eid": _eid, "lg": _lg, "mid": int(_load2.message_id)}, name=f"finalstats_retry_{_eid}_{_load2.message_id}")
            except: pass
        except: pass
    elif data.startswith("finalstats_no:"):
        try: await q.message.delete()
        except:
            try: await q.message.edit_text("❌ Ok, keine Stats!\n\nTippe /start für ein neues Fenster!")
            except: pass
    elif data.startswith("results_finalstats:"):
        try:
            _pp = data.split(":"); _lg2 = _pp[1]; _eid2 = _pp[2]
            _uid2 = update.effective_user.id if update.effective_user else 0
            _load = await ctx.bot.send_message(chat_id=_uid2, text="⏳ Spiel wird zusammengefasst...\nEinen Moment, ich hol die Stats von ESPN!")
            _txt2 = get_final_stats_text(_eid2, _lg2) if _lg2 in LEAGUES else ""
            if _txt2:
                try: await ctx.bot.delete_message(chat_id=_uid2, message_id=_load.message_id)
                except: pass
                _del_rows2 = []
                if _lg2 in LEAGUES:
                    _del_rows2.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{_eid2}:{_lg2}")])
                _del_rows2.extend(_yt_buttons_for_game(_eid2, _lg2, _txt2))
                _del_rows2.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
                _del_kb = InlineKeyboardMarkup(_del_rows2)
                await ctx.bot.send_message(chat_id=_uid2, text=_txt2, reply_markup=_del_kb)
            else:
                _kb2 = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, nochmal schauen!", callback_data=f"finalstats_retry:{_eid2}:{_lg2}"), InlineKeyboardButton("❌ Nein, danke!", callback_data=f"finalstats_no:{_eid2}:{_lg2}")]])
                try: await ctx.bot.edit_message_text(chat_id=_uid2, message_id=_load.message_id, text="😅 Grad noch keine Stats vorhanden!\nESPN ist noch langsam!\nSoll ich in 5 Min nochmal schauen?", reply_markup=_kb2)
                except: pass
        except: pass
    # V227: next_live_league / next_live_list RAUS - geht jetzt über Next Games Heute/Morgen + Zahl!
    elif data.startswith("next_live_pick:"):
        _pp = data.split(":"); await next_live_pick_cmd(update, ctx, _pp[1], _pp[2])
    elif data.startswith("next_live_toggle:"):
        _pp = data.split(":"); _lg3 = _pp[1]; _eid3 = _pp[2]; _kind3 = _pp[3]
        set_oneoff_live_toggle(update.effective_user.id, _eid3, _kind3)
        await next_live_pick_cmd(update, ctx, _lg3, _eid3, expanded235=True)  # V235: Nach Toggle aufgeklappt bleiben!
    elif data.startswith("next_live_expand:"):
        # V235: Buttons aufklappen!
        _pp = data.split(":"); await next_live_pick_cmd(update, ctx, _pp[1], _pp[2], expanded235=True)
    elif data.startswith("next_live_collapse:"):
        # V235: Buttons wieder einklappen!
        _pp = data.split(":"); await next_live_pick_cmd(update, ctx, _pp[1], _pp[2], expanded235=False)
    elif data.startswith("next_live_remove:"):
        # V213: Fertiges Spiel aus "Meine Live-Spiele" werfen!
        _pp = data.split(":"); _eid3 = _pp[2]
        try:
            _s213 = load_settings(); _s213.get(str(update.effective_user.id), {}).get("oneoff_live", {}).pop(str(_eid3), None); save_settings(_s213)
        except: pass
        try: await q.message.edit_text("✅ Raus aus der Liste! 🗑️\n\nTippe /start für ein neues Fenster!")
        except: pass
        # V237: Zahl zum Fenster mitloeschen - wie bei 'close'/'back'!
        try:
            _uid237r = update.effective_user.id if update.effective_user else 0
            _mid237r = q.message.message_id if q.message else None
            _num237r = _CLOSE_NUM_MAP.pop((_uid237r, int(_mid237r)), None) if _mid237r else None
            if _num237r:
                try: await ctx.bot.delete_message(chat_id=_uid237r, message_id=int(_num237r))
                except: pass
        except: pass
    elif data.startswith("live_clean_yes:"):
        _eid = data.split(":")[1]; _uid = update.effective_user.id if update.effective_user else 0
        _ids = list(_LIVE_MSG_IDS.get((_uid, str(_eid)), []))
        for _mid in _ids:
            try: await ctx.bot.delete_message(chat_id=_uid, message_id=_mid)
            except: pass
        _LIVE_MSG_IDS.pop((_uid, str(_eid)), None)
        try: await q.message.edit_text("✅ Live-Nachrichten gelöscht! Sauberer Chat!\n\nTippe /start für ein neues Fenster!")
        except: pass
    elif data.startswith("live_clean_no:"):
        _eid = data.split(":")[1]; _uid = update.effective_user.id if update.effective_user else 0
        _LIVE_MSG_IDS.pop((_uid, str(_eid)), None)
        try: await q.message.edit_text("❌ Ok, bleibt alles da!\n\nTippe /start für ein neues Fenster!")
        except: pass
    elif data=="back":
        # V95: Zurück im Fenster = Fenster loeschen, Hauptmenue nach /start bleibt oben! Nicht Hauptmenue doppelt machen!
        try:
            if _is_main_msg(q.message): return
        except: pass
        # V237: Zahl zum Fenster mitloeschen - wie bei 'close'! Vorher blieb die getippte Zahl (z.B. '6') bei Zurueck fuer immer stehen!
        try:
            _uid237 = update.effective_user.id if update.effective_user else 0
            _chain_remove(_uid237, q.message.message_id if q.message else None)
        except: pass
        # V243: Nerd-Fenster-ID loeschen, damit eine spaeter getippte Zahl nicht ins tote Fenster editiert!
        try:
            if ctx.user_data.get("nerd_window_id") == (q.message.message_id if q.message else None):
                ctx.user_data["nerd_window_id"] = None
        except: pass
        try: await q.message.delete()
        except:
            try: await q.message.edit_text("⬅️ Zurück zum Hauptmenü!\n\nDein Hauptmenü nach /start ist noch da! 👆", reply_markup=None)
            except: pass
        try:
            _mid237 = q.message.message_id if q.message else None
            _num237 = _CLOSE_NUM_MAP.pop((_uid237, int(_mid237)), None) if _mid237 else None
            if _num237:
                try: await ctx.bot.delete_message(chat_id=_uid237, message_id=int(_num237))
                except: pass
        except: pass
    elif data=="help":
        _sec = ""
        try: _sec = ctx.user_data.get("last_section", "main") or "main"
        except: _sec = "main"
        # V97: Hilfe im HAUPTMENUE = IMMER grosse Hilfe (HELP_TEXT)! Kleine Kontext-Hilfe NUR wenn man wirklich IN einem Fenster ist!
        _from_main = False
        try: _from_main = _is_main_msg(q.message)
        except: _from_main = False
        if _from_main:
            # V134: Hilfe = Kategorien, nicht mehr Batzen! Wähl nur, was du wissen willst!
            _hkb = _help_cats_kb()
            await q.message.reply_text("❓ Hilfe - Was willst du wissen?\n\nTippe eine Kategorie an - nur das Thema, kein Batzen Text!", reply_markup=_hkb)
        elif _sec in HELP_SHORT:
            _hkb = InlineKeyboardMarkup([[InlineKeyboardButton("📖 Alle Hilfe-Kategorien", callback_data="help_cats")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
            await q.message.edit_text(HELP_SHORT[_sec], reply_markup=_hkb)
        else:
            await q.message.edit_text("❓ Hilfe - Was willst du wissen?\n\nTippe eine Kategorie an - nur das Thema, kein Batzen Text!", reply_markup=_help_cats_kb())
    elif data.startswith("help_cat:"):
        _k=data.split(":")[1]; _txt=HELP_CATS.get(_k,"❓ Hilfe\n\nTippe eine Kategorie an!")
        _hkb2=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Hilfe", callback_data="help_cats")],[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
        try: await q.message.edit_text(_txt, reply_markup=_hkb2)
        except: await q.message.reply_text(_txt, reply_markup=_hkb2)
    elif data in ("help_all", "help_cats"):
        # V251: Riesen-Fenster ist weg! Ganze Hilfe = Kategorien-Menue!
        try: await q.message.edit_text("❓ Hilfe - Was willst du wissen?\n\nTippe eine Kategorie an - nur das Thema, kein Batzen Text!", reply_markup=_help_cats_kb())
        except:
            try: await q.message.reply_text("❓ Hilfe - Was willst du wissen?\n\nTippe eine Kategorie an - nur das Thema, kein Batzen Text!", reply_markup=_help_cats_kb())
            except: pass
    elif data=="top10": await top10_cmd(update, ctx)
    elif data=="news": await news_cmd(update, ctx)
    elif data=="news_league_expand":
        _uid3=update.effective_user.id if update.effective_user else 0; set_news_league_open(_uid3, not get_news_league_open(_uid3)); await news_cmd(update, ctx)
    elif data.startswith("news_league_toggle:"):
        _uid2=update.effective_user.id if update.effective_user else 0
        _pp2=data.split(":")
        if len(_pp2)>=2:
            _lg2=_pp2[1]; _cur2=get_league_breaking_map(_uid2).get(_lg2, True); set_league_breaking_league(_uid2, _lg2, not _cur2)
        else:
            _cur=get_league_breaking(_uid2); set_league_breaking(_uid2, not _cur)
        await news_cmd(update, ctx)
    elif data=="news_league_menu": await news_league_menu_cmd(update, ctx)
    elif data.startswith("news_league:"): await news_league_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("news_team:"): await news_team_cmd(update, ctx, int(data.split(":")[1]))
    elif data == "draft_preview": await draft_preview_cmd(update, ctx)
    elif data == "nerd": await nerd_cmd(update, ctx)
    elif data == "nerd_rules": await nerd_rules_cmd(update, ctx)
    elif data == "nerd_teams": await nerd_teams_cmd(update, ctx)
    elif data.startswith("nerd_team:"): await nerd_team_cmd(update, ctx, data.split(":", 1)[1])
    elif data.startswith("nerd_hof:"): await nerd_hof_cmd(update, ctx, data.split(":", 1)[1])
    elif data.startswith("teamnext:"):
        _pp214 = data.split(":", 2); await team_next_cmd(update, ctx, _pp214[1], _pp214[2])
    elif data.startswith("teamnews:"):
        _pp214 = data.split(":", 2); await team_news_cmd(update, ctx, _pp214[1], _pp214[2])
    elif data.startswith("teamfav:"):
        # V214: Team zu Favoriten + Knopf rausnehmen (sonst doppelt tippen)!
        try:
            _pp214 = data.split(":", 2); _lgf214 = _pp214[1]; _tmf214 = _pp214[2]
            _favs214 = load_favs(); _uidf214 = str(update.effective_user.id)
            _favs214.setdefault(_uidf214, [])
            _new214 = f"{_tmf214} ({_lgf214})"
            if _new214 not in _favs214[_uidf214]:
                _exists214 = any(_tmf214.lower() in (f.split(" (")[0].strip().lower()) or (f.split(" (")[0].strip().lower()) in _tmf214.lower() for f in _favs214[_uidf214])
                if not _exists214: _favs214[_uidf214].append(_new214)
                save_favs(_favs214)
            try: await q.answer("✅ Zu Favoriten hinzugefügt!")
            except: pass
            try:
                _old_kb214 = q.message.reply_markup
                _new_rows214 = []
                for _r214 in (_old_kb214.inline_keyboard if _old_kb214 else []):
                    if any((getattr(_b214, "callback_data", "") or "").startswith("teamfav:") for _b214 in _r214): continue
                    _new_rows214.append(list(_r214))
                _new_kb214 = InlineKeyboardMarkup(_new_rows214) if _new_rows214 else None
                await q.message.edit_text((q.message.text or "") + chr(10) + chr(10) + "⭐ Dein Favorit!", reply_markup=_new_kb214)
            except: pass
        except: pass

    elif data=="notif": await notif_cmd(update, ctx)
    elif data=="notif_master":
        _m = not get_live_master(update.effective_user.id); set_live_master(update.effective_user.id, _m)
        await notif_cmd(update, ctx)
    elif data=="dnd": await dnd_cmd(update, ctx)
    elif data=="dnd_toggle":
        _du = update.effective_user.id if update.effective_user else 0
        set_dnd(_du, on=not get_dnd(_du)["on"]); await dnd_cmd(update, ctx)
    elif data=="dnd_spoiler":
        _du = update.effective_user.id if update.effective_user else 0
        set_dnd(_du, spoiler=not get_dnd(_du)["spoiler"]); await dnd_cmd(update, ctx)
    elif data=="autoclose_toggle":
        _du = update.effective_user.id if update.effective_user else 0
        set_autoclose(_du, not get_autoclose(_du)); await settings_cmd(update, ctx)
    elif data=="dnd_pick_start": await dnd_pick_cmd(update, ctx, "start")
    elif data=="dnd_pick_end": await dnd_pick_cmd(update, ctx, "end")
    elif data.startswith("dnd_set_start:"):
        _du = update.effective_user.id if update.effective_user else 0
        try: set_dnd(_du, start=int(data.split(":")[1]))
        except: pass
        await dnd_cmd(update, ctx)
    elif data.startswith("dnd_set_end:"):
        _du = update.effective_user.id if update.effective_user else 0
        try: set_dnd(_du, end=int(data.split(":")[1]))
        except: pass
        await dnd_cmd(update, ctx)
    elif data=="dnd_summary": await dnd_summary_cmd(update, ctx)
    elif data.startswith("dnd_reveal:"):
        _pp = data.split(":")
        if len(_pp) >= 3: await dnd_reveal_cmd(update, ctx, _pp[1], _pp[2])
    elif data=="dnd_reveal_all": await dnd_reveal_all_cmd(update, ctx)
    elif data=="dnd_done": await _cb_edit(update, "🌅 Alles klar - Zettel ist leer! Bis zum nächsten Mal! 😊", small_kb())
    elif data=="notif_teams": await notif_teams_cmd(update, ctx)
    elif data=="my_live_games": await my_live_games_cmd(update, ctx)
    elif data.startswith("notif_team:"): await notif_team_cmd(update, ctx, int(data.split(":")[1]))
    elif data.startswith("notif_toggle:"):
        _p = data.split(":"); _idx = int(_p[1]); _kind = _p[2]
        _favs = favs_for(update.effective_user.id)
        if 0 <= _idx < len(_favs):
            set_live_team_toggle(update.effective_user.id, _favs[_idx], _kind)
        await notif_team_cmd(update, ctx, _idx)
    elif data=="settings": await settings_cmd(update, ctx)
    elif data=="settings_reminder": await settings_reminder_cmd(update, ctx)
    elif data=="settings_sender": await q.message.reply_text("📺 Sender-Anzeige: 🇺🇸 Original (CBS / FOX / ESPN ...)\n\nDeutsche Sender wechseln wir nicht - die Rechte ändern sich ständig (NFL jetzt RTL / Sky / Game Pass) und wir wollen dir nichts Falsches zeigen!", reply_markup=small_kb())
    elif data.startswith("reminder_set:"):
        _v = data.split(":")[1]
        _mins = None if _v=="off" else int(_v)
        set_reminder_minutes(update.effective_user.id, _mins)
        await q.message.reply_text(f"✅ Reminder-Zeit eingestellt: {fmt_reminder(_mins)}!\n\nSpielen 2 deiner Favoriten gleichzeitig, kriegst du 1 Nachricht für beide - mit Sender!", reply_markup=small_kb())
    elif data=="nhl_help": await nhl_help_cmd(update, ctx)
    elif data=="tables_all": await tables_all_cmd(update, ctx)
    elif data=="tables": await tables_cmd(update, ctx)
    elif data.startswith("tables_league:"): await tables_league_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("tables_div:"):
        _parts = data.split(":", 2)
        await tables_div_cmd(update, ctx, _parts[1], _parts[2])
    elif data.startswith("tables_conf:"):
        _parts = data.split(":")
        await tables_conf_cmd(update, ctx, _parts[1], _parts[2])
    elif data=="tables_mine": await tables_mine_cmd(update, ctx)
    elif data=="playoffs": await playoffs_cmd(update, ctx)
    elif data.startswith("playoffs_league:"): await playoffs_league_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("playoffs_cfp:"): await playoffs_league_cmd(update, ctx, data.split(":")[1], force_cfp=True)
    elif data.startswith("playoffs_bowls:"): await playoffs_bowls_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("cfp_top25:"): await cfp_top25_cmd(update, ctx)
    elif data.startswith("top10_league:"): await top10_league_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("top10_detail:"): await top10_detail_cmd(update, ctx, int(data.split(":")[1]))
    elif data=="next": await next_hub_cmd(update, ctx)
    elif data=="next_today": await heute_morgen(update, ctx, False)
    elif data=="next_tomorrow": await heute_morgen(update, ctx, True)
    elif data.startswith("next_today:"): await heute_morgen(update, ctx, False, lg_filter=data.split(":")[1], edit=True)
    elif data.startswith("next_tomorrow:"): await heute_morgen(update, ctx, True, lg_filter=data.split(":")[1], edit=True)
    elif data=="next_mine": await next_mine_cmd(update, ctx)
    elif data=="injuries_mine": await injuries_mine_cmd(update, ctx)
    elif data.startswith("injuries_ir:"): _p=data.split(":"); await injuries_ir_cmd(update, ctx, _p[1], ":".join(_p[2:]))
    elif data=="game_info_leagues": await game_info_leagues_cmd(update, ctx)
    elif data.startswith("game_info_games:"): await game_info_games_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("game_info_detail:"): await game_info_detail_cmd(update, ctx, data.split(":")[1])
    elif data=="fav_remove": await fav_remove_cmd(update, ctx)
    elif data.startswith("fav_del:"):
        _idx=int(data.split(":")[1]); _d=load_favs(); _uid=str(update.effective_user.id); _lst=_d.get(_uid,[])
        _rem=_lst.pop(_idx) if 0 <= _idx < len(_lst) else "?"
        _d[_uid]=_lst; save_favs(_d)
        await q.message.reply_text(f"✅ {_rem} entfernt!", reply_markup=small_kb())
    elif data=="heute": await heute_morgen(update, ctx, False)
    elif data=="morgen": await heute_morgen(update, ctx, True)
    elif data=="results": await results_cmd(update, ctx)
    elif data=="results_mine": await results_mine_cmd(update, ctx)
    elif data.startswith("results_league:"): await results_league_cmd(update, ctx, data.split(":")[1])
    elif data=="live": await live_cmd(update, ctx)
    elif data=="live_all": await live_all_cmd(update, ctx)
    elif data=="live_mine": await live_mine_cmd(update, ctx)
    elif data=="live_stats": await live_stats_cmd(update, ctx)
    elif data.startswith("live_stats_one:"): await live_stats_one_cmd(update, ctx, int(data.split(":")[1]))
    elif data=="remind": await remind_cmd(update, ctx)
    elif data=="fav_add":
        ctx.user_data["awaiting_fav"]=True; ctx.user_data["await_live_stats_pick"] = False  # V246: Live-Flag aus! Favoriten-Anlage gewinnt!
        await q.message.reply_text("Bitte Teamnamen eingeben:")
    elif data=="fav_list":
        favs=favs_for(update.effective_user.id)
        _kb=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Favorit hinzufügen", callback_data="fav_add")],[InlineKeyboardButton("🗑️ Favorit entfernen", callback_data="fav_remove")],[InlineKeyboardButton("🗑️ Alle Favoriten löschen", callback_data="fav_clear")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        await q.message.reply_text("⭐ Deine Favoriten:\n" + ("\n".join([f"• {f}" for f in favs]) if favs else "Noch keine."), reply_markup=_kb)
    elif data=="fav_clear":
        # V167: KEINE Liste mehr! Nur fragen + SELBES Fenster editieren, keine neue Nachricht!
        _favs_c = favs_for(update.effective_user.id) if update.effective_user else []
        if not _favs_c:
            await _cb_edit(update, "Noch keine Favoriten zum Loeschen.", small_kb())
        else:
            _kb_c = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, alle loeschen!", callback_data="fav_clear_yes")],[InlineKeyboardButton("❌ Nein, behalten!", callback_data="fav_clear_no")]])
            await _cb_edit(update, "⚠️ Wirklich alle Favoriten löschen?", _kb_c)
    elif data=="fav_clear_yes":
        favs=load_favs(); favs[str(update.effective_user.id)]=[]; save_favs(favs)
        # V167: Selbes Fenster editieren, keine neue Nachricht!
        await _cb_edit(update, "🗑️ Alle Favoriten gelöscht.", small_kb())
    elif data=="fav_clear_no":
        # V167: Selbes Fenster editieren, keine neue Nachricht, keine Liste!
        await _cb_edit(update, "✅ Puh, Glück gehabt! Alle Favoriten behalten!", small_kb())
    elif data.startswith("fav_pick:"):
        idx=int(data.split(":")[1]); cands=ctx.user_data.get("fav_candidates",[])
        if idx < len(cands):
            chosen=cands[idx]; favs=load_favs(); uid=str(update.effective_user.id); favs.setdefault(uid,[])
            if chosen not in favs[uid]: favs[uid].append(chosen)
            save_favs(favs)
            await q.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=small_kb())


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
    # V88-FIX2: Loop MUSS gesetzt sein! PTB ruft intern get_event_loop() auf.
    # Python 3.14 macht KEINEN Default-Loop mehr -> sonst RuntimeError in MainThread.
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception as e:
        print("Loop-Fix:", e)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("fav", fav_cmd))
    app.add_handler(CommandHandler("next", next_hub_cmd))
    app.add_handler(CommandHandler("top10", top10_cmd))
    app.add_handler(CommandHandler("tables", tables_cmd))
    app.add_handler(CommandHandler("heute", lambda u,c: heute_morgen(u,c,False)))
    app.add_handler(CommandHandler("morgen", lambda u,c: heute_morgen(u,c,True)))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(CommandHandler("ergebnisse", results_cmd))
    app.add_handler(CommandHandler("remind", remind_cmd))
    try:
        _jq = getattr(app, "job_queue", None)
        if _jq is not None:
            _jq.run_repeating(reminder_job, interval=900, first=10)
            _jq.run_repeating(live_score_job, interval=60, first=20)  # V89-FIX: 60 Sek statt 120 Sek - so schnell wie moeglich ohne ESPN-Block (429)!
            _jq.run_repeating(dnd_summary_job, interval=300, first=60)  # V203: Auto-Zusammenfassung wenn DND endet!
        else:
            print("JobQueue: kein APScheduler - Reminder aus, Bot laeuft trotzdem.")
    except Exception as e:
        print("JobQueue:", e)
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("✅ USA Sport Radar Bot online - V214 - is live")
    logger.info("✅ USA Sport Radar Bot online - V214 - is live")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()
