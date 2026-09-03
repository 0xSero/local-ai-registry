# demo

The story video, reproducibly: one local model on one GPU, eight agents each doing one step of the same fix, the way a person does it: the cursor clicks the bar icon, picks the agent in the popup, the agent opens on the local model, the prompt is typed live.

- `ledger/` is the repo the agents work on: a 20-line running-balance calculator with one planted off-by-one (`entries[1:]`) and a test that catches it. Copy it to `~/demo/ledger`, `git init`, commit, set a git identity, then `omarchy-local-ai agent-dir ~/demo/ledger`.
- Per-agent flags, so agents do not stop at their own approval prompts: `omarchy-local-ai agent-args claude -- --permission-mode acceptEdits --allowedTools=Bash`, `codex -- --dangerously-bypass-approvals-and-sandbox`, `opencode -- --auto`, `crush -- --yolo`, `omp -- --auto-approve`, `copilot -- --allow-all`, `grok -- --always-approve`.
- `story.sh` runs on the Omarchy host as a user unit (`systemd-run --user ... bash story.sh`). It records `HDMI-A-3` with the cursor, loads the recommended recipe from idle by clicking Start, then for each agent: click the icon, click the agent, place its window on the recorded output, type the prompt, wait, close. `click.py` clicks through a virtual uinput mouse; the cursor moves with Hyprland's `hl.dsp.cursor.move`. It writes `/tmp/story-marks.txt` with recorder-relative chapter times.
- `pickup.sh "<step line>"` re-records one chapter at the current repo state with the same mechanics.
- `cut.py raw.mp4 marks.txt out.mp4 [pickup.mp4 pickup-marks.txt]` keeps every action at 1x and runs the waiting as a time-lapse; pickups replace same-named chapters.

Every prompt is in `story.sh`. Nothing is scripted on the model side; the answers in the video are what the model said.
