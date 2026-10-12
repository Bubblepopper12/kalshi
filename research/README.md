# Research inputs

Raw material for tipster tracking (see CONCEPT.md, "Tipster scoring").

- `youtube_channels.csv` — channels that post betting picks, from Gemini research (Oct 12, 2026),
  each marked `confirmed` (found on the web) or `unconfirmed`. Records they claim are not trusted:
  every pick gets graded against real results once it's recorded with its upload time.

Picks extracted from videos go in `youtube_picks.csv` (same columns as the Gemini prompt),
one row per pick, only when the upload time and the pick were checked in the video itself.
