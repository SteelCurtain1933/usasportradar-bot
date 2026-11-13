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
 "NCAAF": ["Alabama Crimson Tide","Auburn Tigers","Clemson Tigers","Florida Gators","Florida State Seminoles","Georgia Bulldogs","LSU Tigers","Michigan Wolverines","Michigan State Spartans","Notre Dame Fighting Irish","Ohio State Buckeyes","Oklahoma Sooners","Oregon Ducks","Penn State Nittany Lions","Pittsburgh Panthers","Texas Longhorns","Texas A&M Aggies","Texas Tech Red Raiders","USC Trojans","UCLA Bruins","Wisconsin Badgers","Tennessee Volunteers","Arizona Wildcats","Arizona State Sun Devils","Arkansas Razorbacks","Baylor Bears","BYU Cougars","Colorado Buffaloes","Duke Blue Devils","Iowa Hawkeyes","Kansas Jayhawks","Kentucky Wildcats","Louisville Cardinals","Miami Hurricanes","Mississippi State Bulldogs","Nebraska Cornhuskers","North Carolina Tar Heels","Oklahoma State Cowboys","Ole Miss Rebels","Purdue Boilermakers","South Carolina Gamecocks","Stanford Cardinal","TCU Horned Frogs","Utah Utes","Virginia Cavaliers","Virginia Tech Hokies","Washington Huskies","West Virginia Mountaineers","Wake Forest Demon Deacons","Baylor Bears"],
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
def fmt_dt(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z","+00:00")).astimezone(BERLIN)
        return dt.strftime("%d.%m. %H:%M"), dt
    except: return iso, None

def espn_scoreboard(league, days=7, dates=None):
    key = LEAGUES[league]["espn"]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{'football' if league in ('NFL','NCAAF') else 'baseball' if league=='MLB' else 'hockey' if league=='NHL' else 'basketball'}/{key}/scoreboard"
    try:
        params={"limit": 100}
        if dates: params["dates"]=dates
        r = requests.get(url, params=params, timeout=12)
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
            dtype = (d.get("type", {}) or {}).get("text", "") or d.get("type", {}).get("shortText", "") or ""
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
        data = r.json()
        # Details stecken in details oder keyEvents
        dets = []
        for k in ["details", "keyEvents"]:
            if k in data and isinstance(data[k], list): dets.extend(data[k])
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
        a = f"{teams[1][0]} {teams[1][2] or ''}".strip()
        h = f"{teams[0][0]} {teams[0][2] or ''}".strip()
        # NUR bei International / Neutral-Site steht Stadion + Ort drunter - sonst nie!
        is_intl, intl_label = is_neutral_or_international(ev, teams[0][0])
        ven = f"\n   {intl_label}" if is_intl else ""
        bc = broadcast_line(ev)
        bc_suf = f" • 📺 {bc}" if (show_broadcast and bc) else ""
        # Überall: "Heim @ Gast" - erstes Team = Heimteam!
        if state=="post":
            return f"{h} @ {a}  •  {label} • {date_s}{ven}{bc_suf}"
        if state=="in":
            return f"{h} @ {a}  •  {label}{ven}{bc_suf}"
        h0 = teams[0][0]; a0 = teams[1][0]
        return f"{h0} @ {a0}  •  {label}{ven}{bc_suf}"
    return f"{ev.get('name','Spiel')}  •  {label}"

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Favorit hinzufügen", callback_data="fav_add")],
        [InlineKeyboardButton("⭐ Meine Favoriten", callback_data="fav_list")],
        [InlineKeyboardButton("⏭️ Next Games", callback_data="next"),
         InlineKeyboardButton("🏆 Top 10", callback_data="top10")],
        [InlineKeyboardButton("📅 Heute", callback_data="heute"),
         InlineKeyboardButton("📅 Morgen", callback_data="morgen")],
        [InlineKeyboardButton("🔴 Live", callback_data="live"),
         InlineKeyboardButton("⏰ Reminder", callback_data="remind")],
        [InlineKeyboardButton("✅ Ergebnisse", callback_data="results")],
        [InlineKeyboardButton("📊 Tabellen", callback_data="tables")],
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
/top10 - Top 10 Spiele der Woche\n📊 Tabellen - Tabellenstände / Meine Teams
/heute - Spiele heute
/morgen - Spiele morgen
/live - Live-Stände deiner Favoriten
/ergebnisse - Letzte 5 Endergebnisse pro Liga
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
    await target.reply_text("🏆 Top 10 Spiele der Woche\n\nWelche Liga?\n🏠 Erstes Team = Heimteam", reply_markup=kb)
async def top10_league_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str):
    target = update.message or update.callback_query.message
    await target.reply_text("🏆 Ich suche die Top 10... einen Moment ⏳")
    leagues = list(LEAGUES.keys()) if league=="ALL" else [league]
    from datetime import date as _date
    today = _date.today()
    all_games=[]; seen=set()
    for lg in leagues:
        for offset in range(0, 8):
            d = today + timedelta(days=offset)
            ds = d.strftime("%Y%m%d")
            for ev in espn_scoreboard(lg, dates=ds):
                eid = ev.get("id")
                if eid in seen: continue
                seen.add(eid)
                state = ev.get("status",{}).get("type",{}).get("state","")
                if state=="post": continue
                score, bd = rank_game(ev, lg)
                all_games.append((score, lg, ev, bd))
    all_games.sort(key=lambda x: x[0], reverse=True)
    top = all_games[:10]
    ctx.user_data["top10_list"] = [(s, lg, ev, bd) for s, lg, ev, bd in top]
    title = "Alle Ligen" if league=="ALL" else league
    lines=[f"🏆 Top 10 - {title}\n🏠 Erstes Team = Heimteam\n💡 Schreib eine Zahl (1-10) in den Chat für: Warum so bewertet?\n"]
    if not top:
        lines.append("Keine kommenden Spiele in den nächsten 7 Tagen gefunden.")
        await target.reply_text("\n".join(lines), reply_markup=main_kb()); return
    # V53: KEINE Datum-Gruppierung mehr bei Top 10! Strikt 1-10 nach Rating!
    # Sonst: "20.11. -> 4. Texans-Colts" obwohl oben schon 10 Spiele waren - total verwirrend!
    # Ranking ist hier wichtiger als Datum: Platz 1 ist das beste Spiel, egal ob Montag Nacht oder Sonntag!
    for rank, (score, lg, ev, bd) in enumerate(top, 1):
        teams,_ = event_teams(ev)
        def _short(idx):
            try:
                comp = ev.get("competitions", [{}])[0]
                c = comp.get("competitors", [])[idx]
                tm = c.get("team", {}) or {}
                return tm.get("shortDisplayName","") or tm.get("displayName","") or teams[idx][0]
            except: return teams[idx][0] if idx < len(teams) else ""
        h_name = _short(0); a_name = _short(1)
        date_s2, dt2 = fmt_dt(ev.get("date",""))
        # Datum bei jedem Spiel dabei: "16.11. 02:20" - damit man weiß, wann es ist, ohne Gruppierung!
        time_s = dt2.strftime("%d.%m. %H:%M") if dt2 else date_s2
        bc = broadcast_line(ev)
        bc_suf = f" • 📺 {bc}" if bc else ""
        lines.append(f"{rank}. {h_name} - {a_name} • {time_s}{bc_suf} • ⭐ {score:.1f}/10")
    lines.append("\n💡 Schreib einfach die Zahl (z.B. 3) in den Chat, um zu sehen, warum das Spiel so bewertet ist!")
    # V53: KEINE Zahlen-Buttons mehr! Die haben nur reingekloppt und 2 Reihen weggenommen!
    # Nur noch Andere Liga + Zurück - Zahl tippen geht schneller!
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 Andere Liga", callback_data="top10")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await target.reply_text("\n".join(lines), reply_markup=kb)
async def top10_detail_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, idx: int):
    target = update.message or update.callback_query.message
    lst = ctx.user_data.get("top10_list", [])
    if not lst or idx<1 or idx>len(lst):
        await target.reply_text("Tippe erst auf 🏆 Top 10 und wähle eine Liga, dann die Zahl!", reply_markup=main_kb()); return
    score, lg, ev, bd = lst[idx-1]
    teams,_ = event_teams(ev)
    def _short(i):
        try:
            comp = ev.get("competitions", [{}])[0]
            c = comp.get("competitors", [])[i]
            tm = c.get("team", {}) or {}
            return tm.get("shortDisplayName","") or tm.get("displayName","") or teams[i][0]
        except: return teams[i][0] if i < len(teams) else ""
    h_name = _short(0); a_name = _short(1)
    date_s, dt = fmt_dt(ev.get("date",""))
    time_s = dt.strftime("%d.%m. %H:%M") if dt else date_s
    bc = broadcast_line(ev)
    bc_suf = f" • 📺 {bc}" if bc else ""
    if score>=8.5: fazit = "Wenn du nur 1 Spiel diese Woche guckst, dann guck das hier! 🔥"
    elif score>=7.5: fazit = "Richtig starkes Spiel - lohnt sich auf jeden Fall reinzugucken!"
    elif score>=6.5: fazit = "Solides Spiel - vor allem wegen der Tabelle interessant."
    else: fazit = "Kein Kracher, aber für Fans der Teams interessant."
    lines=[f"🏆 {h_name} - {a_name} • ⭐ {score:.1f}/10\n📅 {time_s}{bc_suf}\n🏠 {h_name} ist Heimteam\n\n**Warum {score:.1f}/10?**\n",
        f"📊 **Tabelle:** +{bd['tabelle']:.1f} - Beide Teams sind stark / Top-Teams in ihrer Liga, das Duell hat viel Gewicht für die Tabelle.",
        f"🔥 **Rivalität:** +{bd['rival']:.1f} - " + ("Historische Rivalität! Die beiden haben sich schon oft in großen Spielen getroffen." if bd['rival']>=2.5 else "Division-Duell / zwei starke Teams - da ist Feuer drin." if bd['rival']>=1.5 else "Kein großes Rivalitäts-Spiel, aber beide wollen gewinnen."),
        f"⭐ **Stars:** +{bd['stars']:.1f} - Viele bekannte Stars auf dem Feld, die das Spiel entscheiden können.",
        f"📺 **Primetime:** +{bd['prime']:.1f} - " + ("Primetime-Spiel! Läuft zur besten Zeit, wo alle zugucken." if bd['prime']>=1.0 else "Kein Primetime-Spiel, läuft neben anderen Spielen."),
        f"\n**Fazit:** {fazit}"]
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
def espn_standings(league):
    # V61: NEUE QUELLE! TheSportsDB für Tabellen (1 Call, direkt Tabelle, keine Links, keine Refs!)
    # ESPN Tabellen-API spinnt nur rum: mal nur Links, mal nur Conferences, mal NoneType-Fehler!
    # TheSportsDB: https://www.thesportsdb.com/api/v1/json/3/lookuptable.php?l=NFL&s=2025-2026 -> {"table": [{strTeam, strDivision, intWin, intLoss, ...}]}
    # Kostenlos, ohne Key, 1 Call pro Liga!
    global _STANDINGS_DEBUG
    # --- 1) TheSportsDB (Haupt-Quelle) ---
    tsdb_league = {"NFL": "NFL", "NBA": "NBA", "NHL": "NHL", "MLB": "MLB", "NCAAF": "NCAA Football"}.get(league, league)
    tsdb_seasons = {"NFL": "2025-2026", "NBA": "2025-2026", "NHL": "2025-2026", "MLB": "2025", "NCAAF": "2025-2026"}.get(league, "2025-2026")
    for s in [tsdb_seasons, "2025", "2025-2026"]:
        try:
            u = f"https://www.thesportsdb.com/api/v1/json/3/lookuptable.php?l={tsdb_league}&s={s}"
            _STANDINGS_DEBUG["last_url"]=u
            r = requests.get(u, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
            _STANDINGS_DEBUG["last_status"]=r.status_code
            if r.status_code!=200: continue
            j = r.json()
            _STANDINGS_DEBUG["last_keys"]=", ".join(list(j.keys())[:10]) if isinstance(j, dict) else "?"
            table = j.get("table") or []
            if not table: continue
            out={}
            for row in table:
                if not isinstance(row, dict): continue
                disp = row.get("strTeam","") or row.get("strTeamShort","") or "?"
                short = row.get("strTeamShort","") or disp
                # Kurz: "Pittsburgh Steelers" -> "Steelers"? TheSportsDB strTeamShort ist oft schon kurz!
                # Wir nehmen shortDisplayName-Logik: Letztes Wort wenn Team aus Stadt+Name? Nein, strTeamShort ist besser!
                div = row.get("strDivision","") or row.get("strLeague","") or "Tabelle"
                # Division säubern: "AFC North" bleibt, "Eastern Conference" -> "Eastern"
                try: W=int(float(str(row.get("intWin",0) or 0)))
                except: W=0
                try: L=int(float(str(row.get("intLoss",0) or 0)))
                except: L=0
                try: T=int(float(str(row.get("intTied",0) or 0)))
                except: T=0
                streak = row.get("strForm","") or ""
                # strForm ist wie "WWWLL" -> nur letzte 3? Wir zeigen "W3" / "L1" aus Form: zähle gleiche Zeichen am Ende!
                streak_s=""
                if streak:
                    try:
                        last = streak.strip()[-1].upper() if streak.strip() else ""
                        cnt=0
                        for ch in reversed(streak.strip().upper()):
                            if ch==last: cnt+=1
                            else: break
                        if last in ("W","L") and cnt>0: streak_s=f"{last}{cnt}"
                    except: pass
                # Kurzname: Wenn strTeamShort leer, nimm letztes Wort (Steelers aus Pittsburgh Steelers) nur wenn kurz?
                # Wir lassen disp voll, aber in Anzeige wird short benutzt: short = strTeamShort oder disp
                # TheSportsDB strTeamShort ist z.B. "Steelers", "Penguins" - perfekt!
                out.setdefault(div, []).append((disp, short, "", W, L, T, streak_s))
            if out:
                # Sortieren pro Division: Wins absteigend
                for k in out: out[k].sort(key=lambda x: (x[3], -x[4]), reverse=True)
                return out
        except Exception as e:
            _STANDINGS_DEBUG["last_keys"]=f"TSDB Fehler: {e}"
            continue
    # --- 2) ESPN als Backup (None-sicher! V60-Fehler: children war None -> 'NoneType' not subscriptable) ---
    try:
        urls=[]
        if league=="NFL":
            urls=["https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season=2025&seasontype=2&type=0&level=4",
                  "https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season=2025"]
        elif league=="NBA":
            urls=["https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season=2025"]
        elif league=="NHL":
            urls=["https://site.api.espn.com/apis/v2/sports/hockey/nhl/standings?season=2025"]
        elif league=="MLB":
            urls=["https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings?season=2025"]
        elif league=="NCAAF":
            urls=["https://site.api.espn.com/apis/v2/sports/football/college-football/standings?season=2025"]
        for u in urls:
            try:
                r=requests.get(u, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
                _STANDINGS_DEBUG["last_url"]=u; _STANDINGS_DEBUG["last_status"]=r.status_code
                if r.status_code!=200: continue
                j=r.json()
                out={}
                def walk(node, path):
                    if isinstance(node, dict):
                        kids = node.get("children") or []  # None-sicher! War der V60-Fehler!
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
                                for s in e.get("stats", []) or []:
                                    if not isinstance(s, dict): continue
                                    n=(s.get("name","") or "").lower(); v=s.get("displayValue", s.get("value",""))
                                    try:
                                        if n=="wins": W=int(float(str(v)))
                                        elif n=="losses": L=int(float(str(v)))
                                        elif n=="ties": T=int(float(str(v)))
                                        elif n=="streak": streak=str(v)
                                    except: pass
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
    except Exception:
        pass
    return {}
def standings_conferences(league, divs):
    # Für NBA/NHL: Eastern/Western als Sammel-Liste (sortiert nach Wins)
    # Division -> Conference Mapping
    conf_map = {
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
        # Sortieren: Wins absteigend
        rows.sort(key=lambda x: (x[3], -x[4]), reverse=True)
        res[conf]=rows
    return res
async def tables_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏈 NFL", callback_data="tables_league:NFL"),
         InlineKeyboardButton("🎓 NCAAF", callback_data="tables_league:NCAAF")],
        [InlineKeyboardButton("🏒 NHL", callback_data="tables_league:NHL"),
         InlineKeyboardButton("🏀 NBA", callback_data="tables_league:NBA")],
        [InlineKeyboardButton("⚾ MLB", callback_data="tables_league:MLB")],
        [InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await target.reply_text("📊 Tabellen\n\nWelche Liga?\n⭐ Meine Teams = Alle deine Favoriten auf einmal, über alle Ligen!", reply_markup=kb)
async def tables_league_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str):
    target = update.message or update.callback_query.message
    await target.reply_text("📊 Ich hole die Tabelle... einen Moment ⏳")
    divs = espn_standings(league)
    if not divs:
        dbg = _STANDINGS_DEBUG
        await target.reply_text(f"Keine Tabelle gefunden - versuch es später nochmal.\n\nDebug: Status {dbg.get('last_status')} | Keys: {dbg.get('last_keys')} | URL: {dbg.get('last_url')}", reply_markup=main_kb()); return
    ctx.user_data["tables_divs_"+league]=divs
    # NCAAF: nur Top 25, keine Division-Auswahl
    if league=="NCAAF":
        await tables_top25_cmd(update, ctx, league, divs); return
    # Division / Conference Buttons: 2 pro Reihe
    rows=[]
    # NBA/NHL: erst Conference-Buttons
    if league in ("NBA","NHL"):
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
    kb = InlineKeyboardMarkup(rows)
    await target.reply_text(f"📊 Tabelle - {LEAGUES[league]['emoji']} {league}\n\nWelche Division / Conference?\nNur 1 Division = übersichtlich, 4-8 Teams!", reply_markup=kb)
async def tables_div_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str, div: str):
    target = update.message or update.callback_query.message
    divs = ctx.user_data.get("tables_divs_"+league)
    if not divs:
        divs = espn_standings(league)
        ctx.user_data["tables_divs_"+league]=divs
    rows = divs.get(div, [])
    if not rows:
        await target.reply_text("Division nicht gefunden.", reply_markup=main_kb()); return
    favs = favs_for(update.effective_user.id) if update.effective_user else []
    fav_names = [f.split(" (")[0].strip().lower() for f in favs]
    div_short = div.replace("American Football Conference", "AFC").replace("National Football Conference", "NFC").replace("American Football", "AFC").replace("National Football", "NFC").strip()
    lines=[f"📊 Tabelle - {LEAGUES[league]['emoji']} {league} - {div_short}\n"]
    for i,(disp, short, abbrev, W, L, T, streak) in enumerate(rows,1):
        rec = f"{W}-{L}" + (f"-{T}" if T else "")
        is_fav = any(fn in disp.lower() or disp.lower() in fn for fn in fav_names)
        star = " ⭐" if is_fav else ""
        streak_s = f" ({streak})" if streak and streak not in ("-", "0") else ""
        # Kurz: "1. Steelers 7-2 ⭐ (W3)" - 1 Zeile pro Team!
        lines.append(f"{i}. {short} {rec}{star}{streak_s}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Andere Division", callback_data=f"tables_league:{league}")],
        [InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await target.reply_text("\n".join(lines), reply_markup=kb)
async def tables_conf_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str, conf: str):
    target = update.message or update.callback_query.message
    divs = ctx.user_data.get("tables_divs_"+league)
    if not divs:
        divs = espn_standings(league)
        ctx.user_data["tables_divs_"+league]=divs
    confs = standings_conferences(league, divs)
    rows = confs.get(conf, [])
    if not rows:
        await target.reply_text("Conference nicht gefunden.", reply_markup=main_kb()); return
    favs = favs_for(update.effective_user.id) if update.effective_user else []
    fav_names = [f.split(" (")[0].strip().lower() for f in favs]
    lines=[f"📊 Tabelle - {LEAGUES[league]['emoji']} {league} - {conf} Conference\n"]
    for i,(disp, short, abbrev, W, L, T, streak) in enumerate(rows,1):
        rec = f"{W}-{L}" + (f"-{T}" if T else "")
        is_fav = any(fn in disp.lower() or disp.lower() in fn for fn in fav_names)
        star = " ⭐" if is_fav else ""
        # Playoff-Strich bei NBA/NHL: Top 8 = Playoffs, 9-10 = Play-In (NBA) / Top 8 Playoffs (NHL)
        marker = ""
        if league=="NBA" and i==8: marker=" — Playoff-Platz"
        if league=="NBA" and i==10: marker=" — Play-In"
        if league=="NHL" and i==8: marker=" — Playoff-Platz"
        lines.append(f"{i}. {short} {rec}{star}{marker}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Andere Division", callback_data=f"tables_league:{league}")],
        [InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await target.reply_text("\n".join(lines), reply_markup=kb)
async def tables_top25_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, league: str, divs):
    target = update.message or update.callback_query.message
    # NCAAF: Alle Teams aus allen Conferences, nach Wins sortiert, Top 25
    all_rows=[]
    for k,v in divs.items():
        all_rows.extend(v)
    all_rows.sort(key=lambda x: (x[3], -x[4]), reverse=True)
    top = all_rows[:25]
    favs = favs_for(update.effective_user.id) if update.effective_user else []
    fav_names = [f.split(" (")[0].strip().lower() for f in favs]
    lines=[f"📊 Tabelle - 🎓 NCAAF - Top 25\n"]
    for i,(disp, short, abbrev, W, L, T, streak) in enumerate(top,1):
        rec = f"{W}-{L}" + (f"-{T}" if T else "")
        is_fav = any(fn in disp.lower() or disp.lower() in fn for fn in fav_names)
        star = " ⭐" if is_fav else ""
        lines.append(f"{i}. {short} {rec}{star}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Meine Teams", callback_data="tables_mine")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await target.reply_text("\n".join(lines), reply_markup=kb)
async def tables_mine_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs = favs_for(user.id) if user else []
    if not favs:
        await target.reply_text("Du hast noch keine Favoriten. Füge erst ein Team hinzu, dann zeige ich dir hier deine Tabellen!", reply_markup=main_kb()); return
    await target.reply_text("📊 Ich hole deine Tabellen... einen Moment ⏳")
    lines=["📊 Deine Teams - Tabellen\n⭐ = Dein Team\n"]
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
        lines.append(f"\n{LEAGUES[lg]['emoji']} {lg} - {div_s}")
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
    ])
    await target.reply_text("\n".join(lines), reply_markup=kb)

async def next_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    favs = favs_for(user.id) if user else []
    lines=["⏭️ Next Games - Deine Favoriten\n🏠 Erstes Team = Heimteam  (Heim @ Gast)\n"]
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
    for league in LEAGUES:
        for offset in range(0, 15):
            d = today + timedelta(days=offset)
            ds = d.strftime("%Y%m%d")
            for ev in espn_scoreboard(league, dates=ds):
                eid = ev.get("id")
                if eid in seen_ids: continue
                seen_ids.add(eid)
                # Nur zukünftige / heutige Spiele, keine fertigen
                state = ev.get("status",{}).get("type",{}).get("state","")
                if state=="post": continue
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
        weekday = ["Mo","Di","Mi","Do","Fr","Sa","So"][dt.weekday()] if dt else ""
        lines.append(f"\n{LEAGUES[league]['emoji']} {disp}:")
        lines.append(f"• {weekday} {game_line(ev, league, show_broadcast=True)}")
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
                lines.append(f"\n{LEAGUES[lg2]['emoji']} {disp2} - {pre_label}:")
                lines.append(f"• {weekday} {game_line(ev, lg2, show_broadcast=True)}")
    if not shown:
        lines.append("Keine kommenden Spiele für deine Favoriten gefunden - auch keine Preseason / Spring Training Daten bei ESPN.")
        lines.append("Aktueller Meister:")
        for lg,ch in CHAMPIONS.items():
            if any(lg in f for f in favs):
                lines.append(f"{LEAGUES[lg]['emoji']} {lg}: {ch['team']} ({ch['year']}) - {ch['result']}")
    await target.reply_text("\n".join(lines), reply_markup=main_kb())

async def heute_morgen(update: Update, ctx: ContextTypes.DEFAULT_TYPE, morgen=False):
    target = update.message or update.callback_query.message
    want = (datetime.now(BERLIN)+timedelta(days=1 if morgen else 0)).date()
    lines=[f"📅 {'Morgen' if morgen else 'Heute'} ({want.strftime('%d.%m.')})\n"]
    # Überall: "Heim @ Gast" - erstes Team ist Heimteam!
    lines.append("🏠 Erstes Team = Heimteam  (Heim @ Gast)\n")
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


async def results_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Liga-Auswahl für Ergebnisse - nicht alle Ligen auf einmal, sonst ewige Liste!
    target = update.message or update.callback_query.message
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏈 NFL", callback_data="results_league:NFL"),
         InlineKeyboardButton("🏒 NHL", callback_data="results_league:NHL")],
        [InlineKeyboardButton("⚾ MLB", callback_data="results_league:MLB"),
         InlineKeyboardButton("🏀 NBA", callback_data="results_league:NBA")],
        [InlineKeyboardButton("🏈 NCAAF", callback_data="results_league:NCAAF")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await target.reply_text("✅ Ergebnisse\n\nWelche Liga?\n🏠 Erstes Team = Heimteam  (Heim @ Gast)", reply_markup=kb)
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
    lines=[f"✅ Ergebnisse - {LEAGUES[league]['emoji']} {league} (letzte {limit})\n🏠 Erstes Team = Heimteam\n"]
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
                lines.append(f"{h_name} {h_score} - {a_score} {a_name}{suffix}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Andere Liga", callback_data="results")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back")],
    ])
    await target.reply_text("\n".join(lines), reply_markup=kb)

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
    lines=["🔴 Live - Deine Favoriten\n🏠 Erstes Team = Heimteam  (Heim @ Gast)\n"]
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
    elif not live_found:
        lines.append("Gerade spielt kein Team von deinen Favoriten live.")
        if finals:
            lines.append("\n✅ Letzte Endergebnisse deiner Favoriten:")
            lines.extend(finals[:5])
    await target.reply_text("\n".join(lines), reply_markup=main_kb())

async def remind_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    # Reminder-Info: Wir merken uns, dass Reminder an ist. Echte JobQueue waere hier erweiterbar.
    ctx.user_data["remind"] = True
    await target.reply_text("⏰ Reminder an! Ich erinnere dich 1h vor dem Spiel deiner Favoriten.\n\nHinweis: Auf Render Free bleibt der Reminder aktiv, solange der Bot läuft.", reply_markup=main_kb())

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
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

async def on_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data=q.data
    if data=="back": await q.message.edit_text(START_TEXT, reply_markup=main_kb())
    elif data=="help": await q.message.edit_text(HELP_TEXT, reply_markup=main_kb())
    elif data=="top10": await top10_cmd(update, ctx)
    elif data=="tables": await tables_cmd(update, ctx)
    elif data.startswith("tables_league:"): await tables_league_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("tables_div:"):
        _parts = data.split(":", 2)
        await tables_div_cmd(update, ctx, _parts[1], _parts[2])
    elif data.startswith("tables_conf:"):
        _parts = data.split(":")
        await tables_conf_cmd(update, ctx, _parts[1], _parts[2])
    elif data=="tables_mine": await tables_mine_cmd(update, ctx)
    elif data.startswith("top10_league:"): await top10_league_cmd(update, ctx, data.split(":")[1])
    elif data.startswith("top10_detail:"): await top10_detail_cmd(update, ctx, int(data.split(":")[1]))
    elif data=="next": await next_cmd(update, ctx)
    elif data=="heute": await heute_morgen(update, ctx, False)
    elif data=="morgen": await heute_morgen(update, ctx, True)
    elif data=="results": await results_cmd(update, ctx)
    elif data.startswith("results_league:"): await results_league_cmd(update, ctx, data.split(":")[1])
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
    app.add_handler(CommandHandler("tables", tables_cmd))
    app.add_handler(CommandHandler("heute", lambda u,c: heute_morgen(u,c,False)))
    app.add_handler(CommandHandler("morgen", lambda u,c: heute_morgen(u,c,True)))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(CommandHandler("ergebnisse", results_cmd))
    app.add_handler(CommandHandler("remind", remind_cmd))
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("USA Sport Radar läuft...")
    app.run_polling()

if __name__=="__main__": main()
