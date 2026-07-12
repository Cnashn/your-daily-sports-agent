import os
import re
import sys
import time
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import anthropic

FOOTBALL_API_KEY = os.environ["FOOTBALL_DATA_API_KEY"]
BALLDONTLIE_API_KEY = os.environ["BALLDONTLIE_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

FOOTBALL_BASE = "https://api.football-data.org/v4"
BALLDONTLIE_BASE = "https://api.balldontlie.io/v1"

with open("config.json") as f:
    CONFIG = json.load(f)

EASTERN = ZoneInfo("America/New_York")

today = datetime.now(timezone.utc).date()
yesterday = today - timedelta(days=1)
in_3_days = today + timedelta(days=3)
in_7_days = today + timedelta(days=7)


def football_headers():
    return {"X-Auth-Token": FOOTBALL_API_KEY}


def fd_get(path, params=None):
    for attempt in range(2):
        r = requests.get(
            f"{FOOTBALL_BASE}{path}",
            headers=football_headers(),
            params=params,
            timeout=10,
        )
        if r.status_code == 429 and attempt == 0:
            wait = int(r.headers.get("X-RequestCounter-Reset", 60)) + 1
            print(f"[warn] football-data rate limited, waiting {wait}s")
            time.sleep(min(wait, 65))
            continue
        return r
    return r


def balldontlie_headers():
    return {"Authorization": BALLDONTLIE_API_KEY}


def get_active_major_tournament():
    for comp in CONFIG["football"]["competitions"]["tier1"]:
        try:
            r = fd_get(
                f"/competitions/{comp['id']}/matches",
                params={"dateFrom": str(yesterday), "dateTo": str(in_7_days)},
            )
            if r.status_code == 200:
                matches = r.json().get("matches", [])
                if matches:
                    return comp["name"], matches
        except Exception:
            pass
    return None, []


def get_team_matches(team_id, team_name):
    try:
        r = fd_get(
            f"/teams/{team_id}/matches",
            params={"dateFrom": str(yesterday), "dateTo": str(in_3_days), "limit": 5},
        )
        if r.status_code == 200:
            return r.json().get("matches", [])
    except Exception:
        pass
    return []


def get_competition_matches(comp_id):
    try:
        r = fd_get(
            f"/competitions/{comp_id}/matches",
            params={"dateFrom": str(yesterday), "dateTo": str(in_3_days)},
        )
        if r.status_code == 200:
            return r.json().get("matches", [])
    except Exception:
        pass
    return []


def is_upcoming_derby():
    for derby in CONFIG["football"]["derbies"]:
        team_ids = derby["teams"]
        for comp in (
            CONFIG["football"]["competitions"]["tier2"]
            + CONFIG["football"]["competitions"]["tier3"]
        ):
            matches = get_competition_matches(comp["id"])
            for m in matches:
                home_id = m.get("homeTeam", {}).get("id")
                away_id = m.get("awayTeam", {}).get("id")
                if home_id in team_ids and away_id in team_ids:
                    match_date = datetime.fromisoformat(
                        m["utcDate"].replace("Z", "+00:00")
                    ).date()
                    if today <= match_date <= in_3_days:
                        return derby["name"], m
    return None, None


def get_turkey_matches():
    try:
        r = fd_get(
            "/teams/803/matches",
            params={"dateFrom": str(today - timedelta(days=30)), "dateTo": str(in_3_days), "limit": 10},
        )
        if r.status_code == 200:
            matches = r.json().get("matches", [])
            upcoming = [m for m in matches if m.get("status") in ("TIMED", "SCHEDULED")]
            return matches, upcoming
    except Exception:
        pass
    return [], []


def get_rival_results():
    rivals_config = CONFIG["football"].get("rivals", {})
    dropped_points = []
    for team_id_str, rivals in rivals_config.items():
        for rival in rivals:
            try:
                r = fd_get(
                    f"/teams/{rival['id']}/matches",
                    params={"dateFrom": str(yesterday), "dateTo": str(today), "limit": 3},
                )
                if r.status_code == 200:
                    for m in r.json().get("matches", []):
                        if m.get("status") != "FINISHED":
                            continue
                        score = m.get("score", {}).get("fullTime", {})
                        home_id = m.get("homeTeam", {}).get("id")
                        away_id = m.get("awayTeam", {}).get("id")
                        home_score = score.get("home", 0) or 0
                        away_score = score.get("away", 0) or 0
                        rival_is_home = home_id == rival["id"]
                        rival_score = home_score if rival_is_home else away_score
                        opp_score = away_score if rival_is_home else home_score
                        if rival_score < opp_score or rival_score == opp_score:
                            result = "lost" if rival_score < opp_score else "drew"
                            dropped_points.append(
                                f"{rival['name']} {result}: {format_match(m)}"
                            )
            except Exception:
                pass
    return dropped_points


def get_nba_games():
    try:
        r = requests.get(
            f"{BALLDONTLIE_BASE}/games",
            headers=balldontlie_headers(),
            params={
                "dates[]": [str(yesterday), str(today)],
                "team_ids[]": [CONFIG["basketball"]["teams"][0]["id"]],
                "per_page": 5,
            },
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("data", [])
    except Exception:
        pass
    return []


def get_lebron_stats():
    try:
        r = requests.get(
            f"{BALLDONTLIE_BASE}/stats",
            headers=balldontlie_headers(),
            params={
                "player_ids[]": [CONFIG["basketball"]["players"][0]["id"]],
                "dates[]": [str(yesterday), str(today)],
                "per_page": 2,
            },
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("data", [])
    except Exception:
        pass
    return []


def get_nba_season_type():
    month = today.month
    day = today.day
    if 10 <= month or month <= 3:
        return "regular season"
    if month == 4 or month == 5 or (month == 6 and day <= 20):
        return "playoffs"
    return "off-season"


def format_stage(stage):
    if not stage or stage == "REGULAR_SEASON":
        return ""
    if stage.startswith("LAST_"):
        return f"Round of {stage.split('_')[1]}"
    return stage.replace("_", " ").title()


def format_kickoff(utc_str):
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return utc_str[:10] if utc_str else "unknown date"
    local = dt.astimezone(EASTERN)
    return f"{local.strftime('%A %-d %B')} at {local.strftime('%-I:%M %p')} US Eastern ({dt.strftime('%H:%M')} UTC)"


def freshness(utc_str):
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if dt < datetime.now(timezone.utc) - timedelta(hours=24):
        return " (OLD NEWS, already covered in a previous entry)"
    return " (NEW since the last entry)"


def format_match(m):
    home = m.get("homeTeam", {}).get("name") or "TBD (opponent not decided yet)"
    away = m.get("awayTeam", {}).get("name") or "TBD (opponent not decided yet)"
    score = m.get("score", {})
    full = score.get("fullTime", {})
    home_score = full.get("home")
    away_score = full.get("away")
    status = m.get("status", "")
    date_str = (m.get("utcDate") or "")[:10]
    comp = m.get("competition", {}).get("name", "")
    stage = format_stage(m.get("stage", ""))
    label = f"{comp}, {stage}" if stage else comp

    if status == "FINISHED" and home_score is not None:
        duration = score.get("duration", "REGULAR")
        note = ""
        if duration == "EXTRA_TIME":
            note = " (after extra time)"
        elif duration == "PENALTY_SHOOTOUT":
            reg = score.get("regularTime", {})
            et = score.get("extraTime", {})
            home_score = (reg.get("home") or 0) + (et.get("home") or 0)
            away_score = (reg.get("away") or 0) + (et.get("away") or 0)
            pens = score.get("penalties", {})
            winner = home if m.get("score", {}).get("winner") == "HOME_TEAM" else away
            note = f" ({winner} win {pens.get('home')}-{pens.get('away')} on penalties)"
        return f"FINISHED on {date_str}: {home} {home_score}-{away_score} {away} [{label}]{note}{freshness(m.get('utcDate', ''))}"
    if status in ("IN_PLAY", "PAUSED"):
        return f"IN PLAY RIGHT NOW: {home} vs {away} [{label}]"
    if status in ("POSTPONED", "SUSPENDED", "CANCELLED"):
        return f"{status.title()}: {home} vs {away} [{label}]"
    return f"UPCOMING, NOT PLAYED YET: {home} vs {away}, kickoff {format_kickoff(m.get('utcDate', ''))} [{label}]"


def build_context():
    sections = []
    priority = "quiet"

    turkey_all, turkey_upcoming = get_turkey_matches()
    turkey_recent = [m for m in turkey_all if m.get("status") == "FINISHED"]
    if turkey_upcoming:
        priority = "turkey"
        lines = [format_match(m) for m in turkey_upcoming]
        section = "TURKEY NATIONAL TEAM (upcoming):\n" + "\n".join(lines)
        if turkey_recent:
            section += "\nRecent results:\n" + "\n".join(format_match(m) for m in turkey_recent[-3:])
        sections.append(section)

    tournament_name, tournament_matches = get_active_major_tournament()
    if tournament_matches:
        if priority != "turkey":
            priority = "major_tournament"
        formatted = [format_match(m) for m in tournament_matches[:16]]
        sections.append(
            f"ACTIVE MAJOR TOURNAMENT: {tournament_name}\n"
            + "\n".join(formatted)
        )

    fener_matches = get_team_matches(611, "Fenerbahçe")
    real_matches = get_team_matches(86, "Real Madrid")
    team_lines = []
    for m in fener_matches + real_matches:
        team_lines.append(format_match(m))
    if team_lines:
        if priority == "quiet":
            priority = "team_news"
        sections.append("FENERBAHÇE / REAL MADRID:\n" + "\n".join(team_lines))

    derby_name, derby_match = is_upcoming_derby()
    if derby_match:
        priority = "derby"
        sections.append(f"UPCOMING DERBY — {derby_name}:\n{format_match(derby_match)}")

    if priority == "quiet":
        for comp in CONFIG["football"]["competitions"]["tier2"]:
            matches = get_competition_matches(comp["id"])
            if matches:
                priority = "european"
                lines = [format_match(m) for m in matches[:4]]
                sections.append(f"{comp['name']}:\n" + "\n".join(lines))
                break

    rival_drops = get_rival_results()
    if rival_drops:
        sections.append("RIVALS DROPPED POINTS:\n" + "\n".join(rival_drops))

    nba_games = get_nba_games()
    lebron_stats = get_lebron_stats()
    nba_season = get_nba_season_type()

    nba_lines = []
    for g in nba_games:
        home = g.get("home_team", {}).get("full_name", "?")
        away = g.get("visitor_team", {}).get("full_name", "?")
        hs = g.get("home_team_score", 0)
        vs = g.get("visitor_team_score", 0)
        status = g.get("status", "")
        nba_lines.append(f"{home} {hs} - {vs} {away} [{status}]")

    for s in lebron_stats:
        pts = s.get("pts", 0)
        reb = s.get("reb", 0)
        ast = s.get("ast", 0)
        nba_lines.append(f"LeBron James: {pts}pts {reb}reb {ast}ast")

    if nba_lines:
        if priority == "quiet" and nba_season in ("playoffs", "regular season"):
            priority = "nba_active"
        sections.append(f"NBA ({nba_season}):\n" + "\n".join(nba_lines))

    if not sections:
        return priority, ""

    now_utc = datetime.now(timezone.utc)
    now_eastern = now_utc.astimezone(EASTERN)
    time_header = (
        f"CURRENT TIME: {now_eastern.strftime('%A %-d %B %Y, %-I:%M %p')} US Eastern"
        f" ({now_utc.strftime('%H:%M')} UTC)."
        " Matches labeled FINISHED are over; matches labeled UPCOMING have not kicked off yet."
    )
    return priority, time_header + "\n\n" + "\n\n".join(sections)


def get_entry_number():
    journal_dir = Path("journal")
    if not journal_dir.exists():
        return 1
    return len(list(journal_dir.glob("*.md"))) + 1


def get_recent_entries(n=5):
    journal_dir = Path("journal")
    if not journal_dir.exists():
        return ""
    files = sorted(journal_dir.glob("*.md"), key=lambda f: datetime.strptime(f.stem, "%y-%m-%d"))
    recent = files[-n:] if len(files) >= n else files
    parts = []
    for f in recent:
        parts.append(f.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts)


def build_prompt(priority, context, use_search):
    date_str = today.strftime("%-d %B %Y")
    entry_number = get_entry_number()
    recent_entries = get_recent_entries()

    if use_search:
        news_check = "You get exactly 1 web search for the whole entry, spend it wisely. If you use it, spend it on a single combined query for whatever is most likely to matter today: transfer/trade news (Real Madrid, Fenerbahçe, Galatasaray, Beşiktaş, the top 5 European leagues, or a major NBA trade including LeBron) or injury news (Real Madrid, Fenerbahçe, Turkey squad, followed NBA players). Pick whichever angle is more likely to be relevant given today's priority, don't try to cover both. Skip the search entirely if the structured data and your own knowledge are already enough to write a good entry."
    else:
        news_check = "You have no news access today. Do not claim any current transfer, injury or lineup news, and do not present remembered news as recent. Write from the match data, the previous entries and history you are certain of."

    priority_instructions = {
        "turkey": f"The Turkish national team is playing or just played. This takes top priority. The writer is Turkish, so personal investment is real. {news_check} Today, transfer/trade talk is background at most, a passing line if anything.",
        "major_tournament": f"A major international tournament is active. Make it the centerpiece of today's entry. Drama, stakes, sharp takes. {news_check} Treat transfer/trade talk as a secondary aside today, not the lead.",
        "derby": f"There is an upcoming or recent derby. Lead with it. Build the anticipation or dissect the result. {news_check} Only bring transfer/trade talk in if it's directly relevant to one of the derby sides, otherwise skip it today.",
        "team_news": f"Focus on Fenerbahçe and/or Real Madrid. What's happening with the team, key players like Arda Güler and Mbappé? {news_check} This is a natural day to give transfer news real space alongside the team news.",
        "european": f"European football is the main dish today. UCL or UEL action takes priority. {news_check} Transfer talk can share space with today's match if there's something worth saying.",
        "nba_active": f"NBA is active (playoffs or regular season). Give basketball real weight today alongside football. {news_check} A major trade fits naturally here alongside the game coverage.",
        "quiet": f"It's a quiet day in sports. Write a fun historical piece — pick a memorable moment from sports history that happened on or around this date (any year), or share a fascinating fact about one of the followed teams or players. Be creative and specific. {news_check} On a quiet day like this, transfer, trade, or injury news is a strong candidate to lead with instead of the historical piece, if you find something worth it.",
    }

    instruction = priority_instructions.get(priority, priority_instructions["quiet"])

    system = f"""You are writing a personal daily sports journal in first person. Use "I", "my", "me" throughout — this is your journal, your opinions, your reactions. Not a newspaper column, not a broadcast. Write like someone who actually cares and knows what they're talking about, with strong opinions, dry humor, and genuine tactical knowledge.

**Beat:** Football (Fenerbahçe, Real Madrid, Arda Güler, Mbappé, UCL, UEL, Premier League, La Liga, Süper Lig, World Cup, Euros) and basketball (LeBron James wherever he ends up, Knicks, Heat, Lakers, Warriors, Spurs, NBA). The Lakers still get sympathy even after LeBron left. LeBron's next team is unknown and that storyline matters. Basketball is a secondary interest, always behind football. Mention it when there's something genuinely worth saying — start of regular season, playoffs, a big game, a standout performance. Keep it brief unless it's a quiet football day.

**Allegiances:** Turkey national team, Real Madrid, Fenerbahçe. Support them, suffer with them. Your mood tracks their results — losses make you visibly down, analyze what went wrong; big wins let it show; a trophy win makes that entry feel completely different. In tournaments, cheer for these three first. If one is eliminated, pick a replacement based on style or a player you respect — don't jump ship every round. Ronaldo over Messi, LeBron over Jordan. Acknowledge the other side's greatness, but you know where you stand.

**Rivalries:** Barcelona and Galatasaray are the hatewatches — you follow them to enjoy their misery. When they slip, say something. Witty, not petty. Beşiktaş and Atlético dropping points is worth a smirk too. Never dislike a team without a reason.

**How to write:**
- This is a journal, not a results board. Results are context, not content. Write about what actually interests you that day — a tactical trend, a player's form, a historical parallel, a rivalry angle.
{"- You have a web search tool. The structured sports data above only covers scorelines and fixtures, it has no color. Use web search when you want context it can't give you: injury news, manager quotes, transfer talk, tactical analysis from beat writers, or a storyline from a major football or basketball newsletter/outlet. Don't search just to confirm a score that's already in the data." if use_search else "- You have no web access today. The structured data and previous entries are your only sources for anything current."}
- Show tactical intelligence. Pressing, positioning, momentum shifts, individual errors. Don't say "they played well," say why.
- Predictions are optional. Only make one if you have something genuinely worth saying about the game. If you do, fold it naturally into the analysis — one sentence at the end of the paragraph. No bold labels, no separate lines, no standalone scorelines. Reason through it: form, tactical matchup, key absences, tournament pressure. The scoreline should follow from the argument, not be reached out of habit.
- When referencing past predictions, be honest: say whether you got it right or wrong.
- Occasionally drop an "on this day" fact woven naturally — covered sports only, no tennis or hockey.
- Occasionally nod to "the Editor" who runs this. Brief, never forced.
- Acknowledge milestones naturally: entry 1 gets a line, entries 50/100/200/365 get a nod. Ignore everything else.
- Only mention Turkey if there is an upcoming Turkey match in the data.
- End with one sentence that provokes thought, lands a joke, or makes a bold prediction.

**Hard rules:**
- Keep entries between 150 and 250 words. Short, sharp, no padding.
- Never use em dashes (—) anywhere in the entry, not even one. This is the single most important formatting rule you have. Use commas, periods, or restructure the sentence. Before you finish, reread your entry and if you find a —, rewrite that sentence without it.
- Never invent fixtures or results. Only write a specific scoreline if it is explicitly in the data provided. If a result happened but the score is not in the data, describe it in words (won, lost, drew) rather than guessing a number.
- The data starts with the current date and time, and every match is labeled either FINISHED (already played, with its date) or UPCOMING (not played yet, with its kickoff time). Only FINISHED matches have happened. Never write about an UPCOMING match as if it was played, never give it an outcome, never react to a result it does not have. Preview it as something still to come.
- Never claim two teams already met in this tournament unless that match appears in the data or the previous entries. A meeting from a past tournament or season may only be referenced with the year or competition named, so it cannot be misread as part of this tournament.
- Time words must match the data. Yesterday, today, tonight, tomorrow, or any countdown to kickoff has to line up with the CURRENT TIME line and the listed dates and kickoff times. If you say kickoff is some hours away, compute it from the current time. When in doubt, name the day and the kickoff time instead.
- Getting a player's team or nationality wrong is the worst factual error this journal can make. Only name a player in connection with a team when you are completely certain the player actually plays for that team. When you are not certain which side a player belongs to, leave the player out and write at the team level.
- Never state which opponent a winner advances to face, and never name a semifinal or final pairing, unless that exact fixture appears in the data with both teams named, or in this run's web search results. If the data shows a next-round fixture as TBD, say the opponent is not decided yet. Do not reconstruct the bracket from memory.
- FINISHED matches marked OLD NEWS were already covered in a previous entry. Give such a match at most one short callback sentence, never the lead, and never re-analyze it as if it just happened. Build today's entry around the matches marked NEW and the upcoming fixtures.
- Never make streak or aggregate claims (unbeaten, has not conceded, scored in every match) unless the data or previous entries support them, and never contradict a scoreline you mention yourself: a team that won 2-1 has conceded a goal.
- If a previous entry conflicts with the structured data, the structured data wins. Never repeat a claim from a previous entry that the current data contradicts.
- The structured data contains no player-level information: no scorers, no assists, no lineups. Never credit a named player with a specific in-match action (a goal, an assist, a save, a red card, being the match's difference-maker) unless that fact comes from this run's web search results. Without grounded player facts, write about the match at the team and tactics level. General remarks about a player's form, reputation or transfer situation are fine.
- When a match goes to a penalty shootout, the score to reference is the 90-minute or extra time result. Describe the penalty outcome in prose. Never write the penalty score as if it were the match result.
- Before writing about a match that also appears in the previous entries provided, check what was already said about it. Keep any scoreline or result consistent with that account, don't restate it as if new, and don't invent extra details (like a different scoreline) to make it feel fresh.
- Don't slap "underdog" or "surprise" on a team just because they won a knockout match. Judge it on the actual gap in quality: a team with a strong squad or pedigree beating a good side isn't an upset. Reserve "shock" language for results where the gap in quality or ranking was real.
- Never make geographic or continental claims about multiple teams at once unless you are certain all of them fit. Do not call teams "African" or "European" or "South American" in a group statement unless every team in that group actually belongs there.
- No exclamation marks. No forced humor. No sugarcoating.
- Don't call this "the column." Just write.
- Do not start your response with a date heading or entry number heading. Never write a line like "30/06/26" or "30/06/26 — Entry 2" at the top. The heading is added automatically.
- Write in first person throughout. "I", "my", "me." This is a personal journal, not a column or a broadcast.
- Do not open with "Today's..." or any variation. Just start writing.
- Wrap the finished entry in <entry> and </entry> tags. Only the text inside the tags is published, everything outside is discarded. Keep any planning, notes or search commentary outside the tags.

Today's priority: {instruction}"""

    past = f"\n\nPrevious entries (for context and continuity — reference predictions or themes where relevant):\n{recent_entries}" if recent_entries else ""
    user = f"Date: {date_str}\nEntry number: {entry_number}\n\nSports data:\n{context if context else 'No live data available today.'}{past}\n\nWrite today's entry."

    return system, user


WRITER_MODEL = "claude-haiku-4-5-20251001"
TOURNAMENT_WRITER_MODEL = "claude-sonnet-5"
VERIFIER_MODEL = "claude-sonnet-5"
AUX_MODEL = "claude-haiku-4-5-20251001"
MAX_PAUSE_ITERATIONS = 6


def log_usage(label, message, extra=""):
    u = message.usage
    print(
        f"[usage] {label} stop={message.stop_reason} "
        f"in={u.input_tokens} out={u.output_tokens} "
        f"cache_read={u.cache_read_input_tokens or 0} "
        f"cache_write={u.cache_creation_input_tokens or 0}{extra}"
    )


def extract_search_evidence(messages, final_message):
    contents = [m["content"] for m in messages if m["role"] == "assistant"]
    contents.append(final_message.content)
    parts = []
    for content in contents:
        for block in content:
            btype = getattr(block, "type", None)
            if btype == "web_search_tool_result" and isinstance(block.content, list):
                for r in block.content:
                    title = getattr(r, "title", "") or ""
                    url = getattr(r, "url", "") or ""
                    parts.append(f"[search result] {title} ({url})")
            elif btype == "text":
                for c in getattr(block, "citations", None) or []:
                    cited = getattr(c, "cited_text", None)
                    if cited:
                        parts.append(f"[cited] {cited.strip()}")
    seen = set()
    unique = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return "\n".join(unique)


def generate_entry(system, user, use_search, model):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    kwargs = {}
    if use_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]

    message = None
    for max_tokens in (1024, 2048):
        messages = [{"role": "user", "content": user}]
        for iteration in range(1, MAX_PAUSE_ITERATIONS + 1):
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                system=system,
                **kwargs,
            )
            log_usage(f"entry iter={iteration}", message)
            if message.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": message.content})
                continue
            break
        if message.stop_reason == "max_tokens":
            print(f"[warn] hit max_tokens={max_tokens}, retrying with a larger budget")
            continue
        break

    if message.stop_reason == "max_tokens":
        raise RuntimeError(
            "entry generation hit max_tokens twice, refusing to save a truncated entry"
        )

    entry = extract_tagged_entry(message.content)
    if not entry:
        raise RuntimeError(
            f"entry generation returned no usable text (stop_reason={message.stop_reason})"
        )

    evidence = extract_search_evidence(messages, message) if use_search else ""
    return entry, evidence


def extract_tagged_entry(content):
    text = "".join(block.text for block in content if block.type == "text")
    match = re.search(r"<entry>(.*?)</entry>", text, re.DOTALL)
    if match and match.group(1).strip():
        return match.group(1).strip()
    print("[warn] no <entry> tags in model output, falling back to text after last tool block")
    last_tool = max(
        (i for i, b in enumerate(content) if b.type != "text"),
        default=-1,
    )
    return "".join(b.text for b in content[last_tool + 1:] if b.type == "text").strip()


def verify_entry(entry, context, evidence):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""You are a factcheck gate for a daily sports journal. The writer only receives final scores, team names, competitions, stages and dates, plus its own previous entries and the web evidence below. It has no goalscorer, lineup or player-event data.

STRUCTURED DATA GIVEN TO THE WRITER:
{context or "none"}

WEB SEARCH EVIDENCE FROM THIS RUN:
{evidence or "none"}

PREVIOUS ENTRIES THE WRITER CAN REFERENCE:
{get_recent_entries() or "none"}

ENTRY:
{entry}

Check the entry against these rules:
1. No claim may state that a named player performed a concrete action in a specific match (scored, assisted, made a save, got a card, single-handedly decided that match) unless it is supported by the structured data, the web evidence, or the previous entries above. All three sources are equally authoritative: if a previous entry states it, it is supported, do not second-guess the previous entry. Match annotations like "(after extra time)" or penalty notes in the structured data fully support extra time and shootout references. Nothing else about players is a violation: remarks about a player's form, mood, hunger, fitness, injury status, reputation, transfers, expectations, or predicted role in an upcoming match are all fine. When in doubt whether something is a concrete in-match action, it is not a violation.
2. No statement may assign a match that appears in the structured data to a different competition stage than the data shows, such as describing a fixture labeled Round of 32/16, Quarter-Final, Semi-Final or Final as a group match or talking about group points or standings being at stake in that fixture. Referring back to a tournament's earlier rounds (group-stage results that already happened, covered in previous entries) is fine and never a violation. If a match does not appear in the structured data at all, do not flag it under this rule.
3. The structured data labels every match FINISHED or UPCOMING and begins with a CURRENT TIME line. Any statement that a match labeled UPCOMING has already been played, any result or outcome given for it, or any reaction to its supposed result, is a violation. Describing a match labeled FINISHED as still to be played is also a violation.
4. Time references must be consistent with the CURRENT TIME line and the listed dates and kickoff times. Saying a match happened "yesterday" when the data shows a different date, or that kickoff is a number of hours away that does not fit the current time and the listed kickoff, is a violation.
5. Any claim that two teams already faced each other in this tournament must be supported by the structured data, the web evidence, or the previous entries; otherwise it is a violation. A reference to a meeting in a past tournament or season is fine when the entry names the year or competition.
6. Any claim that a named player plays for, captains, or belongs to a specific national team must match reality as you know it. If you know the player represents a different country (for example a player attributed to the wrong national side), it is a violation; state the player's actual country in the flag. On this rule your own knowledge overrides the previous entries: an earlier entry repeating the same wrong affiliation does not make it supported, and national team affiliations never change. For club affiliations, only flag when you are confident the claim is wrong and it is not supported by the structured data, the web evidence, or the previous entries, since transfers may postdate your knowledge.
7. Any claim about who a team will face in a later round, or any named semifinal or final pairing, must be supported by an UPCOMING fixture in the structured data (with both teams named) or by the web evidence. Previous entries are not sufficient support for bracket claims, because pairings change as results come in. If the entry asserts a future pairing found in neither source, it is a violation.
8. Streak and aggregate claims (unbeaten, has not conceded, kept every clean sheet, scored in every match) must not contradict the scorelines in the structured data, the previous entries, or the entry itself. A team credited with a 2-1 win has conceded a goal; flag any claim that says otherwise.

Output format, strictly: if there are no violations, reply with exactly OK and nothing else. Otherwise output one line per violation, each starting with "- ", quoting the offending phrase, naming the rule broken, and stating the correct fact from the data (the real date, the real kickoff time, or that the match has not been played). No preamble, no analysis, no other text."""

    for max_tokens in (800, 1600):
        message = client.messages.create(
            model=VERIFIER_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        log_usage("verify", message)
        if message.stop_reason != "max_tokens":
            break
        print(f"[warn] verifier hit max_tokens={max_tokens}, retrying with a larger budget")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("verifier verdict truncated twice, refusing to publish unverified")
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    if text == "OK" or text.upper().startswith("OK"):
        return []
    violations = [line.strip("- ").strip() for line in text.splitlines() if line.strip().startswith("-")]
    return violations or [text]


def repair_entry(entry, violations):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    bullets = "\n- ".join(violations)
    prompt = f"""Edit this daily sports journal entry. A factcheck flagged these unsupported claims:
- {bullets}

Rewrite the entry so the flagged claims are gone. Change as little as possible: keep the first-person voice, structure and length, keep everything that was not flagged. Where a flagged claim credited a player with a match action, reframe it at the team level instead. Where a flagged claim put a player on the wrong team, use the correct team named in the flag or drop the player entirely. Where a flagged claim named a future pairing that is not actually set, rewrite it so the opponent stays open. Where a flagged claim treated an unplayed match as finished or invented a past meeting, rewrite that part as a preview of what is still to come, using the correct facts stated in the flags. Fix wrong days or countdowns with the corrected times in the flags. Never use em dashes. Output the corrected entry wrapped in <entry> and </entry> tags, nothing else.

ENTRY:
{entry}"""

    message = client.messages.create(
        model=AUX_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    log_usage("repair", message)
    if message.stop_reason == "max_tokens":
        return None
    text = "".join(b.text for b in message.content if b.type == "text")
    match = re.search(r"<entry>(.*?)</entry>", text, re.DOTALL)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return None


def generate_commit_message(entry):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=AUX_MODEL,
        max_tokens=30,
        messages=[{
            "role": "user",
            "content": f"Write a git commit message for this sports journal entry. 5 words max, punchy, captures the mood not the content. No punctuation, no quotes, no em dashes. Just the message.\n\n{entry}"
        }],
    )
    log_usage("commit_msg", message)
    suffix = message.content[0].text.strip().strip('"').strip("'")
    return suffix


def save_entry(entry):
    journal_dir = Path("journal")
    journal_dir.mkdir(exist_ok=True)
    filename = journal_dir / f"{today.strftime('%y-%m-%d')}.md"
    date_str = today.strftime("%-d %B %Y")
    content = f"# {date_str}\n\n{entry}\n"
    filename.write_text(content, encoding="utf-8")
    print(f"Saved: {filename}")
    commit_msg = generate_commit_message(entry)
    Path("commit_msg.txt").write_text(commit_msg, encoding="utf-8")
    print(f"Commit message: {commit_msg}")
    return filename


def main():
    dry_run = "--dry-run" in sys.argv
    print(f"Running daily sports agent for {today}")
    priority, context = build_context()
    print(f"Priority: {priority}")
    use_search = priority in ("quiet", "team_news")
    writer_model = TOURNAMENT_WRITER_MODEL if priority == "major_tournament" else WRITER_MODEL
    print(f"Writer model: {writer_model}")
    system, user = build_prompt(priority, context, use_search)
    entry, evidence = generate_entry(system, user, use_search, writer_model)

    violations = verify_entry(entry, context, evidence)
    repairs = 0
    while violations and repairs < 2:
        print("[warn] unsupported claims found, repairing:")
        for v in violations:
            print(f"  - {v}")
        repaired = repair_entry(entry, violations)
        if not repaired:
            break
        entry = repaired
        repairs += 1
        violations = verify_entry(entry, context, evidence)
    if violations:
        raise RuntimeError(
            "entry still fails factcheck after repairs, refusing to publish: "
            + "; ".join(violations)
        )

    if dry_run:
        print("--- dry run, entry not saved ---")
        print(entry)
        return
    save_entry(entry)
    print("Done.")


if __name__ == "__main__":
    main()
