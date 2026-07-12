# Project Instructions

## Journal Entries
- Factcheck every claim before committing or pushing: scores, goal counts, team names, match outcomes, competition format (group stage vs knockout). Search online to verify if unsure.
- Commit message for the first entry of a tournament or season: "day one". Future entries: 5-word max title reflecting the day's content, sourced from commit_msg.txt
- Never use group stage language (points, standings) for knockout matches
- When a match ends in a penalty shootout, the score to report is the 90-minute or extra time result. Penalties are a separate event — reference them in prose, not as part of the scoreline.
- Never make geographic or continental claims about a group of teams unless every team in that group actually belongs there.
- This is a daily sports journal, not a results board. Don't just list game results one after another. Write freely: analysis, opinions, historical tangents, player takes, anything — as long as it's factually correct.
- Predictions are encouraged for upcoming matches. In future entries, referencing back to earlier predictions is allowed and welcome.
- Write in first person, never use em dashes, don't repeat topics already covered in recent entries.
- An entry must end complete. Before committing, check the text isn't cut off mid-sentence (max_tokens truncation has pushed unfinished entries before). If truncated, regenerate or raise the token limit, never push it as-is.

## Testing & Costs
- NEVER run the live agent (agent.py against real APIs) for testing or debugging without asking first. It burns Claude API credits and football-data rate limits. Use mocked API responses or a dry-run that skips LLM and HTTP calls.
- Use both football APIs equally; don't hammer one until it rate-limits.
- Model and max_tokens choices are cost decisions: ask before changing them.

## Scheduling
- Daily run is `.github/workflows/daily.yml` (GitHub Actions cron). Actions cron is queued, not exact: firing 15-120 min late is normal, not a bug. Check runs with `gh run list`/`gh run view --log` instead of asking me to report back.
- Journal filenames must sort chronologically (year first), date headers in "7 July 2026" style.
