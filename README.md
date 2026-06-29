# Your Daily Sports Agent

An AI sports journalist that wakes up every day and writes about what matters.

Built with Claude Haiku and GitHub Actions. Every morning at 7 AM UTC, the agent pulls live sports data, figures out what is worth talking about, and writes a short opinionated entry committed straight to this repo.

## What it covers

- **Football:** Fenerbahce, Real Madrid, Arda Guler, Mbappe, Champions League, Europa League, Premier League, La Liga, Super Lig, World Cup, Euros
- **Basketball:** LeBron James, Los Angeles Lakers, NBA

## How it prioritizes

The agent is not equally excited about everything. It follows this order:

1. Active major tournament (World Cup, Euros, NBA Finals/Playoffs)
2. Fenerbahce or Real Madrid news
3. European football (UCL/UEL + domestic leagues)
4. NBA season, rumors and games
5. Regular matchdays with the agent's own takes
6. Quiet days get a fun historical fact or an "on this day in sports history" moment

Upcoming derbies get bumped up automatically. If Galatasaray or Barcelona drop points, expect the agent to notice.

## Writing style

Opinionated, direct, occasionally funny. No match report copy-paste. The agent adds its own takes, makes jokes when rivals slip up, and ends every entry with one sentence worth remembering. No em dashes.

## Stack

- [Claude Haiku](https://anthropic.com) for writing
- [football-data.org](https://football-data.org) for football data
- [balldontlie.io](https://balldontlie.io) for NBA data
- GitHub Actions for daily scheduling

## Setup

1. Clone the repo
2. Add the following secrets to your GitHub repo under Settings > Secrets and variables > Actions:
   - `ANTHROPIC_API_KEY`
   - `FOOTBALL_DATA_API_KEY`
   - `BALLDONTLIE_API_KEY`
3. The workflow runs automatically every day at 7 AM UTC. You can also trigger it manually from the Actions tab.

## Local run

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in your keys
python agent.py
```

Entries are saved to the `journal/` folder as daily markdown files.
