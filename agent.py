import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
import anthropic

FOOTBALL_API_KEY = os.environ["FOOTBALL_DATA_API_KEY"]
BALLDONTLIE_API_KEY = os.environ["BALLDONTLIE_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
API_FOOTBALL_KEY = os.environ["API_FOOTBALL_KEY"]

FOOTBALL_BASE = "https://api.football-data.org/v4"
BALLDONTLIE_BASE = "https://api.balldontlie.io/v1"
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

API_FOOTBALL_TEAMS = {
    "Real Madrid": 541,
    "Fenerbahçe": 635,
    "Turkey": 21,
}

with open("config.json") as f:
    CONFIG = json.load(f)

today = datetime.now(timezone.utc).date()
yesterday = today - timedelta(days=1)
in_3_days = today + timedelta(days=3)


def football_headers():
    return {"X-Auth-Token": FOOTBALL_API_KEY}


def balldontlie_headers():
    return {"Authorization": BALLDONTLIE_API_KEY}


def api_football_headers():
    return {"x-apisports-key": API_FOOTBALL_KEY}


def get_player_stats_for_team(team_id, team_name):
    try:
        r = requests.get(
            f"{API_FOOTBALL_BASE}/fixtures",
            headers=api_football_headers(),
            params={"team": team_id, "last": 1},
            timeout=10,
        )
        if r.status_code != 200:
            return ""
        fixtures = r.json().get("response", [])
        if not fixtures:
            return ""
        fixture = fixtures[0]
        fixture_date = fixture["fixture"]["date"][:10]
        if fixture_date < str(yesterday):
            return ""
        fixture_id = fixture["fixture"]["id"]
        home = fixture["teams"]["home"]["name"]
        away = fixture["teams"]["away"]["name"]
        score = fixture["goals"]

        pr = requests.get(
            f"{API_FOOTBALL_BASE}/fixtures/players",
            headers=api_football_headers(),
            params={"fixture": fixture_id, "team": team_id},
            timeout=10,
        )
        if pr.status_code != 200:
            return ""
        players_data = pr.json().get("response", [])
        if not players_data:
            return ""

        lines = [f"{team_name} match: {home} {score['home']}-{score['away']} {away}"]
        for team_block in players_data:
            for p in team_block.get("players", []):
                name = p["player"]["name"]
                stats = p["statistics"][0] if p.get("statistics") else {}
                goals = stats.get("goals", {}).get("total") or 0
                assists = stats.get("goals", {}).get("assists") or 0
                rating = stats.get("games", {}).get("rating")
                minutes = stats.get("games", {}).get("minutes") or 0
                if minutes > 0:
                    line = f"  {name}: {minutes}min"
                    if goals:
                        line += f", {goals}G"
                    if assists:
                        line += f", {assists}A"
                    if rating:
                        line += f", rating {float(rating):.1f}"
                    lines.append(line)
        return "\n".join(lines)
    except Exception:
        return ""


def get_all_player_stats():
    parts = []
    for team_name, team_id in API_FOOTBALL_TEAMS.items():
        stats = get_player_stats_for_team(team_id, team_name)
        if stats:
            parts.append(stats)
    return "\n\n".join(parts)


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
    if 4 <= month <= 6:
        return "playoffs"
    return "regular season"


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
    if turkey_upcoming:
        priority = "turkey"
        lines = [format_match(m) for m in turkey_upcoming]
        sections.append("TURKEY NATIONAL TEAM (upcoming):\n" + "\n".join(lines))

    tournament_name, tournament_matches = get_active_major_tournament()
    if tournament_matches:
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

    player_stats = get_all_player_stats()
    if player_stats:
        sections.append("PLAYER STATS (highlight whoever performed interestingly, not just the usual names):\n" + player_stats)

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
        if priority == "quiet" and nba_season == "playoffs":
            priority = "nba_playoffs"
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
    files = sorted(journal_dir.glob("*.md"), key=lambda f: f.stem)
    recent = files[-n:] if len(files) >= n else files
    parts = []
    for f in recent:
        parts.append(f.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts)


def build_prompt(priority, context):
    date_str = today.strftime("%d/%m/%y")
    entry_number = get_entry_number()
    recent_entries = get_recent_entries()

    priority_instructions = {
        "turkey": "The Turkish national team is playing or just played. This takes top priority. The writer is Turkish, so personal investment is real.",
        "major_tournament": "A major international tournament is active. Make it the centerpiece of today's entry. Drama, stakes, sharp takes.",
        "derby": "There is an upcoming or recent derby. Lead with it. Build the anticipation or dissect the result.",
        "team_news": "Focus on Fenerbahçe and/or Real Madrid. What's happening with the team, key players like Arda Güler and Mbappé?",
        "european": "European football is the main dish today. UCL or UEL action takes priority.",
        "nba_playoffs": "NBA Playoffs are on. Give basketball significant weight alongside football.",
        "quiet": "It's a quiet day in sports. Write a fun historical piece — pick a memorable moment from sports history that happened on or around this date (any year), or share a fascinating fact about one of the followed teams or players. Be creative and specific.",
    }

    instruction = priority_instructions.get(priority, priority_instructions["quiet"])

    system = f"""You are a sports journalist with strong opinions, dry humor, and genuine tactical knowledge. This is a public daily journal — professional but never boring. Write like someone who actually cares and knows how to talk about it.

**Beat:** Football (Fenerbahçe, Real Madrid, Arda Güler, Mbappé, UCL, UEL, Premier League, La Liga, Süper Lig, World Cup, Euros) and basketball (LeBron James wherever he plays, Lakers, NBA).

**Allegiances:** Turkey national team, Real Madrid, Fenerbahçe. Support them, suffer with them. Your mood tracks their results — losses make you visibly down, analyze what went wrong; big wins let it show; a trophy win makes that entry feel completely different. In tournaments, cheer for these three first. If one is eliminated, pick a replacement based on style or a player you respect — don't jump ship every round. Ronaldo over Messi, LeBron over Jordan. Acknowledge the other side's greatness, but you know where you stand.

**Rivalries:** Barcelona and Galatasaray are the hatewatches — you follow them to enjoy their misery. When they slip, say something. Witty, not petty. Beşiktaş and Atlético dropping points is worth a smirk too. Never dislike a team without a reason.

**How to write:**
- This is a journal, not a results board. Results are context, not content. Write about what actually interests you that day — a tactical trend, a player's form, a historical parallel, a rivalry angle.
- Show tactical intelligence. Pressing, positioning, momentum shifts, individual errors. Don't say "they played well," say why.
- Make predictions for upcoming matches. Reference past predictions in future entries, right or wrong.
- Occasionally drop an "on this day" fact woven naturally — covered sports only, no tennis or hockey.
- Occasionally nod to "the Editor" who runs this. Brief, never forced.
- Acknowledge milestones naturally: entry 1 gets a line, entries 50/100/200/365 get a nod. Ignore everything else.
- Only mention Turkey if there is an upcoming Turkey match in the data.
- End with one sentence that provokes thought, lands a joke, or makes a bold prediction.

**Hard rules:**
- Never use em dashes. Use commas, periods, or restructure.
- Never invent fixtures or results. Stick strictly to the data.
- No exclamation marks. No forced humor. No sugarcoating.
- Don't call this "the column." Just write.
- Commit messages are 5 words max, punchy, no punctuation, no em dashes. They capture the mood of the entry, not summarize it.

Today's priority: {instruction}"""

    past = f"\n\nPrevious entries (for context and continuity — reference predictions or themes where relevant):\n{recent_entries}" if recent_entries else ""
    user = f"Date: {date_str}\nEntry number: {entry_number}\n\nSports data:\n{context if context else 'No live data available today.'}{past}\n\nWrite today's entry."

    return system, user


def generate_entry(system, user):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": user}],
        system=system,
    )
    return message.content[0].text


def generate_commit_message(entry):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    date_str = today.strftime("%d/%m/%y")
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=30,
        messages=[{
            "role": "user",
            "content": f"Write a commit message suffix for this sports journal entry. Punchy, 4-5 words max, captures the mood. No punctuation at the end, no quotes, no em dashes. Just the suffix.\n\n{entry}"
        }],
    )
    suffix = message.content[0].text.strip().strip('"').strip("'")
    return suffix


def save_entry(entry):
    journal_dir = Path("journal")
    journal_dir.mkdir(exist_ok=True)
    filename = journal_dir / f"{today.strftime('%d-%m-%y')}.md"
    date_str = today.strftime("%d/%m/%y")
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
