# HireAce admin portal

A web app to watch and manage every workstation that has HireAce: online or offline, HireAce up
or down, updates, restart, deactivate, and OpenAI usage with monthly limits. It works on phones.

## How it fits together

```
 Workstation (any network)                           Portal (Vercel + Postgres)
 ┌──────────────────────────────┐   check-in, 1/min  ┌──────────────────────────┐
 │ fleet.ps1 (monitor)          │ ─────────────────► │ status, token counts     │
 │  runs from Windows sign-in,  │ ◄───────────────── │ orders, limits           │
 │  even when HireAce is closed │   answer           └──────────────────────────┘
 └──────────────────────────────┘                                ▲
        │ on an update order: downloads from GitHub              │ browser
        │ checks the signature, installs, rolls back on failure  │
        ▼                                                      Admin
 %LOCALAPPDATA%\HireAce
```

A PC behind a router cannot be reached from the internet, so the portal never calls a PC: each one
calls out, and orders travel in the answer. An order takes up to one check-in to arrive.

| Shown as | Means |
| --- | --- |
| Online · HireAce up | Monitor checked in lately; gatekeeper, voice agent and web app all run |
| Online · Partly up | Checked in, but one of the three is not running |
| Online · HireAce down | Checked in, and HireAce is closed (normal when the user closed the panel) |
| Offline | No check-in for 3 minutes: PC off, asleep, signed out, or no internet |
| Deactivated | Turned off here: HireAce stops and will not start until activated |

The monitor runs per Windows user while that user is signed in. It sends the PC and user name,
version, which parts run, whether a call is on, free memory and disk, and token counts. It never
sends conversations, screens or emails.

## Run it on this PC

```powershell
cd admin
pnpm install
copy .env.example .env.local   # then fill it in; pnpm hash-password "a long password"
pnpm build
pnpm start                     # http://localhost:3200
```

Without `DATABASE_URL` it keeps its data in `admin\.data`.

## Put it online

1. **Database:** create a Postgres database (Neon has a free plan) and copy its connection string.
2. **Vercel:** a new project from this repository, with **Root Directory** `admin`, and every
   setting from `.env.example`:
   - `ADMIN_USERNAME`, and `ADMIN_PASSWORD_HASH` from `pnpm hash-password "a long password"`
   - `SESSION_SECRET`: any long random text
   - `LICENSE_SECRET`: the contents of `installer\license-secret.txt`
   - `RELEASE_PUBLISH_KEY`: the contents of `installer\release-publish-key.txt`
   - `DATABASE_URL`
3. **Installer:** add `HIREACE_PORTAL_URL=https://your-portal.vercel.app` to `agent\.env.local`, then
   run `installer\build.ps1`. PCs installed from that installer join the portal by themselves, with
   their license code. PCs installed before this need it once; after that they update from here.

Checking in once a minute is about 43,000 requests per PC per month, so about 860,000 for 20 PCs. Check that against the
limits of your Vercel and database plans, and note Vercel's free plan is for non-commercial use.
Check-ins can be made less frequent under Usage.

## Publish an update

```powershell
git commit ...                 # only committed code is packaged
powershell -ExecutionPolicy Bypass -File .\installer\publish-release.ps1 -Portal https://your-portal.vercel.app -Notes "What changed"
```

It packs the code, signs it and uploads it as a GitHub release (the repository is public, and the
package holds nothing else). Nothing installs until you choose it on **Releases** or **Workstations**.

On each PC an update waits for any call to end, checks the signature, stops HireAce, replaces the code,
reinstalls and rebuilds (about 5 minutes), and starts HireAce again if it was running. If a step fails it goes
back to the previous version. Keys, settings, the price list and the template are not in the package and are kept.

**The signing key.** PCs install only what is signed with `installer\release-key.xml`, which stays on your
PC, so someone who gets into the portal still cannot put code on your workstations. Back it up: without it you
cannot publish updates, and PCs would need a new installer to accept a new key. Never commit it or share it.

## Usage and limits

Each PC reports the voice model's token counts, and the portal prices them, so the dollars are an
**estimate**. Prices are editable under Usage (image input is a guess: check it). Not counted: the smaller
OpenAI calls made outside the voice model (transcript clean-up, screen reading). For the real bill, set
`OPENAI_ADMIN_KEY`, and the bill for the whole OpenAI organization shows next to the estimate. That key can
also manage the organization, so it stays on the server only.

Limits are off until you set them. At a limit the portal only warns, unless you choose **Refuse new calls**:
then HireAce says the limit was reached and ends new calls; a call already open finishes. They count from the 1st
of the month, UTC, and take up to one check-in to apply.

## What this does not protect against

All PCs share the OpenAI and LiveKit keys in the installer. Deactivating stops HireAce on a PC, but someone who
copied those keys could still use them. To cut that off, replace the keys, or later give each PC its own.
Likewise a local administrator can remove the monitor from their own PC: it then shows as offline.

The portal has one admin sign-in, with no second factor yet. Use a long password.
