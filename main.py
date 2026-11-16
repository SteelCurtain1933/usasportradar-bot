# USA Sport Radar - V158 FINAL - Ergebnisse Favoriten-Filter + YouTube Highlights & Pressekonferenz bei Final Stats!
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
def fmt_reminder(minutes):
    if minutes is None: return "Aus"
    if minutes>=60: return f"{minutes//60}h vorher" if minutes%60==0 else f"{minutes} Min vorher"
    return f"{minutes} Min vorher"

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

def espn_injuries(league):
    if league == "NCAAF": return []
    _sport = "football" if league in ("NFL",) else "baseball" if league == "MLB" else "hockey" if league == "NHL" else "basketball"
    _key = LEAGUES[league]["espn"]
    try:
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{_sport}/{_key}/injuries", timeout=12)
        j = r.json()
        return j.get("injuries", []) or []
    except Exception:
        return []
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

def rank_game(ev, league):
    teams, comp = event_teams(ev)
    names = " ".join([x[0] for x in teams]).lower()
    big_teams = ["steelers","eagles","chiefs","cowboys","dodgers","yankees","lakers","celtics","panthers","penguins","pirates","patriots","packers","ravens","49ers","bills","lions","texans","georgia","alabama","ohio state","michigan","notre dame","texas","oregon","bengals","browns","vikings","seahawks","rams","dolphins","jets"]
    big_count = sum(1 for b in big_teams if b in names)
    tabelle = 2.0 + min(1.5, big_count*0.7)
    # ALLE großen Rivalitäten! Bengals-Steelers fehlte! Das ist AFC North, Battle of Ohio, Riesen-Rivalität!
    rival_pairs = [
        # NFL - AFC North (die härteste Division!)
        ("steelers","ravens"),("steelers","bengals"),("steelers","browns"),
        ("bengals","ravens"),("bengals","browns"),("ravens","browns"),
        # NFL - NFC North / East / West
        ("cowboys","49ers"),("cowboys","eagles"),("cowboys","giants"),("eagles","giants"),
        ("packers","bears"),("packers","vikings"),("bears","vikings"),("lions","packers"),
        ("chiefs","bills"),("chiefs","raiders"),("chiefs","broncos"),("chiefs","chargers"),
        ("patriots","bills"),("patriots","jets"),("patriots","dolphins"),
        ("49ers","seahawks"),("49ers","rams"),("rams","seahawks"),
        ("saints","falcons"),("saints","buccaneers"),("colts","titans"),("texans","colts"),
        # NBA / MLB / NHL
        ("lakers","celtics"),("lakers","clippers"),("knicks","celtics"),("bulls","pistons"),
        ("yankees","red sox"),("dodgers","giants"),("dodgers","padres"),("cubs","cardinals"),
        ("penguins","capitals"),("penguins","flyers"),("rangers","islanders"),("bruins","canadiens"),("blackhawks","red wings"),
        # College
        ("michigan","ohio state"),("alabama","auburn"),("georgia","florida"),("texas","oklahoma"),("notre dame","usc"),
        ("texas","texas a&m"),("army","navy"),("florida","florida state"),("ohio state","penn state"),
    ]
    rival = 0.5
    for a,b in rival_pairs:
        if a in names and b in names: rival = 2.8; break
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
    h = sum(ord(c) for c in names) % 10
    var = h / 20.0
    total = round(min(9.9, max(3.0, tabelle + rival + stars + prime + var)), 1)
    breakdown = {"tabelle": round(tabelle,1), "rival": round(rival,1), "stars": round(stars,1), "prime": round(prime,1), "var": round(var,1), "total": total}
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
            if any(k in dtype for k in ["Goal", "Touchdown", "Field Goal", "Home Run", "Three Point", "Two Point", "Dunk", "Layup", "Single", "Double", "Triple"]):
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
                label = "Letztes Tor" if league=="NHL" else "Letzter Score" if league=="MLB" else "Letzter Touchdown" if dtype=="Touchdown" else "Letzter Score"
                extra = f" • {clock} P{period}" if league=="NHL" and clock else ""
                if scorer:
                    return f"   {emo} {label}: {scorer} ({team}){extra}" if team else f"   {emo} {label}: {scorer}{extra}"
        return ""
    except Exception:
        return ""


def espn_summary_details(ev, league):
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

def main_kb(with_close=True):
    # V94: Hauptmenue = KEIN Fenster-schliessen (sonst muss man jedes Mal wieder /start tippen)! Ueberall sonst = mit Fenster-schliessen!
    # V134: 5 Reihen, logisch! Oben Inhalt, unten System! Einstellungen + Hilfe ganz unten!
    rows = [
        [InlineKeyboardButton("⭐ Meine Favoriten", callback_data="fav_list")],
        [InlineKeyboardButton("⏭️ Next Games", callback_data="next"),
         InlineKeyboardButton("🏆 Top 10", callback_data="top10")],
        [InlineKeyboardButton("🔴 Live", callback_data="live"),
         InlineKeyboardButton("📊 Tabellen", callback_data="tables")],
        [InlineKeyboardButton("📰 News", callback_data="news"),
         InlineKeyboardButton("✅ Ergebnisse", callback_data="results")],
        [InlineKeyboardButton("⚙️ Einstellungen", callback_data="settings"),
         InlineKeyboardButton("❓ Hilfe", callback_data="help")],
    ]
    if with_close:
        rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
    return InlineKeyboardMarkup(rows)

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
Nach Spielende fragt der Bot, ob er die Live-Nachrichten löschen soll!

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
    await update.message.reply_text(START_TEXT, reply_markup=main_kb(with_close=False))
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _hkb = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f4d6 Grundlagen (Gast @ Heim, \u2b50, 📺)", callback_data="help_cat:grund")],[InlineKeyboardButton("\U0001f3c8 Spiele / Live / Next Games", callback_data="help_cat:spiele")],[InlineKeyboardButton("\U0001f4ca Tabellen / Top 10", callback_data="help_cat:tabellen")],[InlineKeyboardButton("\U0001f514 Benachrichtigungen", callback_data="help_cat:benach")],[InlineKeyboardButton("\U0001f4f0 News / Verletzungen / Breaking", callback_data="help_cat:news")],[InlineKeyboardButton("\U0001fa9f Fenster", callback_data="help_cat:fenster")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")],])
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
        all_games=[]; seen=set()
        for lg in leagues:
            for offset in range(0, 8):
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
        all_games.sort(key=lambda x: x[0], reverse=True)
        top = all_games[:10]
        ctx.user_data["top10_list"] = [(s, lg, ev, bd) for s, lg, ev, bd in top]
        title = "Alle Ligen" if league=="ALL" else league
        lines=[f"🏆 Top 10 - {title}\n💡 Zahl tippen für Rating + Details!\n"]
        if not top:
            lines.append("Keine Spiele in den nächsten 7 Tagen gefunden.")
            _live_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔴 Meine Live-Spiele", callback_data="my_live_games")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
            try:
                if _load: await ctx.bot.delete_message(chat_id=update.effective_user.id, message_id=_load.message_id)
            except Exception: pass
            await target.reply_text("\n".join(lines), reply_markup=_live_kb); return
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
        await target.reply_text("\n".join(lines), reply_markup=kb)
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
        await target.reply_text("Tippe erst auf 🏆 Top 10 und wähle eine Liga, dann die Zahl!", reply_markup=main_kb()); return
    score, lg, ev, bd = lst[idx-1]
    if _v135_is_finished(ev):
        await target.reply_text("🏁 Spiel vorbei — wird nicht mehr bewertet!\n\nSchau bei ✅ Ergebnisse für Final Stats!", reply_markup=main_kb()); return
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
        f"📊 **Tabelle:** +{bd['tabelle']:.1f} - Beide Teams sind stark / Top-Teams in ihrer Liga, das Duell hat viel Gewicht für die Tabelle.",
        f"🔥 **Rivalität:** +{bd['rival']:.1f} - " + ("Historische Rivalität! Die beiden haben sich schon oft in großen Spielen getroffen." if bd['rival']>=2.5 else "Division-Duell / zwei starke Teams - da ist Feuer drin." if bd['rival']>=1.5 else "Kein großes Rivalitäts-Spiel, aber beide wollen gewinnen."),
        f"⭐ **Stars:** +{bd['stars']:.1f} - Viele bekannte Stars auf dem Feld, die das Spiel entscheiden können.",
        f"📺 **Primetime:** +{bd['prime']:.1f} - " + ("Primetime-Spiel! Läuft zur besten Zeit, wo alle zugucken." if bd['prime']>=1.0 else "Kein Primetime-Spiel, läuft neben anderen Spielen."),
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
    await target.reply_text("\n".join(lines), reply_markup=kb)


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

def espn_standings(league):
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
    await target.reply_text("\n".join(lines), reply_markup=kb)
async def playoffs_league_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str, force_cfp: bool = False):
    target = update.message or update.callback_query.message
    # V83: NCAAF -> erst Auswahl! CFP Playoffs vs. Bowl Games! Bowls sind keine Playoffs!
    if league == "NCAAF" and not force_cfp:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏆 CFP Playoffs", callback_data="playoffs_cfp:NCAAF")],
            [InlineKeyboardButton("🥣 Bowl Games", callback_data="playoffs_bowls:NCAAF")],
            [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
        ])
        await target.reply_text("🏆 Playoffs - 🎓🏈 NCAAF\n\nWas willst du sehen?\n🏆 CFP Playoffs = Wer ist in den Top 12, wer ist sicher, wer ist raus!\n🥣 Bowl Games = Alle Bowl Games mit Bowl-Namen!", reply_markup=kb); return
    from datetime import date as _date
    today = _date.today()
    # --- Phase 2 Check: Laufen schon Playoffs? Postseason-Spiele in den letzten 30 + nächsten 30 Tagen? ---
    _post = []  # (dt, round_label, ev)
    for _rng in [f"{(today - timedelta(days=30)).strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}", f"{today.strftime('%Y%m%d')}-{(today + timedelta(days=30)).strftime('%Y%m%d')}"]:
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
            await target.reply_text("\n".join(lines), reply_markup=kb); return
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
        await target.reply_text("\n".join(lines), reply_markup=kb); return
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
        await target.reply_text("\n".join(lines), reply_markup=kb); return
    # --- Phase 1: Vor den Playoffs ---
    if not _playoff_mode(league):
        lines = [f"🏆 Playoffs - {LEAGUES[league]['emoji']} {league}\n\nNoch nix fest! 😅\nNoch kein Team ist sicher in den Playoffs oder raus!\nSchau später nochmal vorbei!"]
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        await target.reply_text("\n".join(lines), reply_markup=kb); return
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
            _label = f"Die {disp} ({W}-{L})"
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
        # V83: NCAAF -> KEIN "Noch im Rennen: 134 Teams"! Stattdessen: Aktuell Top 12!
        if league == "NCAAF":
            # Top 12 aus allen Rows: nach W sortiert, erste 12!
            _all_sorted = []
            for _dk, _rv in divs.items():
                for (disp, short, abbr, W, L, T, streak) in _rv:
                    _all_sorted.append((disp, W, L))
            _all_sorted.sort(key=lambda x: (x[1], -x[2]), reverse=True)
            lines.append("\n🔝 **Aktuell Top 12:**")
            for _i, (disp, W, L) in enumerate(_all_sorted[:12], 1):
                lines.append(f"{_i}. Die {disp} ({W}-{L})")
        elif _rennen:
            lines.append("\n🔥 **Noch im Rennen:**")
            lines.extend([f"• {_s}" for _s in _rennen[:12]])
            if len(_rennen) > 12: lines.append(f"... und {len(_rennen)-12} weitere!")
        if _raus:
            lines.append("\n❌ **Raus:**")
            lines.extend([f"• {_s}" for _s in _raus])
    # V83: NCAAF CFP -> Bowl-Button dazu!
    if league == "NCAAF" and force_cfp:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🥣 Bowl Games", callback_data="playoffs_bowls:NCAAF")], [InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        await target.reply_text("\n".join(lines), reply_markup=kb); return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 Andere Liga", callback_data="playoffs")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
    await target.reply_text("\n".join(lines), reply_markup=kb)
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
        await target.reply_text(f"Keine Tabelle gefunden - versuch es später nochmal.\n\nDebug: Status {dbg.get('last_status')} | Keys: {dbg.get('last_keys')} | URL: {dbg.get('last_url')}", reply_markup=main_kb()); return
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
        await target.reply_text("Division nicht gefunden.", reply_markup=main_kb()); return
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
    _kb_rows = [[InlineKeyboardButton("📊 Andere Division", callback_data=f"tables_league:{league}")], [InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]]
    if league=="NHL":
        _kb_rows.append([InlineKeyboardButton("❓ Was bedeutet W-L-OTL / OT1?", callback_data="nhl_help")])
    _kb_rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    kb = InlineKeyboardMarkup(_kb_rows)
    await target.reply_text("\n".join(lines), reply_markup=kb)
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
        await target.reply_text("Conference nicht gefunden.", reply_markup=main_kb()); return
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
    _kb_rows2 = [[InlineKeyboardButton("📊 Andere Division", callback_data=f"tables_league:{league}")], [InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]]
    if league=="NHL":
        _kb_rows2.append([InlineKeyboardButton("❓ Was bedeutet W-L-OTL / OT1?", callback_data="nhl_help")])
    _kb_rows2.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    kb = InlineKeyboardMarkup(_kb_rows2)
    await target.reply_text("\n".join(lines), reply_markup=kb)
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
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")],[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")],])
    await target.reply_text("\n".join(lines), reply_markup=kb)


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
        await target.reply_text("Du hast noch keine Favoriten. Füge erst ein Team hinzu, dann zeige ich dir hier deine Tabellen!", reply_markup=main_kb()); return
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
    await target.reply_text("\n".join(lines), reply_markup=kb)

async def next_hub_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Heute - Alle Spiele", callback_data="next_today")],
        [InlineKeyboardButton("📅 Morgen - Alle Spiele", callback_data="next_tomorrow")],
        [InlineKeyboardButton("⭐ Nur meine Favoriten", callback_data="next_mine")],
        [InlineKeyboardButton("🔴 Live für ein Spiel (nicht Favorit)", callback_data="next_live_league")],
        [InlineKeyboardButton("❓ Hilfe", callback_data="help")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "⏭️ Next Games\n\nWas willst du sehen?\n📅 Heute / Morgen = alle Spiele, auch ohne Favoriten!\n⭐ Nur meine Favoriten = wann spielen DEINE Teams als Nächstes?", kb)
async def next_mine_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs = favs_for(user.id) if user else []
    lines=["⏭️ Next Games - Deine Favoriten\n"]
    grouped = {}  # V69: Datum -> [(dt, league, ev, disp)]
    if not favs:
        lines.append("Du hast noch keine Favoriten. Füge erst ein Team hinzu, dann zeige ich dir hier das nächste Spiel pro Team.")
        await target.reply_text("\n".join(lines), reply_markup=main_kb()); return
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
    await target.reply_text("\n".join(lines), reply_markup=_kb)

async def injuries_mine_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs = favs_for(user.id) if user else []
    _now = datetime.now(BERLIN)
    lines = [f"🏥 Verletzungen — Meine Teams\n📅 Stand: {_now.strftime('%d.%m. %H:%M')}\nℹ️ Bis zu 15 Min verzögert!"]
    if not favs:
        lines.append("Du hast noch keine Favoriten.")
        await target.reply_text("\n".join(lines), reply_markup=main_kb()); return
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
    await target.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(_kb_rows))
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
        await target.reply_text("ℹ️ Mehr Infos — Keine kommenden Spiele deiner Favoriten gefunden.", reply_markup=main_kb()); return
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
        await target.reply_text("Keine Spiele in dieser Liga.", reply_markup=main_kb()); return
    _rows=[]
    for _dt,_lg,_ev,_f in _filt:
        _rows.append([InlineKeyboardButton(f"{game_line(_ev,_lg,show_broadcast=False)[:60]}", callback_data=f"game_info_detail:{_ev.get('id')}")])
    _rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="game_info_leagues")])
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
        await target.reply_text("Spiel nicht mehr gefunden. Bitte nochmal über Next Games öffnen.", reply_markup=main_kb()); return
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
    await target.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu den Spielen", callback_data="game_info_leagues")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]]))
async def fav_remove_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target=update.message or update.callback_query.message
    _favs=favs_for(update.effective_user.id)
    if not _favs:
        await target.reply_text("Noch keine Favoriten.", reply_markup=main_kb()); return
    _rows=[[InlineKeyboardButton(f"❌ {_f}", callback_data=f"fav_del:{_i}")] for _i,_f in enumerate(_favs)]
    _rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    await target.reply_text("🗑️ Welchen Favorit willst du entfernen?", reply_markup=InlineKeyboardMarkup(_rows))
async def heute_morgen(update: Update, ctx: ContextTypes.DEFAULT_TYPE, morgen=False):
    target = update.message or update.callback_query.message
    want = (datetime.now(BERLIN)+timedelta(days=1 if morgen else 0)).date()
    lines=[f"📅 {'Morgen' if morgen else 'Heute'} ({want.strftime('%d.%m.')})\n"]
    # Überall: "Gast @ Heim" - erstes Team ist Heimteam!

    live_lines=[]; upcoming_lines=[]
    for league in LEAGUES:
        for ev in espn_scoreboard(league):
            _, dt = fmt_dt(ev.get("date",""))
            if dt and dt.date()==want:
                state = ev.get("status",{}).get("type",{}).get("state","")
                # Heute: NUR Live + Noch heute! Finals kommen bei ✅ Ergebnisse rein, sonst ewige Liste!
                if not morgen and state=="post":
                    continue
                if state=="in":
                    live_lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league, show_broadcast=True)}")
                else:
                    upcoming_lines.append(f"{LEAGUES[league]['emoji']} {game_line(ev, league, show_broadcast=True)}")
    if live_lines:
        lines.append("🔴 Live:")
        lines.extend(live_lines)
    if upcoming_lines:
        lines.append("\n⏰ Noch heute:" if not morgen else "\n⏰ Morgen:")
        lines.extend(upcoming_lines)
    if not live_lines and not upcoming_lines:
        if morgen:
            lines.append("Morgen keine Spiele in den Ligen. Schau mal bei /top10 oder /next vorbei.")
        else:
            lines.append("Heute kein Spiel mehr - alles schon vorbei! Schau mal bei ✅ Ergebnisse für die Endergebnisse von letzter Nacht.")
            lines.append("Oder bei ⏭️ Next Games für die nächsten Spiele deiner Favoriten.")
    await target.reply_text("\n".join(lines), reply_markup=main_kb())



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
                        _short = (_tm.get("shortDisplayName","") or "").lower()
                        for _fn in _wanted:
                            if _fn in _full or _full in _fn or _fn == _short or _short in _fn or _fn.split()[-1] in _full:
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
    _rm = await target.reply_text("\n".join(lines) + "\n\n📊 Für Final Stats einfach die Zahl schicken! z.B. 1", reply_markup=_with_close(kb))
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
        lines.append(f"{i}. {game_line(ev, lg, show_broadcast=False)}")
        rows.append([InlineKeyboardButton(f"{i}. {game_line(ev, lg, show_broadcast=False)[:40]}", callback_data=f"live_stats_one:{i-1}")])
    lines.append("\nTippe die Zahl ein (z.B. 1) oder tippe auf das Spiel!")
    ctx.user_data["await_live_stats_pick"]=True
    rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
    # V148: Bei Button-Klick bearbeiten, nicht neue Nachricht!
    _kb_pick=InlineKeyboardMarkup(rows)
    _txt_pick="\n".join(lines)
    if update.callback_query:
        await _cb_edit(update, _txt_pick, _kb_pick)
    else:
        await target.reply_text(_txt_pick, reply_markup=_kb_pick)

async def live_stats_one_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, idx: int):
    target=update.message or update.callback_query.message
    _live=ctx.user_data.get("live_events_v147") or []
    try: ctx.user_data["await_live_stats_pick"]=False
    except Exception: pass
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
            await target.reply_text(_msg, reply_markup=_kb)
        return
    # V148: Frisches Event für Situation (Down & Distance, Feldposition) - gespeichertes ev ist alt!
    try:
        _fresh=None
        for _ev2 in espn_scoreboard(lg):
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
        await target.reply_text(_txt, reply_markup=_kb)

async def live_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
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
        for ev in espn_scoreboard(league):
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
                    for _ev2 in espn_scoreboard(_lg2):
                        _teams2, _ = event_teams(_ev2)
                        _tt2 = " ".join([x[0] for x in _teams2]).lower()
                        if fav_map and not any((lgx is None or lgx==_lg2) and fnx in _tt2 for lgx, fnx in fav_map): continue
                        if _ev2.get("status",{}).get("type",{}).get("state","")=="post":
                            _lf.append((_lg2, str(_ev2.get("id",""))))
                ctx.user_data["live_finals_list"] = _lf[:5]
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
            for ev in espn_scoreboard(league):
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
    await target.reply_text("\n".join(lines), reply_markup=_kb)

async def settings_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    uid = update.effective_user.id if update.effective_user else 0
    rm = get_reminder_minutes(uid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Favoriten verwalten", callback_data="fav_list")],
        [InlineKeyboardButton("🔔 Benachrichtigungen", callback_data="notif")],
        [InlineKeyboardButton("❓ Allgemeine Hilfe", callback_data="help")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, "⚙️ Einstellungen\n\nWas willst du einstellen?", kb)
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
def _chain_add(uid, mid):
    try:
        if not uid or not mid: return
        _CLOSE_CHAIN.setdefault(int(uid), [])
        if int(mid) not in _CLOSE_CHAIN[int(uid)]: _CLOSE_CHAIN[int(uid)].append(int(mid))
        # Nur letzte 20 merken, sonst wirds ewig lang!
        _CLOSE_CHAIN[int(uid)] = _CLOSE_CHAIN[int(uid)][-20:]
    except: pass
def _chain_clear(uid):
    try: _CLOSE_CHAIN[int(uid)] = []
    except: pass
async def _chain_delete_all(ctx, uid, current_mid=None):
    try:
        _ids = list(_CLOSE_CHAIN.get(int(uid), []) or [])
        if current_mid: _ids.append(int(current_mid))
        for _mid in _ids:
            try: await ctx.bot.delete_message(chat_id=int(uid), message_id=int(_mid))
            except: pass
        _chain_clear(uid)
    except: pass

async def _cb_edit(update, text, kb):
    # V95: /start-Hauptmenue bleibt IMMER da! Nie bearbeiten!
    # Wenn der Klick aus dem Hauptmenue kommt, NEUE Nachricht als Fenster schicken, Hauptmenue bleibt oben!
    try:
        if update.callback_query and update.callback_query.message:
            _mt = (update.callback_query.message.text or "") if getattr(update.callback_query.message, "text", None) else ""
            _uid_cb = update.effective_user.id if update.effective_user else 0
            if _mt.startswith("Willkommen beim USA Sport Radar"):
                # Neuer Flow ab Hauptmenü -> alte Kette weg!
                _chain_clear(_uid_cb)
                _m = await update.callback_query.message.reply_text(text, reply_markup=_with_close(kb))
                try: _chain_add(_uid_cb, _m.message_id)
                except: pass
                return
            # Fenster wird bearbeitet (gleiche Nachricht) -> ID merken!
            try: _chain_add(_uid_cb, update.callback_query.message.message_id)
            except: pass
            await update.callback_query.message.edit_text(text, reply_markup=_with_close(kb)); return
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
    try:
        m = await context.bot.send_message(chat_id=uid, text=text)
        if m and getattr(m, "message_id", None):
            _LIVE_MSG_IDS.setdefault((uid, str(eid)), []).append(int(m.message_id))
        return m
    except Exception:
        try: return await context.bot.send_message(chat_id=uid, text=text)
        except: return None


# ===== V134: News + Liga-Breaking + Spiel-Breaking in einem Rutsch! =====
_ESPN_NEWS_SPORT = {"NFL": ("football","nfl"), "NCAAF": ("football","college-football"), "NBA": ("basketball","nba"), "NHL": ("hockey","nhl"), "MLB": ("baseball","mlb")}
_LIGA_BREAKING_KEYS = ["international series","london","munich","munchen","madrid","berlin","schedule","super bowl","playoffs","trade deadline","expansion","rule change","new stadium","franchise"]
# V134: Pro Liga eigene Begriffe! Super Bowl nur NFL, NBA Finals nur NBA, usw!
_LIGA_BREAKING_PER_LEAGUE = {
 "NFL": ["super bowl","draft","trade deadline","international series","london","munich","munchen","madrid","berlin","schedule","playoffs","franchise tag","rule change","expansion","new stadium"],
 "NBA": ["nba finals","draft","trade deadline","all-star","playoffs","play-in","schedule","expansion","rule change"],
 "NHL": ["stanley cup","trade deadline","winter classic","playoffs","draft","schedule","expansion","rule change"],
 "MLB": ["world series","trade deadline","draft","playoffs","opening day","schedule","expansion","rule change"],
 "NCAAF": ["college football playoff","national championship","bowl games","draft","transfer portal","schedule","playoffs","rule change"],
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
        if not tid: return []
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
            if hl and not _v136_is_scam_news(hl, link): out.append({"headline":hl,"link":link,"published":a.get("published","")})
        return out
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
def _google_news_rss(team_full, league, limit=8):
    try:
        import urllib.parse as _up, xml.etree.ElementTree as _ET
        q=f"{team_full} {league} news"
        url="https://news.google.com/rss/search?q="+_up.quote(q)+"&hl=en-US&gl=US&ceid=US:en"
        r=requests.get(url,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
        root=_ET.fromstring(r.content or b"")
        out=[]
        for it in root.iter("item"):
            t=it.findtext("title") or ""
            lk=it.findtext("link") or ""
            if " - " in t: t=t.rsplit(" - ",1)[0]
            t=t.strip()
            if not t or not lk: continue
            if _v136_is_scam_news(t, lk): continue
            out.append({"headline":t,"link":lk,"published":""})
            if len(out)>=limit: break
        return out
    except: return []
def _team_news_all(league, team_full, limit=8):
    # V137: 2. Filter-Layer! Auch wenn RSS/ESPN mal Scam liefert, fliegt er hier raus!
    arts=_espn_team_news(league,team_full,limit=limit)
    arts=[a for a in arts if not _v136_is_scam_news(a.get("headline",""), a.get("link",""))]
    if arts: return arts, "ESPN"
    arts2=_google_news_rss(team_full,league,limit=limit)
    arts2=[a for a in arts2 if not _v136_is_scam_news(a.get("headline",""), a.get("link",""))]
    if arts2: return arts2, "Google News"
    return [], "ESPN"
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
async def news_cmd(update, ctx):
    # Team-News: nur Favoriten! Nur Headline + Link!
    uid=update.effective_user.id if update.effective_user else 0
    favs=favs_for(uid)
    if not favs:
        await _cb_edit(update, "📰 News\n\nDu hast noch keine Favoriten. Füge erst ein Team hinzu!", main_kb()); return
    _lb_map = get_league_breaking_map(uid)
    _open = get_news_league_open(uid)
    _on_list = [lg for lg,_v in _lb_map.items() if _v]
    _on_txt = f" ({len(_on_list)} an: {', '.join(_on_list)})" if not _open else ""
    rows=[[InlineKeyboardButton(f"🌍 Liga-Breaking {'▾' if _open else '▸'}{_on_txt}", callback_data="news_league_expand")]]
    if _open:
        _em={"NFL":"🏈","NBA":"🏀","NHL":"🏒","MLB":"⚾","NCAAF":"🎓"}
        for _lg in ["NFL","NBA","NHL","MLB","NCAAF"]:
            rows.append([InlineKeyboardButton(f"{'✅' if _lb_map.get(_lg) else '❌'} {_em[_lg]} {_lg}", callback_data=f"news_league_toggle:{_lg}")])
        rows.append([InlineKeyboardButton("✖️ Zuklappen", callback_data="news_league_expand")])
    for i,f in enumerate(favs): rows.append([InlineKeyboardButton(f"📰 {f}", callback_data=f"news_team:{i}")])
    rows.append([InlineKeyboardButton("⬅️ Zurück", callback_data="back")])
    await _cb_edit(update, "📰 News - Nur deine Favoriten!\n\n🌍 Liga-Breaking oben = Push für große Sachen (International Series, Schedule, Super Bowl, Playoffs, Trade Deadline)!\n\nTippe ein Team an, dann kriegst du nur Headline + Link! Artikel sind auf Englisch, Quelle: ESPN!\nKein Push-Spam - News holst du dir, wenn du willst!", InlineKeyboardMarkup(rows))
async def news_team_cmd(update, ctx, idx):
    uid=update.effective_user.id if update.effective_user else 0
    favs=favs_for(uid)
    if idx<0 or idx>=len(favs): await news_cmd(update, ctx); return
    f=favs[idx]; lg=f.split(" (")[-1].replace(")","").strip() if " (" in f else "NFL"
    _full = f.split(" (")[0].strip()
    arts, _src = _team_news_all(lg, _full, limit=8)
    # V137: 3. Layer - Scam auch beim Anzeigen raus, falls Liste schon alt/cached war!
    arts=[a for a in arts if not _v136_is_scam_news(a.get("headline",""), a.get("link",""))]
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
            except Exception: await q.message.reply_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True)
        else: await update.message.reply_text(_txt, reply_markup=_kb, parse_mode="HTML", disable_web_page_preview=True)
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
                    try: await context.bot.send_message(chat_id=uid, text=f"🌍 LIGA-BREAKING: {lg}\n\n{a['headline']}\n🔗 {a.get('link','')}")
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
        await target.reply_text("Du hast noch keine Favoriten. Füge erst ein Team hinzu!", reply_markup=main_kb()); return
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
        if any([d.get("score"), d.get("period"), d.get("final"), d.get("crunch"), d.get("start")]): active.append((str(eid), d.get("lg",""), d.get("name","") or f"Spiel {eid}", d))
    if not active:
        await _cb_edit(update, "🔴 Meine Live-Spiele\n\nNoch keine einzelnen Spiele angemacht.\nGeh zu Nächste Spiele → 🔴 Live für ein Spiel, dann tauchen sie hier auf!", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Teams", callback_data="notif_teams")]])); return
    try: ctx.user_data["my_live_list"] = [(eid, lg) for eid, lg, nm, d in active]
    except: pass
    lines = ["🔴 Meine Live-Spiele\n"]
    for i, (eid, lg, nm, d) in enumerate(active, start=1):
        _on = []
        if d.get("score"): _on.append("Score")
        if d.get("period"): _on.append(period_toggle_label(lg))
        if d.get("final"): _on.append("Endstand")
        if d.get("crunch"): _on.append("Crunch-Time")
        if d.get("breaking"): _on.append("Breaking")
        # V117: Kompakt! Stadion-Name kürzen: "FC Bayern Munich Stadium, Munich" -> "München", Zeilenumbrüche weg!
        _nm_clean = (nm or "").replace("\n"," ").replace("FC Bayern Munich Stadium, Munich","München").replace("FC Bayern Munich Stadium","München")
        # Kurz-Namen: "New England Patriots" -> "Patriots" in der Liste (nur Anzeige, nicht speichern!)
        for _full,_short in [("New England Patriots","Patriots"),("Detroit Lions","Lions")]:
            _nm_clean = _nm_clean.replace(_full,_short)
        lines.append(f"{i}. {_nm_clean} • {' + '.join(_on) if _on else 'an'}")
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
    try:
        d = context.job.data or {}
        uid = int(d.get("uid", 0)); eid = str(d.get("eid", "")); lg = d.get("lg", ""); mid = int(d.get("mid", 0)); orig = d.get("orig", "")
        if not uid or not eid or not mid or not orig: return
        # Summary-Details holen (da steht der Scorer wirklich drin!)
        _dets = []
        try: _dets = espn_summary_details({"id": eid}, lg) or []
        except: _dets = []
        _sc = ""
        # Auch Scoreboard als Fallback probieren
        if not _dets:
            try:
                for _ev2 in espn_scoreboard(lg):
                    if str(_ev2.get("id", "")) == eid:
                        _sc = last_scorer(_ev2, lg) or ""
                        break
            except: pass
            if _sc.strip() and _sc.strip() not in orig:
                try: await context.bot.edit_message_text(chat_id=uid, message_id=mid, text=orig + "\n" + _sc.strip())
                except: pass
            else:
                # V105: Auch hier Retry, wenn Scoreboard auch keinen Scorer hatte!
                try:
                    _try2 = int((context.job.data or {}).get("try", 1) or 1)
                    if _try2 < 3 and context.job_queue:
                        _nd2 = dict(context.job.data or {}); _nd2["try"] = _try2 + 1
                        context.job_queue.run_once(_scorer_update_job, 120, data=_nd2, name=f"scorer_retry2_{eid}_{mid}_{_try2+1}")
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
                if not any(k.lower() in _dtype.lower() for k in ["Goal", "Touchdown", "Field Goal", "Home Run", "Three Point", "Two Point", "Dunk", "Layup", "Single", "Double", "Triple", "Extra Point"]): continue
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
                _label = "Letztes Tor" if lg=="NHL" else "Letzter Touchdown" if _dtype=="Touchdown" else "Letzter Score"
                _extra = f" \u2022 {_clock} P{_per}" if lg=="NHL" and _clock else ""
                if _scorer:
                    _sc = f"   {_emo} {_label}: {_scorer} ({_team}){_extra}" if _team else f"   {_emo} {_label}: {_scorer}{_extra}"
                    break
            except: continue
        if not _sc.strip():
            # V105: Retry! Wenn nach 2 Min noch kein Scorer da ist, nochmal in 2 Min probieren (max 3x)!
            try:
                _try = int((context.job.data or {}).get("try", 1) or 1)
                if _try < 3 and context.job_queue:
                    _nd = dict(context.job.data or {}); _nd["try"] = _try + 1
                    context.job_queue.run_once(_scorer_update_job, 120, data=_nd, name=f"scorer_retry_{eid}_{mid}_{_try+1}")
            except: pass
            return
        if _sc.strip() in orig: return
        # V102: Wenn bis zum Scorer-Edit schon der XP / 2PC drin ist (+1 / +2), dann TD-Nachricht auf Endstand bringen!
        # z.B. orig "TOUCHDOWN! 7-13" -> "TOUCHDOWN + EXTRA POINT! 7-14" + Scorer! Wenn schon wieder ein TD (+6+) gefallen ist, NICHT updaten!
        _final_txt = orig + "\n" + _sc.strip()
        try:
            # Aktuellen Score holen (Scoreboard)
            _cur_scores = {}
            try:
                for _ev3 in espn_scoreboard(lg):
                    if str(_ev3.get("id", "")) == eid:
                        _cur_scores = _live_scores_of(_ev3); break
            except: _cur_scores = {}
            # Orig-Score aus orig parsen: suche "Team X @ Team Y" - wir nehmen die Team-Namen aus _sc? Einfacher: Vergleiche _cur_scores mit prev? Wir kennen orig-Score nicht direkt, also: Wenn _cur_scores fuer das Scorer-Team um genau +1/+2 groesser ist als der Score in orig, dann updaten.
            # Orig-Score extrahieren: Muster "AWAY <num> @ HOME <num>" - suche alle " <num>" vor " @ " und am Ende vor " •"
            import re as _re2
            _m = _re2.search(r"(\S.+?)\s(\d+)\s@\s(\S.+?)\s(\d+)", orig)
            if _m and _cur_scores:
                _away_nm, _away_sc, _home_nm, _home_sc = _m.group(1), int(_m.group(2)), _m.group(3), int(_m.group(4))
                # Finde welches Team gescored hat (aus _sc Team in Klammern)
                _tm = _re2.search(r"\((.+?)\)", _sc)
                _sc_team = _tm.group(1) if _tm else ""
                # Cur Score fuer Scorer-Team finden (Name enthaelt Scorer-Team oder umgekehrt)
                _cur = None; _is_away = False
                for _k, _v in _cur_scores.items():
                    if _sc_team and (_sc_team.lower() in _k.lower() or _k.lower() in _sc_team.lower()):
                        _cur = _v; _is_away = (_away_nm.lower() in _k.lower() or _k.lower() in _away_nm.lower()); break
                if _cur is not None:
                    _orig_sc = _away_sc if _is_away else _home_sc
                    _diff = _cur - _orig_sc
                    if _diff == 1:
                        # XP ist drin! Score in orig ersetzen + Label auf TOUCHDOWN + EXTRA POINT!
                        _new_away = _away_sc + 1 if _is_away else _away_sc
                        _new_home = _home_sc + 1 if not _is_away else _home_sc
                        _final_txt = _re2.sub(r"(\S.+?)\s\d+\s@\s(\S.+?)\s\d+", f"{_away_nm} {_new_away} @ {_home_nm} {_new_home}", orig, count=1)
                        _final_txt = _final_txt.replace("TOUCHDOWN!", "TOUCHDOWN + EXTRA POINT!")
                        _final_txt = _final_txt + "\n" + _sc.strip()
                    elif _diff == 2:
                        _new_away = _away_sc + 2 if _is_away else _away_sc
                        _new_home = _home_sc + 2 if not _is_away else _home_sc
                        _final_txt = _re2.sub(r"(\S.+?)\s\d+\s@\s(\S.+?)\s\d+", f"{_away_nm} {_new_away} @ {_home_nm} {_new_home}", orig, count=1)
                        _final_txt = _final_txt.replace("TOUCHDOWN!", "TOUCHDOWN + 2-POINT!")
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
                for ev in espn_scoreboard(lg):
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
                                _LIVE_SEEN[_k2] = {"scores": scores, "period": period, "state": "pre", "last_td": {}, "awaiting_resume": None, "halftime_sent": False, "crunch_sent": False, "start_sent": False}
                        continue
                    key = (uid, eid, fav)
                    prev = _LIVE_SEEN.get(key)
                    if prev is None:
                        _LIVE_SEEN[key] = {"scores": scores, "period": period, "state": state, "last_td": {}, "awaiting_resume": None, "halftime_sent": False, "crunch_sent": False, "start_sent": False}; continue
                    # V119: SPIELSTART gehört zu PERIOD! Wer Quarter-Ende + Beginn will, will auch Spielstart!
                    # (cfg.start noch drin für alle, die V118 schon an hatten - sonst geht nix verloren!)
                    if (cfg.get("period") or cfg.get("start")) and state == "in" and prev.get("state") == "pre" and not prev.get("start_sent"):
                        try: await _live_send(context, uid, eid, f"🚨 Es geht los! {game_start_label(lg)}\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg) if _score_line_short(ev, lg) else game_line(ev, lg)}\n\nViel Spaß! 🔥")
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
                            try: await _live_send(context, uid, eid, f"❌ {_label_neg}! {_team_neg}\n{LEAGUES[lg]['emoji']} {game_line(ev, lg)}\nWieder {scores.get(_team_neg, 0)} - wurde zurückgenommen!")
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
                            _time_line = f"\n⏰ {_clk}" if _clk else ""
                            _live_txt = f"{_emoji2} {_lbl2} {_short_scorer}\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}{_time_line}{_scorer_line}"
                            try:
                                _lm = await _live_send(context, uid, eid, _live_txt)
                                # V98-A: In 2 Min Scorer nachladen und reineditieren (wenn ESPN ihn dann hat)!
                                try:
                                    if _lm and getattr(_lm, "message_id", None) and context.job_queue:
                                        context.job_queue.run_once(_scorer_update_job, 120, data={"uid": uid, "eid": eid, "lg": lg, "mid": int(_lm.message_id), "orig": _live_txt}, name=f"scorer_{eid}_{_lm.message_id}")
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
                                _ht_txt = f"⏸️ Halbzeit{_ort}\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n\nKurze Pause! 🥤"
                            elif lg == "NHL":
                                _ht_txt = f"⏸️ Pause!\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n\nKurze Pause! 🥤"
                            elif lg == "NBA":
                                _ht_txt = f"⏸️ Halbzeit!\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n\nKurze Pause! 🥤"
                            else:
                                _ht_txt = f"⏸️ Pause!\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}"
                            try: await _live_send(context, uid, eid, _ht_txt)
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
                    if cfg.get("period") and state == "in" and prev["period"] is not None and period is not None and int(period) > int(prev["period"]) and not _skip_pe:
                        try: await _live_send(context, uid, eid, f"⏸️ {live_period_label(lg, prev['period'])} vorbei!\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}")
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
                                try: await _live_send(context, uid, eid, f"▶️ {live_period_label(lg, period)} läuft!\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n⏰ {live_clock(ev, lg) or ''}")
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
                                if _behind > 0: _ct = f"🔥🔥🔥 CRUNCH-TIME!!! 🔥🔥🔥\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n⏰ Noch {_mm}:{_ss:02d} zu spielen!\n\nNur {_behind} hinten — JETZT WIRD\'S WILD! 👀🔥"
                                elif _behind < 0: _ct = f"🔥🔥🔥 CRUNCH-TIME!!! 🔥🔥🔥\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n⏰ Noch {_mm}:{_ss:02d} zu spielen!\n\nNur {abs(_behind)} vorne — HALT DICH FEST! 😱🔥"
                                else: _ct = f"🔥🔥🔥 CRUNCH-TIME!!! 🔥🔥🔥\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n⏰ Noch {_mm}:{_ss:02d} zu spielen!\n\nUnentschieden — JETZT WIRD\'S WILD! 👀🔥"
                                if lg == "MLB": _ct = f"🔥🔥🔥 CRUNCH-TIME!!! 🔥🔥🔥\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n{int(period)}. Inning!\n\nJETZT WIRD\'S WILD! 👀🔥"
                                try: await _live_send(context, uid, eid, _ct)
                                except: pass
                                prev["crunch_sent"] = True
                    except: pass
                    # V124: 2-Minute Warning! Nur NFL/NCAAF, nur 4. Quarter, nur wenn eng (Diff <=8)!
                    try:
                        if cfg.get("period") and state=="in" and lg in ("NFL","NCAAF") and period is not None and int(period)==4 and not prev.get("2min_sent"):
                            _cs2=_clock_secs(ev)
                            _diff2=abs(list(scores.values())[0]-list(scores.values())[1]) if len(scores)>=2 else 999
                            if _cs2 is not None and 0 < _cs2 <= 120 and _diff2 <= 8:
                                try: await _live_send(context, uid, eid, f"⏰ 2-Minute Warning!\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n⏰ Noch 2:00 im 4. Quarter!\n\nJetzt wird\'s ernst! 👀")
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
                    if cfg.get("final") and state == "post" and prev["state"] != "post":
                        try:
                            _fs_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Final Stats", callback_data=f"finalstats:{eid}:{lg}")]])
                            # V124: Endstand custom! Fav gewonnen/verloren? Bye Week?
                            _final_txt = f"🏁 Endstand!\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n\nWas ein Spiel!"
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
                                            _final_txt = f"🏁 Sieg! {_short_fav} gewinnen! 🎉\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n\nJaaaa! Was ein Spiel!"
                                        elif _fav_sc2 < _opp_sc2:
                                            _has_next=_has_game_next_week(_fav_nm, lg)
                                            if _has_next:
                                                _final_txt = f"🏁 Schade... {_short_fav} verlieren 😔\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n\nHm, schade... Aber nächste Woche wird weiter gekämpft! 💪"
                                            else:
                                                _final_txt = f"🏁 Schade... {_short_fav} verlieren 😔\n\n{LEAGUES[lg]['emoji']} {_score_line_short(ev, lg)}\n\nHm, schade... Jetzt erstmal Bye Week, Pause!\nDanach wird weiter gekämpft! 💪"
                            except: pass
                            _em = await context.bot.send_message(chat_id=uid, text=_final_txt, reply_markup=_fs_kb)
                            if _em and getattr(_em, "message_id", None): _LIVE_MSG_IDS.setdefault((uid, str(eid)), []).append(int(_em.message_id)); _save_live_msg_ids()
                        except:
                            try: await _live_send(context, uid, eid, f"✅ Endstand: {_fav_disp}\n{LEAGUES[lg]['emoji']} {game_line(ev, lg)}")
                            except: pass
                    if state == "post" and prev["state"] != "post" and _LIVE_MSG_IDS.get((uid, str(eid))):
                        try:
                            _cq = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, löschen", callback_data=f"live_clean_yes:{eid}"), InlineKeyboardButton("❌ Nein, behalten", callback_data=f"live_clean_no:{eid}")]])
                            _qm = await context.bot.send_message(chat_id=uid, text=f"🏁 Spiel zu Ende! {_fav_disp}\n\nSoll ich die Live-Nachrichten von diesem Spiel löschen?", reply_markup=_cq)
                            if _qm and getattr(_qm, "message_id", None): _LIVE_MSG_IDS.setdefault((uid, str(eid)), []).append(int(_qm.message_id)); _save_live_msg_ids()
                        except: pass
                    _LIVE_SEEN[key] = {"scores": scores, "period": period, "state": state, "last_td": prev.get("last_td") or {}, "awaiting_resume": prev.get("awaiting_resume"), "halftime_sent": prev.get("halftime_sent", False), "crunch_sent": prev.get("crunch_sent", False), "start_sent": prev.get("start_sent", False), "2min_sent": prev.get("2min_sent", False)}
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
            if not upcoming: continue
            # Gruppieren nach Startzeit (gleiche Minute = gleiche Nachricht!)
            groups = {}
            for dt, league, ev, name in sorted(upcoming, key=lambda x: x[0]):
                k = dt.strftime("%d.%m. %H:%M")
                groups.setdefault(k, []).append((dt, league, ev, name))
            for k, items in groups.items():
                lines = [f"⏰ Reminder - In ca. {mins//60}h geht's los! ({k})\n" if mins>=60 else f"⏰ Reminder - In ca. {mins} Min geht's los! ({k})\n"]
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
                ctx.user_data["await_live_stats_pick"]=False
                await live_stats_one_cmd(update, ctx, _n-1); return
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
            ctx.user_data["my_live_list"] = None
            await next_live_pick_cmd(update, ctx, _lg_m, _eid_m); return
    # V110: Zahl für Nächste Spiele Live (wie bei Favoriten!)
    if txt.isdigit() and ctx.user_data.get("next_live_list") and not ctx.user_data.get("awaiting_fav"):
        _nl = ctx.user_data.get("next_live_list") or []
        _n = int(txt)
        if 1 <= _n <= len(_nl):
            _lg, _eid = _nl[_n-1]
            ctx.user_data["next_live_list"] = None
            await next_live_pick_cmd(update, ctx, _lg, _eid); return
    # V110: Zahl für Ergebnisse Final Stats!
    if txt.isdigit() and ctx.user_data.get("results_list") and not ctx.user_data.get("awaiting_fav"):
        _rl = ctx.user_data.get("results_list") or []
        _n2 = int(txt)
        if 1 <= _n2 <= len(_rl):
            _lg2, _eid2 = _rl[_n2-1]
            # Liste behalten, damit man gleich noch ein Spiel tippen kann? Nein - einmal reicht, danach neu wählen!
            ctx.user_data["results_list"] = None
            _uid2 = update.effective_user.id if update.effective_user else 0
            _load = await update.message.reply_text("⏳ Spiel wird zusammengefasst...\nEinen Moment, ich hol die Stats von ESPN!")
            _txt2 = get_final_stats_text(_eid2, _lg2) if _lg2 in LEAGUES else ""
            if _txt2:
                try: await ctx.bot.delete_message(chat_id=_uid2, message_id=_load.message_id)
                except: pass
                _del_rows = []
                if _lg2 == "NFL":
                    _del_rows.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{_eid2}:{_lg2}")])
                # V158: YouTube Highlights + Pressekonferenz - du entscheidest selbst!
                _del_rows.extend(_yt_buttons_for_game(_eid2, _lg2, _txt2))
                _del_rows.append([InlineKeyboardButton("🗑️ Nachrichten löschen", callback_data=f"live_clean_yes:{_eid2}")])
                _del_rows.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
                _del_kb = InlineKeyboardMarkup(_del_rows)
                await update.message.reply_text(_txt2, reply_markup=_del_kb)
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
            ctx.user_data["live_finals_list"] = None
            _uid3 = update.effective_user.id if update.effective_user else 0
            _load3 = await update.message.reply_text("⏳ Spiel wird zusammengefasst...\nEinen Moment, ich hol die Stats von ESPN!")
            _txt3 = get_final_stats_text(_eid3, _lg3) if _lg3 in LEAGUES else ""
            if _txt3:
                try: await ctx.bot.delete_message(chat_id=_uid3, message_id=_load3.message_id)
                except: pass
                _rows3 = []
                if _lg3 == "NFL":
                    _rows3.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{_eid3}:{_lg3}")])
                _rows3.extend(_yt_buttons_for_game(_eid3, _lg3, _txt3))
                _rows3.append([InlineKeyboardButton("🗑️ Nachrichten löschen", callback_data=f"live_clean_yes:{_eid3}")])
                _rows3.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
                await update.message.reply_text(_txt3, reply_markup=InlineKeyboardMarkup(_rows3))
            else:
                _kb3 = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, nochmal schauen!", callback_data=f"finalstats_retry:{_eid3}:{_lg3}"), InlineKeyboardButton("❌ Nein, danke!", callback_data=f"finalstats_no:{_eid3}:{_lg3}")]])
                try: await ctx.bot.edit_message_text(chat_id=_uid3, message_id=_load3.message_id, text="😅 Grad noch keine Stats vorhanden!\nESPN ist noch langsam!\nSoll ich in 5 Min nochmal schauen?", reply_markup=_kb3)
                except: pass
            return
    if txt.isdigit() and 1 <= int(txt) <= 10 and ctx.user_data.get("top10_list") and not ctx.user_data.get("awaiting_fav"):
        await top10_detail_cmd(update, ctx, int(txt)); return
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
                await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=main_kb())
                return
    # 2) Spitzname? z.B. "Steelers" oder "Panthers"
    if low in NICKNAME_MAP:
        cands = NICKNAME_MAP[low]
        if len(cands)==1:
            chosen = cands[0]
            favs = load_favs(); uid=str(update.effective_user.id); favs.setdefault(uid, [])
            if chosen not in favs[uid]: favs[uid].append(chosen)
            save_favs(favs)
            await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=main_kb())
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
        await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=main_kb())
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
        await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=main_kb())
        return
    # 5) Gar nichts gefunden -> nicht einfach speichern, sondern nachfragen!
    await update.message.reply_text(f"Hmm, '{name}' nicht gefunden. Probier mal den vollen Teamnamen, z.B. 'Pittsburgh Steelers'.", reply_markup=main_kb())
    return
    chosen = partial[0] if partial else name
    favs = load_favs(); uid=str(update.effective_user.id)
    favs.setdefault(uid, [])
    if chosen not in favs[uid]: favs[uid].append(chosen)
    save_favs(favs)
    await update.message.reply_text(f"✅ {chosen} zu deinen Favoriten hinzugefügt!", reply_markup=main_kb())


# V94: Hilfe passend zur Funktion, wo man grade ist! Nur beim Start / Hauptmenue die ganze Hilfe!

# V134: Hilfe in Kategorien - nicht mehr ein Batzen Text!
HELP_CATS = {
 "grund": "❓ Hilfe - Grundlagen\n\n**Gast @ Heim**\nErstes Team = Auswärts, zweites = Heim!\nZ.B. Vikings @ Packers = Vikings spielt bei den Packers!\n\n**⭐ = Dein Team**\nDas ist einer deiner Favoriten!\n\n**📺 = US-Sender**\nSender in den USA (CBS / FOX / ESPN...). Deutsche Sender zeigen wir nicht, Rechte ändern sich ständig!\n\n**📍 / 🏟️ = Stadion / Ort**\nWo das Spiel stattfindet!",
 "spiele": "❓ Hilfe - Spiele / Live / Next Games\n\n**🔴 Live**\nLäuft gerade! Nach Spielende fragt der Bot, ob er Live-Nachrichten löschen soll!\n\n**⏭️ Next Games**\nHeute / Morgen = alle Spiele! Nur Favoriten = nur deine Teams!\nDa kannst du auch 🔴 Live für ein Spiel anmachen (z.B. München)!\n\n**✅ Ergebnisse**\nWie die letzten Spiele ausgingen, mit Final Stats!",
 "tabellen": "❓ Hilfe - Tabellen / Top 10\n\n**📊 Tabellen**\nW-L-OTL = Siege - Niederlagen - Overtime-Niederlagen.\nNHL: Sieg = 2 Punkte, Overtime-Niederlage = 1 Punkt!\n\n**🏆 Top 10**\nTippe Zahl 1-10 für Rating + Warum so bewertet!\nRating (z.B. ⭐ 9,9/10) steht nur im Detail!",
 "benach": "❓ Hilfe - Benachrichtigungen\n\nIn ⚙️ Einstellungen → 🔔 Benachrichtigungen:\n**⏰ Reminder** - 3h / 2h / 1h / 30 Min / Aus. 2 Favoriten gleichzeitig = 1 Nachricht für beide, mit Sender!\n**🔴 Live-Scores** - Nur für Favoriten, pro Team: Jeder Score / Spielstart + Quarter-Wechsel / Endstand / Crunch-Time / Spiel-Breaking!\nAlles aus = kein Spam!",
 "news": "❓ Hilfe - News / Verletzungen / Breaking\n\n**📰 News** - Nur deine Favoriten! Nur Headline + Link!\nQuelle: ESPN! Artikel sind auf Englisch!\nKein Push-Spam - du holst dir News, wenn du willst!\n\n**🌍 Liga-Breaking** - In News ganz oben als Toggle! Nur große Sachen: International Series, Schedule, Super Bowl, Playoffs, Trade Deadline! Push, aber nur 1x!\n\n**🚨 Spiel-Breaking** - Bei Favorit / Live-Spiel: Nur OUT / RULED OUT / Ejection! Nur 1x pro Spieler!\n\n**🏥 Verletzungen** - Daten von Sleeper (NFL) / ESPN (NBA, NHL, MLB). Offizielle Team-Apps können bis zu 15 Min schneller sein - Bot holt alle 15 Min neu!",
 "fenster": "❓ Hilfe - Fenster\n\n**🪟 Fenster**\nAuswahl = Fenster ändert sich! Detail = neues Fenster! ✖️ = Fenster weg!\n\n**Einfach auf Knöpfe drücken** - kein @, kein Befehl nötig!",
}
HELP_SHORT = {
    "top10": "❓ Hilfe - Top 10\n\nTippe eine Zahl 1-10 in den Chat für Rating + Warum!\nRating steht nur im Detail, nicht in der Übersicht!",
    "tables": "❓ Hilfe - Tabellen\n\nW-L-OTL = Siege - Niederlagen - Overtime-Niederlagen.\nBei NHL: Sieg = 2 Punkte, Overtime-Niederlage = 1 Punkt!",
    "next": "❓ Hilfe - Next Games\n\nHeute / Morgen = alle Spiele!\nNur Favoriten = nur deine Teams!",
    "live": "❓ Hilfe - Live\n\nLäuft gerade!\nNach Spielende fragt der Bot, ob er die Live-Nachrichten löschen soll!",
    "results": "❓ Hilfe - Ergebnisse\n\nWelche Liga? Dann siehst du, wie die letzten Spiele ausgingen!",
    "settings": "❓ Hilfe - Einstellungen\n\nHier: Favoriten + Benachrichtigungen!\nReminder + Live-Scores sind unter Benachrichtigungen!",
    "notif": "❓ Hilfe - Benachrichtigungen\n\nReminder + Live-Scores!\nLive nur für Favoriten, pro Team: Jeder Score / Perioden-Ende + Weiter / Endstand!",
    "fav": "❓ Hilfe - Favoriten\n\nFavorit hinzufügen / entfernen!\n⭐ = dein Team!",
    "injuries": "❓ Hilfe - Verletzungen\n\nDaten von Sleeper / ESPN, bis zu 15 Min verzögert!\nOffizielle Team-Apps sind schneller!",
    "game_info": "❓ Hilfe - Mehr Infos\n\nWetter, Form, Wer fehlt?\nWähle Liga → Spiel → Detail!",
}


def get_expert_stats_text(eid, lg):
    # V157: SofaScore-Style! Gruppen: Offense / Passen / Laufspiel / Andere.
    # Final Stats bleiben wie sie sind! Nur Experten-Stats wird SofaScore-Style!
    # Alles aus ESPN Boxscore + Drives. Kein EPA/CPOE. Kein neuer Key!
    # Unsere 5 alten Experten-Werte (Points per Drive, 3-and-Out, Explosive, Sack Rate) bleiben drin, in Offense!
    try:
        if lg != "NFL": return ""
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
            # Exakt zuerst, dann Teilstring - aber "attempts" darf nie Rushing treffen wenn Passing gesucht wird!
            for _k in keys:
                if sd.get(_k.lower()): return sd.get(_k.lower())
            for _k in keys:
                for _kk, _vv in sd.items():
                    if _k.lower() in _kk.lower() or _kk.lower() in _k.lower():
                        if _vv not in ("", "-"): return _vv
            return ""
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
            # 3-and-Out: max 3 Offense-Plays + Punt (Punt = 4. Play bei ESPN!)
            _off = [p for p in _plays if isinstance(p, dict) and str(p.get("type", {}).get("text", "") if isinstance(p.get("type"), dict) else p.get("type", "")).lower() not in ("punt", "kickoff", "field goal", "extra point")]
            if len(_off) <= 3 and ("punt" in _res or "downs" in _res or "down" in _res):
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
            v = _pick(sd, ["totaltouchdowns", "total touchdowns", "touchdowns"])
            if v and _int(v) is not None: return str(_int(v))
            pt = _int(_pick(sd, ["passing touchdowns", "passingTouchdowns"]))
            rt = _int(_pick(sd, ["rushing touchdowns", "rushingTouchdowns"]))
            if pt is not None or rt is not None: return str((pt or 0) + (rt or 0))
            return ""
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
            v = _pick(sd, ["sacks", "sack"])
            _, y = _split_pair(v) if v else (None, None)
            return y or 0
        def _gross(sd):
            n = _num(_net(sd))
            if n is None: return ""
            return str(int(n + _sack_yards(sd)))
        va_n, vb_n = _both(_net); va_g, vb_g = _both(_gross)
        if va_n or vb_n: lines.append(f"Net Passing Yards: {_fmt_pair(va_n, vb_n)}")
        if va_g or vb_g: lines.append(f"Gross Passing Yards: {_fmt_pair(va_g, vb_g)}")
        def _ptd(sd):
            v = _pick(sd, ["passing touchdowns", "passingtouchdowns", "passing td"])
            return str(_int(v)) if v and _int(v) is not None else ""
        va, vb = _both(_ptd)
        if va or vb: lines.append(f"Touchdowns durch Pässe: {_fmt_pair(va, vb)}")
        def _int_thrown(sd):
            v = _pick(sd, ["interceptionsthrown", "interceptions thrown", "passinginterceptions", "interceptions"])
            return str(_int(v)) if v and _int(v) is not None else ""
        va, vb = _both(_int_thrown)
        if va or vb: lines.append(f"Geworfene Interceptions: {_fmt_pair(va, vb)}")
        # Yards pro Versuch = Net / (Attempts + Sacks) - wie SofaScore!
        def _ypa(sd):
            n = _num(_net(sd))
            att = None
            for _k in ("passingattempts", "passattempts", "passing attempts", "pass attempts"):
                _v = _pick(sd, [_k])
                if _v:
                    _s2 = str(_v).strip()
                    att = float(_s2.split("/")[-1].strip()) if "/" in _s2 else _num(_s2)
                    if att is not None: break
            if att is None:
                _ca = _pick(sd, ["comp/att", "completions/attempts"])
                if _ca and "/" in str(_ca):
                    try: att = float(str(_ca).split("/")[-1].strip())
                    except: att = None
            sacks_n, _ = _split_pair(_pick(sd, ["sacks", "sack"])) if _pick(sd, ["sacks", "sack"]) else (0, 0)
            sacks_n = sacks_n or 0
            if n is None or att is None or (att + sacks_n) <= 0: return ""
            return f"{n/(att+sacks_n):.1f}"
        va, vb = _both(_ypa)
        if va or vb: lines.append(f"Durchschn. Passing Yards pro Versuch: {_fmt_pair(va, vb)}")
        # Comp/Att
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
        # Sack Rate (eigene kassierte Sacks!)
        def _sackrate(sd):
            sacks_n, _ = _split_pair(_pick(sd, ["sacks", "sack"])) if _pick(sd, ["sacks", "sack"]) else (0, 0)
            sacks_n = sacks_n or 0
            att = None
            for _k in ("passingattempts", "passing attempts"):
                _v = _pick(sd, [_k])
                if _v:
                    _s2 = str(_v).strip()
                    att = float(_s2.split("/")[-1].strip()) if "/" in _s2 else _num(_s2)
                    if att is not None: break
            if att is None or (att + sacks_n) <= 0: return ""
            return f"{round(sacks_n/(att+sacks_n)*100)}%"
        va, vb = _both(_sackrate)
        if va or vb: lines.append(f"Sack Rate: {_fmt_pair(va, vb)}")
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
            v = _pick(sd, ["rushing touchdowns", "rushingtouchdowns"])
            return str(_int(v)) if v and _int(v) is not None else ""
        va, vb = _both(_rtd)
        if va or vb: lines.append(f"Touchdowns durch Lauf: {_fmt_pair(va, vb)}")
        # ============ ANDERE ============
        lines.append("")
        lines.append("--- Andere ---")
        def _pen_n(sd):
            v = _pick(sd, ["penalties", "penalty"])
            x, _ = _split_pair(v) if v else (None, None)
            return str(x) if x is not None else ""
        def _pen_y(sd):
            v = _pick(sd, ["penalties", "penalty"])
            _, y = _split_pair(v) if v else (None, None)
            return str(y) if y is not None else ""
        va, vb = _both(_pen_n)
        if va or vb: lines.append(f"Strafen: {_fmt_pair(va, vb)}")
        va, vb = _both(_pen_y)
        if va or vb: lines.append(f"Penalty Yards: {_fmt_pair(va, vb)}")
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
        lines.append("Quelle: ESPN Play-by-Play + Boxscore - NFL only - Nach dem Spiel am genauesten!")
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
                if _lbl in ("3rd Down","4th Down","Strafen"):
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
                if _lbl in ("3rd Down","4th Down","Strafen"):
                    va=_v135_slash(va) if va else va; vb=_v135_slash(vb) if vb else vb
                if va or vb: lines.append(f"{_lbl}: {va or '-'} - {vb or '-'}")
                elif _lbl=="Sacks":
                    lines.append("Sacks: - - -")
        elif lg == "NHL":
            for _k,_lbl in [("shotsOnGoal","Schüsse"),("hits","Hits"),("faceoffWinPct","Faceoffs"),("powerPlayGoals","PP Tore")]:
                va = sa.get(_k.lower(),"") or sa.get(_lbl.lower(),"")
                vb = sb.get(_k.lower(),"") or sb.get(_lbl.lower(),"")
                if _lbl in ("3rd Down","4th Down","Strafen"):
                    va=_v135_slash(va) if va else va; vb=_v135_slash(vb) if vb else vb
                if va or vb: lines.append(f"{_lbl}: {va or '-'} - {vb or '-'}")
                elif _lbl=="Sacks":
                    lines.append("Sacks: - - -")
        elif lg == "MLB":
            for _k,_lbl in [("hits","Hits"),("homeRuns","HR"),("RBIs","RBI"),("errors","Errors"),("strikeouts","Strikeouts"),("walks","Walks")]:
                va = sa.get(_k.lower(),"") or sa.get(_lbl.lower(),"")
                vb = sb.get(_k.lower(),"") or sb.get(_lbl.lower(),"")
                if _lbl in ("3rd Down","4th Down","Strafen"):
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
            if lg == "NFL":
                _rows_retry.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{eid}:{lg}")])
            _rows_retry.extend(_yt_buttons_for_game(eid, lg, _txt))
            _rows_retry.append([InlineKeyboardButton("🗑️ Nachrichten löschen", callback_data=f"live_clean_yes:{eid}")])
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
    return {"score": bool(d.get("score", False)), "period": bool(d.get("period", False)), "final": bool(d.get("final", False)), "crunch": bool(d.get("crunch", False)), "start": bool(d.get("start", False)), "breaking": bool(d.get("breaking", False)), "lg": d.get("lg",""), "name": d.get("name","")}
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
    for offset in (0,1):
        d = today + timedelta(days=offset)
        ds = d.strftime("%Y%m%d")
        for ev in espn_scoreboard(league, dates=ds):
            eid = str(ev.get("id",""))
            if eid in seen: continue
            seen.add(eid)
            state = ev.get("status",{}).get("type",{}).get("state","")
            if state == "post": continue
            evs.append(ev)
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

async def next_live_pick_cmd(update, ctx, league, eid):
    # Spiel-Name finden
    _name = f"Spiel {eid}"
    try:
        from datetime import date as _date
        today = _date.today()
        for offset in (0,1,2):
            d = today + timedelta(days=offset)
            for ev in espn_scoreboard(league, dates=d.strftime("%Y%m%d")):
                if str(ev.get("id","")) == str(eid):
                    _teams,_ = event_teams(ev)
                    _name = game_line(ev, league)
                    break
    except: pass
    # In Settings speichern (Name + Liga), damit live_job es findet!
    try:
        s = load_settings(); s.setdefault(str(update.effective_user.id), {}); s[str(update.effective_user.id)].setdefault("oneoff_live", {}).setdefault(str(eid), {})
        s[str(update.effective_user.id)]["oneoff_live"][str(eid)]["lg"] = league
        s[str(update.effective_user.id)]["oneoff_live"][str(eid)]["name"] = _name
        save_settings(s)
    except: pass
    cfg = get_oneoff_live(update.effective_user.id, eid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅' if cfg['score'] else '❌'} Jeder Score", callback_data=f"next_live_toggle:{league}:{eid}:score")],
        [InlineKeyboardButton(f"{'✅' if cfg['period'] else '❌'} {period_toggle_label(league)}", callback_data=f"next_live_toggle:{league}:{eid}:period")],
        [InlineKeyboardButton(f"{'✅' if cfg['final'] else '❌'} Endstand", callback_data=f"next_live_toggle:{league}:{eid}:final")],
        [InlineKeyboardButton(f"{'✅' if cfg.get('crunch') else '❌'} Crunch-Time (8 Min, knapp!)", callback_data=f"next_live_toggle:{league}:{eid}:crunch")],
        [InlineKeyboardButton(f"{'✅' if cfg.get('breaking') else '❌'} 🚨 Spiel-Breaking", callback_data=f"next_live_toggle:{league}:{eid}:breaking")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await _cb_edit(update, f"🔴 Live für ein Spiel\n\n{_name}\n\nTippe an / aus. Nur was du anmachst, schicke ich dir!\nNach dem Spiel wird es automatisch wieder aus!", kb)

async def on_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data=q.data
    # V94: Merken, in welcher Funktion man grade ist - damit Hilfe passend dazu kommt!
    try:
        _sec_map = {"top10": "top10", "tables": "tables", "next": "next", "live": "live", "results": "results", "settings": "settings", "notif": "notif", "fav": "fav", "injur": "injuries", "game_info": "game_info"}
        for _k, _v in _sec_map.items():
            if data.startswith(_k): ctx.user_data["last_section"] = _v; break
        if data == "back": ctx.user_data["last_section"] = "main"
    except: pass
    if data=="close":
        # V95: Hauptmenue nach /start bleibt IMMER da - nie loeschen!
        try:
            if _is_main_msg(q.message): return
        except: pass
        # V113: Fenster + deine 1en + Listen dazwischen alle weg!
        try:
            _uid_c = update.effective_user.id if update.effective_user else 0
            await _chain_delete_all(ctx, _uid_c, q.message.message_id if q.message else None)
        except: pass
        try: await q.message.delete()
        except:
            try: await q.message.edit_text("✖️ Fenster geschlossen!\n\nDein Hauptmenü nach /start ist noch da! 👆", reply_markup=None)
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
                if _lg == "NFL":
                    _fs_rows.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{_eid}:{_lg}")])
                _fs_rows.extend(_yt_buttons_for_game(_eid, _lg, _txt))
                _fs_rows.append([InlineKeyboardButton("🗑️ Nachrichten löschen", callback_data=f"live_clean_yes:{_eid}")])
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
        # V154: Experten-Stats Stufe 1, nur NFL!
        try:
            _parts = data.split(":"); _eid = _parts[1]; _lg = _parts[2] if len(_parts)>2 else ""
            _uid = update.effective_user.id if update.effective_user else 0
            if _lg != "NFL":
                await q.answer("Experten-Stats gibt es erst mal nur für NFL!", show_alert=True); return
            _load = await ctx.bot.send_message(chat_id=_uid, text="🧠 Experten-Stats werden berechnet...\nEinen Moment, ich hol die Drives von ESPN!")
            _txt = get_expert_stats_text(_eid, _lg)
            if _txt:
                try: await ctx.bot.delete_message(chat_id=_uid, message_id=_load.message_id)
                except: pass
                _ekb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Nachrichten löschen", callback_data=f"live_clean_yes:{_eid}")],[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
                await ctx.bot.send_message(chat_id=_uid, text=_txt, reply_markup=_ekb)
            else:
                try: await ctx.bot.edit_message_text(chat_id=_uid, message_id=_load.message_id, text="😅 Grad keine Experten-Stats da!\nESPN hat noch keine Drives für das Spiel!\nVersuch es nach dem Spiel nochmal!")
                except: pass
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
                if _lg2 == "NFL":
                    _del_rows2.append([InlineKeyboardButton("🧠 Experten-Stats", callback_data=f"expert_stats:{_eid2}:{_lg2}")])
                _del_rows2.extend(_yt_buttons_for_game(_eid2, _lg2, _txt2))
                _del_rows2.append([InlineKeyboardButton("🗑️ Nachrichten löschen", callback_data=f"live_clean_yes:{_eid2}")])
                _del_rows2.append([InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")])
                _del_kb = InlineKeyboardMarkup(_del_rows2)
                await ctx.bot.send_message(chat_id=_uid2, text=_txt2, reply_markup=_del_kb)
            else:
                _kb2 = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ja, nochmal schauen!", callback_data=f"finalstats_retry:{_eid2}:{_lg2}"), InlineKeyboardButton("❌ Nein, danke!", callback_data=f"finalstats_no:{_eid2}:{_lg2}")]])
                try: await ctx.bot.edit_message_text(chat_id=_uid2, message_id=_load.message_id, text="😅 Grad noch keine Stats vorhanden!\nESPN ist noch langsam!\nSoll ich in 5 Min nochmal schauen?", reply_markup=_kb2)
                except: pass
        except: pass
    elif data == "next_live_league": await next_live_league_cmd(update, ctx)
    elif data.startswith("next_live_list:"): await next_live_list_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("next_live_pick:"):
        _pp = data.split(":"); await next_live_pick_cmd(update, ctx, _pp[1], _pp[2])
    elif data.startswith("next_live_toggle:"):
        _pp = data.split(":"); _lg3 = _pp[1]; _eid3 = _pp[2]; _kind3 = _pp[3]
        set_oneoff_live_toggle(update.effective_user.id, _eid3, _kind3)
        await next_live_pick_cmd(update, ctx, _lg3, _eid3)
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
        try: await q.message.delete()
        except:
            try: await q.message.edit_text("⬅️ Zurück zum Hauptmenü!\n\nDein Hauptmenü nach /start ist noch da! 👆", reply_markup=None)
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
            _hkb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Grundlagen (Gast @ Heim, ⭐, 📺)", callback_data="help_cat:grund")],
                [InlineKeyboardButton("🏈 Spiele / Live / Next Games", callback_data="help_cat:spiele")],
                [InlineKeyboardButton("📊 Tabellen / Top 10", callback_data="help_cat:tabellen")],
                [InlineKeyboardButton("🔔 Benachrichtigungen", callback_data="help_cat:benach")],
                [InlineKeyboardButton("📰 News / Verletzungen / Breaking", callback_data="help_cat:news")],
                [InlineKeyboardButton("🪟 Fenster", callback_data="help_cat:fenster")],
                [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
            ])
            await q.message.reply_text("❓ Hilfe - Was willst du wissen?\n\nTippe eine Kategorie an - nur das Thema, kein Batzen Text!", reply_markup=_hkb)
        elif _sec in HELP_SHORT:
            _hkb = InlineKeyboardMarkup([[InlineKeyboardButton("📖 Ganze Hilfe", callback_data="help_all")], [InlineKeyboardButton("⬅️ Zurück", callback_data="back")], [InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
            await q.message.edit_text(HELP_SHORT[_sec], reply_markup=_hkb)
        else:
            await q.message.edit_text(HELP_TEXT, reply_markup=main_kb())
    elif data.startswith("help_cat:"):
        _k=data.split(":")[1]; _txt=HELP_CATS.get(_k,"❓ Hilfe\n\nTippe eine Kategorie an!")
        _hkb2=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Zurück zu Hilfe", callback_data="help")],[InlineKeyboardButton("✖️ Fenster schließen", callback_data="close")]])
        try: await q.message.edit_text(_txt, reply_markup=_hkb2)
        except: await q.message.reply_text(_txt, reply_markup=_hkb2)
    elif data=="help_all":
        # V95: Ganze Hilfe auch nie ins Hauptmenue reinschreiben!
        try:
            if _is_main_msg(q.message): await q.message.reply_text(HELP_TEXT, reply_markup=main_kb())
            else: await q.message.edit_text(HELP_TEXT, reply_markup=main_kb())
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
    elif data.startswith("news_team:"): await news_team_cmd(update, ctx, int(data.split(":")[1]))
    elif data=="notif": await notif_cmd(update, ctx)
    elif data=="notif_master":
        _m = not get_live_master(update.effective_user.id); set_live_master(update.effective_user.id, _m)
        await notif_cmd(update, ctx)
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
    elif data=="settings_sender": await q.message.reply_text("📺 Sender-Anzeige: 🇺🇸 Original (CBS / FOX / ESPN ...)\n\nDeutsche Sender wechseln wir nicht - die Rechte ändern sich ständig (NFL jetzt RTL / Sky / Game Pass) und wir wollen dir nichts Falsches zeigen!", reply_markup=main_kb())
    elif data.startswith("reminder_set:"):
        _v = data.split(":")[1]
        _mins = None if _v=="off" else int(_v)
        set_reminder_minutes(update.effective_user.id, _mins)
        await q.message.reply_text(f"✅ Reminder-Zeit eingestellt: {fmt_reminder(_mins)}!\n\nSpielen 2 deiner Favoriten gleichzeitig, kriegst du 1 Nachricht für beide - mit Sender!", reply_markup=main_kb())
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
    elif data.startswith("top10_league:"): await top10_league_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("top10_detail:"): await top10_detail_cmd(update, ctx, int(data.split(":")[1]))
    elif data=="next": await next_hub_cmd(update, ctx)
    elif data=="next_today": await heute_morgen(update, ctx, False)
    elif data=="next_tomorrow": await heute_morgen(update, ctx, True)
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
        await q.message.reply_text(f"✅ {_rem} entfernt!", reply_markup=main_kb())
    elif data=="heute": await heute_morgen(update, ctx, False)
    elif data=="morgen": await heute_morgen(update, ctx, True)
    elif data=="results": await results_cmd(update, ctx)
    elif data=="results_mine": await results_mine_cmd(update, ctx)
    elif data.startswith("results_league:"): await results_league_cmd(update, ctx, data.split(":")[1])
    elif data=="live": await live_cmd(update, ctx)
    elif data=="live_stats": await live_stats_cmd(update, ctx)
    elif data.startswith("live_stats_one:"): await live_stats_one_cmd(update, ctx, int(data.split(":")[1]))
    elif data=="remind": await remind_cmd(update, ctx)
    elif data=="fav_add":
        ctx.user_data["awaiting_fav"]=True
        await q.message.reply_text("Bitte Teamnamen eingeben:")
    elif data=="fav_list":
        favs=favs_for(update.effective_user.id)
        _kb=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Favorit hinzufügen", callback_data="fav_add")],[InlineKeyboardButton("🗑️ Favorit entfernen", callback_data="fav_remove")],[InlineKeyboardButton("🗑️ Alle Favoriten löschen", callback_data="fav_clear")],[InlineKeyboardButton("⬅️ Zurück", callback_data="back")]])
        await q.message.reply_text("⭐ Deine Favoriten:\n" + ("\n".join([f"• {f}" for f in favs]) if favs else "Noch keine."), reply_markup=_kb)
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
        else:
            print("JobQueue: kein APScheduler - Reminder aus, Bot laeuft trotzdem.")
    except Exception as e:
        print("JobQueue:", e)
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("✅ USA Sport Radar Bot online - V158 - Favoriten-Ergebnisse + YouTube!")
    logger.warning("✅ USA Sport Radar Bot online - V158 - Favoriten-Ergebnisse + YouTube!")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()
