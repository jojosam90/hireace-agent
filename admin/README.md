# HireAce admin portal

A web app to watch and manage every workstation that has HireAce: online or offline, HireAce up
or down, updates, restart, deactivate, and OpenAI usage with monthly limits. It works on phones.

This repository is published from the `admin` folder of the HireAce repository, where the `installer`
scripts and the workstation monitor mentioned below live.

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
calls out, and orders travel in the answer. An order takes up to one check-in to arrive. A call
starting or ending is reported within seconds, without waiting for the next check-in.

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

## Who can sign in

The login page shows a card for each account: tap yours, then enter your password. There is one account
(`ADMIN_USERNAME`) until you set `ADMIN_ACCOUNTS`, a line of JSON with a username, name, role and password hash for
each person (`pnpm hash-password` makes a hash; see `.env.example`). Anyone who opens the page can see these names and
roles. The Activity page records which account did what.

After logging in once with **Remember me on this device**, tapping that card on that device shows the password filled in,
for 30 days from the last use. The device keeps a signed cookie, not the password, and it stops working when the password
or `SESSION_SECRET` changes. Other devices still have to type the password. Do not tick it on a shared PC. Anyone using a
remembered device can log in as that person, so lock the device; **Forget this device** on the login page ends it.

`ADMIN_PREFILL_PASSWORD` (or `prefillPassword` for an account in `ADMIN_ACCOUNTS`) fills the real password in on every
device. It is off unless set. It sends the password to anyone who opens the login page, so on a site reachable from the
internet it means no login at all: use it only on this PC or for a demo.

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
2. **Vercel:** a new project from this repository, with every
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

## Spending alerts

Set under **Usage**: alert at shares of a limit (50, 80 and 100% by default), when one day passes an amount, and
when the month is on pace to go over the budget (from the 3rd of the month). Each alert is raised once, shows on the
portal with a red count on Usage until acknowledged, and is emailed if `RESEND_API_KEY` and an address are set. Alerts
only tell you. To stop spending use **Refuse new calls**, or a hard limit at OpenAI (below).

Alerts run on the estimate, within one check-in of the usage. OpenAI's own spend alerts and hard limits (Organization
limits, or Project settings > Limits) run on OpenAI's own tracked spend and a PC cannot get around them: set one as the backstop.

## How fresh are the numbers?

| Source | Freshness | Covers |
| --- | --- | --- |
| Each voice response, reported by the PC (what this portal shows) | About a minute, one check-in | Voice model only, per workstation, priced as an estimate |
| OpenAI Usage API (`/v1/organization/usage/...`, Admin key) | Buckets of 1 minute, 1 hour or 1 day; OpenAI's reference states no delay | Whole organization, tokens, not per workstation |
| OpenAI Costs API (`/v1/organization/costs`, Admin key), the "Billed by OpenAI" chart | Daily buckets only, and OpenAI posts a day's costs some time after use | Whole organization, real dollars, by model |

The first row is the freshest: every response from the model carries its token counts. For fresher numbers lower the
check-in time under Usage (30 seconds at least).

## What this does not protect against

All PCs share the OpenAI and LiveKit keys in the installer. Deactivating stops HireAce on a PC, but someone who
copied those keys could still use them. To cut that off, replace the keys, or later give each PC its own.
Likewise a local administrator can remove the monitor from their own PC: it then shows as offline.

The portal has one admin sign-in, with no second factor yet. Use a long password.
