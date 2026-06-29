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

    tournament_name, tournament_matches = get_active_major_tournament()
    if tournament_matches:
        priority = "major_tournament"
        formatted = [format_match(m) for m in tournament_matches[:6]]
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


def build_prompt(priority, context):
    date_str = today.strftime("%B %d, %Y")

    priority_instructions = {
        "major_tournament": "A major international tournament is active. Make it the centerpiece of today's entry. Deep analysis, drama, stakes.",
        "derby": "There is an upcoming or recent derby. Lead with it. Build the anticipation or dissect the result.",
        "team_news": "Focus on Fenerbahçe and/or Real Madrid. What's happening with the team, key players like Arda Güler and Mbappé?",
        "european": "European football is the main dish today. UCL or UEL action takes priority.",
        "nba_playoffs": "NBA Playoffs are on. Give basketball significant weight alongside football.",
        "quiet": "It's a quiet day in sports. Write a fun historical piece — pick a memorable moment from sports history that happened on or around this date (any year), or share a fascinating fact about one of the followed teams or players. Be creative and specific.",
    }

    instruction = priority_instructions.get(priority, priority_instructions["quiet"])

    system = f"""You are a sharp, opinionated sports journalist writing a daily entry for a personal sports blog. Your beat covers:
- Football: Fenerbahçe, Real Madrid, Arda Güler, Kylian Mbappé, Champions League, Europa League, Premier League, La Liga, Süper Lig, World Cup, Euros
- Basketball: LeBron James (follow him to whatever team he's on), Los Angeles Lakers, NBA

Your writing style:
- Confident and direct, like a seasoned columnist
- Inject personal takes and opinions, not just facts
- Use vivid language but stay concise
- 250-350 words max
- No fluff, no generic filler lines like "what a day in sports"
- End with one sharp sentence that sticks

Today's priority: {instruction}"""

    user = f"Date: {date_str}\n\nSports data:\n{context if context else 'No live data available today.'}\n\nWrite today's entry."

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


def save_entry(entry):
    journal_dir = Path("journal")
    journal_dir.mkdir(exist_ok=True)
    filename = journal_dir / f"{today}.md"
    date_str = today.strftime("%B %d, %Y")
    content = f"# {date_str}\n\n{entry}\n"
    filename.write_text(content, encoding="utf-8")
    print(f"Saved: {filename}")
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
