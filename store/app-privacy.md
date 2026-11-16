# App Privacy: the answers for App Store Connect

App Privacy (the "nutrition label") has **no API**. Set it by hand in App Store Connect → "Fantasy Edge: Game Day"
(app 6833213130) → App Privacy, then **Publish**. Our scripts never touch it.

**Up to 1.0 the app sends nothing to us.** It reads the board from the wearer's own Mac (`fantasyedge api` on the
LAN, the address they type), plays a video URL they paste, and writes Apple Intelligence summaries on the device. None of
that reaches us or anyone else, so 1.0's label is **Data Not Collected**.

**From 1.0.1 (the owner's call 2026-11-16, "update the native apps too"; Box Office rule 6) the app sends usage events**,
so the label changes to two rows, Usage Data → Product Interaction and Identifiers → Device ID, both for Analytics,
**linked**, **not tracking** (Cold Gas's design). **Change the label in App Store Connect and publish it in the same
submission as the 1.0.1 build**, never before (a 1.0 build must keep "Data Not Collected") and never after (1.0.1 must
not reach the store with the old label). 1.0 is PREPARE_FOR_SUBMISSION on 2026-11-16; if the owner submits 1.0.1
instead, rename that version to 1.0.1 and set the label in the same step.

## What leaves the headset, from 1.0.1

One host besides the wearer's own Mac: Box Office's first-party relay, `mutaafaziz.com/boxoffice/e/*` (mutaaf/box-office).

| Request | What it carries | Kept |
|---|---|---|
| `POST /boxoffice/e/batch/` (**from 1.0.1, unless the gear → Privacy → Share usage stats is off**) | `session_start` (returning 0/1, days since the last) and `space_open` (`board`, `board_space`, `tabletop` or `stadium`): enums and numbers only (`packages/swift/UsageKit`); a random install id; the app's version; `platform: visionos` | in the owner's PostHog project (through the relay: cookies stripped, the IP cut to /24 before it's forwarded, and `$geoip_disable` so no location is derived) |

Never sent: a league, team, manager or player, the board's address, a video URL, anything typed, a location, an
advertising id. No IDFA, no App Tracking Transparency prompt, no fingerprinting, no session replay, no autocapture, no
SDK. The one identifier is the **install id**: a random UUID made on the headset the first time an event is kept,
stored in UserDefaults (so deleting the app resets it), and deleted by the switch along with anything unsent. Debug
builds send nothing unless launched with `-insights`, so captures and look-dev runs never count.

## The label (1.0.1)

| Data type (Apple's name) | Collected | Purpose | Linked to the user | Used for tracking |
|---|---|---|---|---|
| Usage Data → **Product Interaction** (the usage events) | Yes | Analytics | **Yes** | **No** |
| Identifiers → **Device ID** (the random install id) | Yes | Analytics | **Yes** | **No** |

Everything else: **not collected**.

**In App Store Connect (with the 1.0.1 submission):** App Privacy → "Do you or your third-party partners collect data
from this app?" **Yes**. Tick Usage Data → *Product Interaction* and Identifiers → *Device ID*. For each: purpose
*Analytics* only; linked to the user's identity **Yes**; used for tracking **No**. Save, then **Publish**.

**Linked** because every event carries the install id (the owner chose linked over dropping the id for Cold Gas on
2026-11-13; every native app follows that design). **Tracking: No**: nothing is combined with other companies' data and
nothing goes to an ad network or broker.

A label with data collected needs a **privacy policy URL** on the app record. The app's Cast List page
(https://mutaaf.github.io/fantasy-edge/) has no privacy page yet; one must exist and be set before 1.0.1 is submitted.

## The privacy manifest

`apple/FantasyEdge/PrivacyInfo.xcprivacy` (new in 1.0.1, bundled by `apple/generate_project.py`) declares Product
Interaction and Device ID for Analytics, linked, not tracking; `NSPrivacyTracking` false, no tracking domains; and the
required-reason APIs the app calls: UserDefaults (CA92.1) and system boot time (35F9.1, `CACurrentMediaTime` for the
head pose in StadiumKit).

## Review notes (paste into App Review Information with 1.0.1)

USAGE COUNTS (NEW IN 1.0.1)
First-party, no SDK. Two counts (a session started; which space opened: the board, the immersive board, the tabletop or
the stadium) and a random install id go to our own relay at mutaafaziz.com/boxoffice, which strips cookies, cuts the IP
and forwards them to our analytics project (PostHog). Nothing about the wearer's leagues, teams or players is ever sent.
The gear → Privacy → Share usage stats turns them off and deletes the id. App Privacy: Product Interaction and Device
ID, Analytics, linked, not tracking. No IDFA, no ATT prompt, no ads.
