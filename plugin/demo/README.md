# demo

The story video, reproducibly: one local model on one GPU, eight agents each doing one step of the same fix.

- `ledger/` is the repo the agents work on: a 20-line running-balance calculator with one planted off-by-one (`entries[1:]`) and a test that catches it. Copy it to `~/demo/ledger`, `git init`, commit, and set a git identity.
- `story.sh` runs on the Omarchy host. It records `HDMI-A-3`, loads the recommended recipe from idle, opens each installed agent through `omarchy-local-ai open-agent` with its prompt, and writes `/tmp/story-marks.txt` with the start of every chapter. Eight chapters: pi (where am I), opencode (find the bug), codex (fix it), claude (review the diff), crush (run the tests), omp (commit), copilot (PR description), grok (summarize the log).
- `cut.py raw.mp4 marks.txt out.mp4` tightens the raw take: each chapter keeps its opening and its answer.

Every prompt is in `story.sh`. Nothing is scripted on the model side; the answers in the video are what the model said.
