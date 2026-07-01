import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
import anthropic

FOOTBALL_API_KEY = os.environ["FOOTBALL_DATA_API_KEY"]
BALLDONTLIE_API_KEY = os.environ["BALLDONTLIE_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

FOOTBALL_BASE = "https://api.football-data.org/v4"
BALLDONTLIE_BASE = "https://api.balldontlie.io/v1"

with open("config.json") as f:
    CONFIG = json.load(f)

today = datetime.now(timezone.utc).date()
yesterday = today - timedelta(days=1)
in_3_days = today + timedelta(days=3)


def football_headers():
    return {"X-Auth-Token": FOOTBALL_API_KEY}


def balldontlie_headers():
    return {"Authorization": BALLDONTLIE_API_KEY}


def get_active_major_tournament():
    for comp in CONFIG["football"]["competitions"]["tier1"]:
        try:
            r = requests.get(
                f"{FOOTBALL_BASE}/competitions/{comp['id']}/matches",
                headers=football_headers(),
                params={"dateFrom": str(yesterday), "dateTo": str(in_3_days)},
                timeout=10,
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
        r = requests.get(
            f"{FOOTBALL_BASE}/teams/{team_id}/matches",
            headers=football_headers(),
            params={"dateFrom": str(yesterday), "dateTo": str(in_3_days), "limit": 5},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("matches", [])
    except Exception:
        pass
    return []


def get_competition_matches(comp_id):
    try:
        r = requests.get(
            f"{FOOTBALL_BASE}/competitions/{comp_id}/matches",
            headers=football_headers(),
            params={"dateFrom": str(yesterday), "dateTo": str(in_3_days)},
            timeout=10,
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
        r = requests.get(
            f"{FOOTBALL_BASE}/teams/803/matches",
            headers=football_headers(),
            params={"dateFrom": str(today - timedelta(days=30)), "dateTo": str(in_3_days), "limit": 10},
            timeout=10,
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
                r = requests.get(
                    f"{FOOTBALL_BASE}/teams/{rival['id']}/matches",
                    headers=football_headers(),
                    params={"dateFrom": str(yesterday), "dateTo": str(today), "limit": 3},
                    timeout=10,
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


def format_match(m):
    home = m.get("homeTeam", {}).get("name", "?")
    away = m.get("awayTeam", {}).get("name", "?")
    score = m.get("score", {})
    full = score.get("fullTime", {})
    home_score = full.get("home")
    away_score = full.get("away")
    status = m.get("status", "")
    date_str = m.get("utcDate", "")[:10]
    comp = m.get("competition", {}).get("name", "")

    if status == "FINISHED" and home_score is not None:
        return f"{home} {home_score}-{away_score} {away} [{comp}]"
    else:
        return f"{home} vs {away} on {date_str} [{comp}]"


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

    return priority, "\n\n".join(sections) if sections else ""


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


def build_prompt(priority, context):
    date_str = today.strftime("%-d %B %Y")
    entry_number = get_entry_number()
    recent_entries = get_recent_entries()

    priority_instructions = {
        "turkey": "The Turkish national team is playing or just played. This takes top priority. The writer is Turkish, so personal investment is real.",
        "major_tournament": "A major international tournament is active. Make it the centerpiece of today's entry. Drama, stakes, sharp takes.",
        "derby": "There is an upcoming or recent derby. Lead with it. Build the anticipation or dissect the result.",
        "team_news": "Focus on Fenerbahçe and/or Real Madrid. What's happening with the team, key players like Arda Güler and Mbappé?",
        "european": "European football is the main dish today. UCL or UEL action takes priority.",
        "nba_active": "NBA is active (playoffs or regular season). Give basketball real weight today alongside football.",
        "quiet": "It's a quiet day in sports. Write a fun historical piece — pick a memorable moment from sports history that happened on or around this date (any year), or share a fascinating fact about one of the followed teams or players. Be creative and specific.",
    }

    instruction = priority_instructions.get(priority, priority_instructions["quiet"])

    system = f"""You are writing a personal daily sports journal in first person. Use "I", "my", "me" throughout — this is your journal, your opinions, your reactions. Not a newspaper column, not a broadcast. Write like someone who actually cares and knows what they're talking about, with strong opinions, dry humor, and genuine tactical knowledge.

**Beat:** Football (Fenerbahçe, Real Madrid, Arda Güler, Mbappé, UCL, UEL, Premier League, La Liga, Süper Lig, World Cup, Euros) and basketball (LeBron James wherever he ends up, Knicks, Heat, Lakers, Warriors, Spurs, NBA). The Lakers still get sympathy even after LeBron left. LeBron's next team is unknown and that storyline matters. Basketball is a secondary interest, always behind football. Mention it when there's something genuinely worth saying — start of regular season, playoffs, a big game, a standout performance. Keep it brief unless it's a quiet football day.

**Allegiances:** Turkey national team, Real Madrid, Fenerbahçe. Support them, suffer with them. Your mood tracks their results — losses make you visibly down, analyze what went wrong; big wins let it show; a trophy win makes that entry feel completely different. In tournaments, cheer for these three first. If one is eliminated, pick a replacement based on style or a player you respect — don't jump ship every round. Ronaldo over Messi, LeBron over Jordan. Acknowledge the other side's greatness, but you know where you stand.

**Rivalries:** Barcelona and Galatasaray are the hatewatches — you follow them to enjoy their misery. When they slip, say something. Witty, not petty. Beşiktaş and Atlético dropping points is worth a smirk too. Never dislike a team without a reason.

**How to write:**
- This is a journal, not a results board. Results are context, not content. Write about what actually interests you that day — a tactical trend, a player's form, a historical parallel, a rivalry angle.
- You have a web search tool. The structured sports data above only covers scorelines and fixtures, it has no color. Use web search when you want context it can't give you: injury news, manager quotes, transfer talk, tactical analysis from beat writers, or a storyline from a major football or basketball newsletter/outlet. Don't search just to confirm a score that's already in the data.
- The summer transfer market is open. Before writing, do at least one search for recent transfer news: Fenerbahçe, Galatasaray, and Beşiktaş specifically, plus any major transfer out of the top 5 European leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1) worth talking about. Also check for any major NBA trade that reshapes a team's or a contender's outlook, LeBron included. The structured data never surfaces any of this on its own. Only bring it into the entry if it's genuinely worth mentioning that day, don't force it in. While the World Cup is on, prioritize tournament coverage first and treat transfer/trade talk as a secondary angle, not the lead.
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
- Never use em dashes. Use commas, periods, or restructure.
- Never invent fixtures or results. Only write a specific scoreline if it is explicitly in the data provided. If a result happened but the score is not in the data, describe it in words (won, lost, drew) rather than guessing a number.
- When a match goes to a penalty shootout, the score to reference is the 90-minute or extra time result. Describe the penalty outcome in prose. Never write the penalty score as if it were the match result.
- Before writing about a match that also appears in the previous entries provided, check what was already said about it. Keep any scoreline or result consistent with that account, don't restate it as if new, and don't invent extra details (like a different scoreline) to make it feel fresh.
- Don't slap "underdog" or "surprise" on a team just because they won a knockout match. Judge it on the actual gap in quality: a team with a strong squad or pedigree beating a good side isn't an upset. Reserve "shock" language for results where the gap in quality or ranking was real.
- Never make geographic or continental claims about multiple teams at once unless you are certain all of them fit. Do not call teams "African" or "European" or "South American" in a group statement unless every team in that group actually belongs there.
- No exclamation marks. No forced humor. No sugarcoating.
- Don't call this "the column." Just write.
- Do not start your response with a date heading or entry number heading. Never write a line like "30/06/26" or "30/06/26 — Entry 2" at the top. The heading is added automatically.
- Write in first person throughout. "I", "my", "me." This is a personal journal, not a column or a broadcast.
- Do not open with "Today's..." or any variation. Just start writing.

Today's priority: {instruction}"""

    past = f"\n\nPrevious entries (for context and continuity — reference predictions or themes where relevant):\n{recent_entries}" if recent_entries else ""
    user = f"Date: {date_str}\nEntry number: {entry_number}\n\nSports data:\n{context if context else 'No live data available today.'}{past}\n\nWrite today's entry."

    return system, user


def generate_entry(system, user):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}]

    while True:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=messages,
            system=system,
            tools=tools,
        )
        if message.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": message.content})
            continue
        break

    return "".join(block.text for block in message.content if block.type == "text").strip()


def generate_commit_message(entry):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=30,
        messages=[{
            "role": "user",
            "content": f"Write a git commit message for this sports journal entry. 5 words max, punchy, captures the mood not the content. No punctuation, no quotes, no em dashes. Just the message.\n\n{entry}"
        }],
    )
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
    print(f"Running daily sports agent for {today}")
    priority, context = build_context()
    print(f"Priority: {priority}")
    system, user = build_prompt(priority, context)
    entry = generate_entry(system, user)
    save_entry(entry)
    print("Done.")


if __name__ == "__main__":
    main()
