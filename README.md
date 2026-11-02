# HireAce

A voice-controlled AI agent with a human in the loop. You talk to HireAce, and it works
directly on your Windows PC: its own Chrome window for Gmail and the web, and desktop
Word, Excel, PowerPoint and Outlook. Risky actions wait for your approval, and you can
watch it from your phone.

## Features

- **Voice conversations** — real-time voice I/O on LiveKit Agents with OpenAI Realtime, English or Mandarin
- **Direct PC control** — its own Chrome window (separate profile, so your sign-ins stay put) plus the real mouse, keyboard and desktop apps
- **Human in the loop** — a gatekeeper service approves, asks, or denies every action; send/submit/delete and any mouse or keyboard input outside its browser wait for "yes" or an **Approve** tap; payments are always blocked
- **Emergency stop** — slam the mouse into any screen corner and desktop actions stop for a minute
- **Phone viewer** — tap **My PC** in the web app on a phone to watch the PC live
- **Mobile responsive** — the Next.js web app works on phones, tablets and desktop

### Roadmap

- Switch the AI brain between models (Claude, Codex, MiMo)
- Edit Slides, Word and Excel documents, highlight the changes, save, and send them by email

## Project structure

```
hireace-agent/
├── start.ps1                   # Starts everything on this PC
├── .github/workflows/          # CI: tests and ruff lint
└── agent/                      # Main project
    ├── src/
    │   ├── agent.py            # Entrypoint — AgentServer, Assistant class
    │   ├── prompts.py          # System prompts and instructions
    │   ├── tools.py            # Browser function tools
    │   ├── desktop_tools.py    # Mouse, keyboard, window and app tools
    │   ├── browser.py          # Playwright browser manager (agent's Chrome profile)
    │   ├── local_desktop.py    # Windows mouse/keyboard/windows/screenshots
    │   ├── action_backend.py   # Routes proposed actions to the gatekeeper
    │   ├── gatekeeper.py       # Approve / ask / deny service + audit log
    │   ├── policy.py           # Gatekeeper rules
    │   ├── screen_stream.py    # Streams the PC screen to the phone viewer
    │   └── transcript_*.py     # Transcript guard and rephraser
    ├── tests/                  # Pytest suite and agent evals
    ├── frontend/               # Next.js web app (voice UI, approvals, phone viewer)
    ├── pyproject.toml / uv.lock
    ├── .env.example            # Environment variable template
    ├── AGENTS.md               # Coding agent guide
    └── plan.md                 # Architecture notes
```

## Prerequisites

- **Windows 10/11** with **Google Chrome** installed
- **Python** >= 3.10 and **[uv](https://docs.astral.sh/uv/)**
- **Node.js** >= 20 and **[pnpm](https://pnpm.io/)**
- Desktop Microsoft Office (optional, for Word/Excel/PowerPoint/Outlook)

## Installation

```powershell
cd agent
uv sync
cd frontend
pnpm install
```

## Configuration

Copy the example environment file and fill in your credentials:

```powershell
cd agent
copy .env.example .env.local
```

| File | Variables |
|---|---|
| `agent/.env.local` | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `OPENAI_API_KEY` |
| `agent/frontend/.env.local` | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| `agent/.env` | `GATEKEEPER_TOKEN=<random string>` (shared by the agent, gatekeeper and web app) |

**AI models (all OpenAI, one key):** voice brain `gpt-realtime-2.1` (female voice `marin`;
`OPENAI_VOICE` picks another), careful transcription `gpt-transcribe`, transcript
clean-up `gpt-4.1-mini`, screen helper `gpt-4.1-mini`. The agent sees your screen when
it works, but not your camera.

**Settings (the gear icon, top right):** voice, sign-offs, the quotation template and
folders, where to search for files, and the OpenAI key. They are kept in
`%USERPROFILE%\.hireace-agent\settings.json` and override `.env.local`; new calls use
them. Settings can be changed only on the PC itself (not from a phone).

**Email (Gmail on standby):** in Settings, **Open Gmail** opens Gmail in HireAce's own
Chrome window; sign in there once and leave the window open (it can be minimized). The
badge shows **Ready** with the account once it is signed in; **Send test** checks it.
HireAce reads email there with its page tools and sends by filling in Gmail's own
compose page in a new tab (attachments added through the page, sent with Ctrl+Enter,
tab closed again). No Google Cloud project or API keys. You name who each email goes
to (or it replies to the email being answered); a quotation goes to the inquiry's
sender with "Re: <subject>" and no copy. Every email waits for your approval, and an
email is never offered for approval while Gmail is not signed in.

## Running

```powershell
.\start.ps1              # starts gatekeeper + agent + web app (rebuilds the web app only if it changed)
.\start.ps1 -SkipBuild   # never rebuild the web app
.\start.ps1 -Lan         # also serve the web app to your network (phone viewer)
.\start.ps1 -NoPanel     # don't open the floating panel
```

The desktop icon runs `start.ps1 -Background`: no console window, each part's output
in `%USERPROFILE%\.hireace-agent\logs`, and **closing the panel quits HireAce**
(minimize it to keep HireAce on standby). Only one HireAce runs at a time: starting it
again brings up the open panel.

The HireAce panel opens by itself as a small window in the top-right corner. It stays on
top of other apps and you can drag it anywhere by its title bar. The **Full view** button
(top left) fills the screen; **Mobile view** shrinks it back to the vertical panel. It
uses its own Chrome profile, so allow the microphone once and it remembers. (Also at
http://localhost:3001.) Ctrl+C stops everything, including the panel.
Closed the panel? Reopen it with `powershell -ExecutionPolicy Bypass -File .\panel.ps1`.
Minimize the panel and a little HireAce character sits at the bottom right of the
screen (`bubble.ps1`, drawn by `assets/make_avatar.py`): click it to bring the panel
back, drag it to move it. If you are away from the mouse and keyboard for 5 minutes it
knocks on the screen (again every 2 minutes) until you are back.

A call started from the phone appears on the PC's panel by itself and follows the
conversation live, read-only, with no sound. The bar under the phone link shows
whether Gmail is signed in, in any browser; sending needs it signed in in HireAce's
own browser (Settings: Open Gmail).

Noise cancellation is off by default because it made audio choppy on Windows; set
`NOISE_CANCELLATION=on` in `agent/.env.local` for a noisy room.

- **First run:** the agent's Chrome window has its own profile
  (`%USERPROFILE%\.hireace-agent\chrome-profile`). Sign in to websites there once, and
  connect Gmail in Settings.
- **Language:** the **EN | 中文** switch (top right) picks English or Mandarin for the
  next call. It is sent to the agent as dispatch metadata (`src/agent.py` `LANGUAGES`).
- **Phone viewer:** run with `-Lan`, open `http://<PC's IP>:3001` on the phone, start a
  call and tap **My PC**. Only do this on a trusted network: anyone on it can open the
  app and approve actions. Phone browsers allow the microphone only over HTTPS, so
  talking from the phone needs an HTTPS address (for example via Tailscale).

### Safety architecture

| Process | Role |
|---|---|
| agent (`src/agent.py`) | Voice brain (LiveKit + OpenAI Realtime). Can only *propose* actions. |
| gatekeeper (`src/gatekeeper.py`) | Sole authority over actions, rules in `src/policy.py`: allow, ask the user, or deny. Listens on 127.0.0.1 only. Payments are always denied and cannot be approved. Every decision is appended to `%USERPROFILE%\.hireace-agent\audit.jsonl`. |
| web app (`frontend/`) | Voice UI, Approve/Deny cards, and the phone viewer. |

What needs your approval: consequential clicks (send, submit, delete, post...),
password fields, closing a window, opening macro-enabled Office files, and **any mouse
click, drag, typing or key press outside the agent's own browser**. Say "yes" or tap
**Approve**. Programs and scripts (`.exe`, `.bat`, `.ps1`...) can never be opened.
To limit where it searches for files, set `HIREACE_SEARCH_DIRS` (`;`-separated folders).

The agent sees your screen: screenshots go to OpenAI so it (and its screen helper) can read it and aim clicks.
Close anything sensitive before asking it to work on the desktop.

Voice commands, in any wording:

| Say | The agent does |
|---|---|
| "Open the browser" / "close the browser" | Opens / closes its Chrome window |
| "Open youtube.com", "search the web for ..." | Browses in its Chrome window |
| "Open Gmail" | Opens Gmail in its Chrome window |
| "Open Excel / Word / PowerPoint / Outlook" | Opens the desktop app |
| "Find my Acme proposal and open it" | Searches Desktop, Documents, Downloads, OneDrive and other drives, then opens the file (asks which one if several match) |
| "Look at my screen" | Takes a screenshot and describes it |

## Development

`uv run src/agent.py console` runs a terminal-only voice chat (gatekeeper in-process).
For frontend work, `pnpm dev` in `agent/frontend` (http://localhost:3000) alongside
`.\start.ps1`.

## Tests

```powershell
cd agent
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Tech stack

| Component | Technology |
|---|---|
| Agent framework | LiveKit Agents 1.8 |
| LLM | OpenAI Realtime (gpt-realtime-2.1), gpt-transcribe, gpt-4.1-mini |
| Browser automation | Playwright (installed Chrome) |
| Desktop control | pyautogui, Win32 API |
| Noise cancellation | AI Coustics |
| Web app | Next.js 15, React 19, Tailwind CSS v4 |
| Package managers | uv (Python), pnpm (JS) |
| Languages | Python 3.10–3.14, TypeScript 5 |
