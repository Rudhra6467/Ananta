# Ananta Mobile Workspace — Compiled Prompt (Account/Privacy overlay + Parity)

Paste the whole block below into the external Ananta mobile workspace agent.

---

## BACKGROUND
Ananta.AI is a cross-platform algorithmic crypto-trading app: a React web app + this Expo/React Native
mobile app, both talking to ONE shared FastAPI backend. The web version is the design + behavior source
of truth. We are preparing the mobile app for App Store submission. To satisfy the App Store privacy
requirement WITHOUT an external privacy URL, we surface account + privacy info INSIDE the app via an
"Account" overlay opened from the Ananta logo. The web app already ships this (verified); mobile must match.

## 1. ANANTA LOGO BUTTON (trigger)
- The Ananta logo in the top-left of the Cockpit header must be a real, tappable button.
- Give it an interactive feel: pressed state (subtle opacity/scale change), hitSlop for easy tapping.
- On press → open the Account overlay (a modal route). testID: `account-logo-btn`.
- Implementation: wrap `<Logo/>` in a `Pressable` with `onPress={() => router.push('/account')}`; register
  `app/account.tsx` in the root `_layout.tsx` Stack with `presentation:'modal'`.

## 2. ACCOUNT / PRIVACY OVERLAY (app/account.tsx)
Layout (top → bottom), mirroring the web overlay:
- **Header:** title "Account" + a close (X) button (`account-close-btn`, `router.back()`).
- **Profile header** (`account-profile-header`): circular avatar with the email's first 2 letters as
  initials, "Ananta Owner", the real email (`account-email`), and an auth-status badge
  (`account-auth-status`): "AUTHENTICATED" (green) when logged in, else "READ-ONLY".
- **Login & Auth card** (ONLY real data this sprint):
  - Email row (`account-cred-email`) = the real logged-in email.
  - Password row (`account-cred-password`) = MASKED bullet dots `••••••••••` (NEVER the real password).
  - Authentication row = "Secure token (JWT)".
- **Invite banner** (`account-invite-banner`): static placeholder ("Invite friends / earn a bonus").
- **Features section** (visual placeholders, each a row with icon + label + right-side pill + chevron;
  pill text "Soon" except Exchange which shows "Kraken"):
  `account-feature-exchange` (Exchange Connection), `account-feature-referrals` (Referrals),
  `account-feature-offers` (Offers), `account-feature-earn` (Earn), `account-feature-tax` (Tax reporting).
- **Settings section** (placeholders, "Soon" pills): `account-setting-payments` (Payment methods),
  `account-setting-notifications` (Notifications), `account-setting-privacy` (Privacy & Security).
- **Privacy statement** (`account-privacy-note`) — REQUIRED for App Store privacy info. Use this copy:
  "Ananta stores only your account email and an encrypted authentication token to keep you signed in.
   We do not sell personal data. Trading is executed via your own exchange keys, which are stored
   securely and never shared."
- **Log out** (`account-logout-btn`, owner only): calls `logout()` then `router.replace('/login')`.
- Build with theme tokens (see parity below) so it inherits the app theme; all touch targets ≥44pt.

## 3. CORRECTIONS / DEFINITION OF DONE
- Logo MUST visibly react to touch (not a static image) and MUST open the overlay.
- Password MUST be masked; do not fetch or render a real password.
- Placeholder rows must not dead-end: an onPress no-op is fine, but keep the "Soon" pill so intent is clear.
- Overlay must render cleanly in the dark theme (no unstyled/overflowing content, safe-area aware).

## 4. MOBILE DESIGN PARITY (align mobile `src/theme.ts` to web — currently diverged)
Replace the teal/blue-black tokens with the web matte-black / matte-silver palette:
```
bg #090A0C · card #121418 · cardPressed #1A1D24 · border #2A2D35
text #E2E4E9 · textMuted #878E99 · textFaint #5C6370
accent #C0C5CE (MATTE SILVER, not teal) · positive #10B981 · negative #F43F5E · warning #D9B36B
radius sm4/md6/lg8 · P&L: >=0 emerald, <0 rose
```
Fonts via expo-font: Chivo (headings), IBM Plex Sans (body), JetBrains Mono (all numbers/tickers/labels).
Labels: JetBrains Mono, 10px, weight 700, letterSpacing 0.2em, UPPERCASE, color #878E99.

## 5. BACKEND CONTRACT (shared — no backend changes; just call these)
Base `${EXPO_PUBLIC_BACKEND_URL}/api`, Bearer token key `ananta_owner_token`.
- Auth: `POST /auth/login {email,password}` -> `{token,email,role}`; `GET /auth/me`; `POST /auth/logout`.
- The overlay needs NO new endpoints — email/role come from the existing auth context (`useAuth().owner`).
- (Separate parity task) add the missing Research-Lab endpoints to `src/api.ts`:
  `/lab/data/coverage`, `/lab/presets`, `POST /lab/runs` (new body fields `strategies:string[]`,
  `compare_timeframes:boolean` default false), `/lab/runs`, `/lab/runs/{id}`, `/lab/runs/{id}/pdf`,
  `/lab/runs/{id}/propose`, `/lab/proposals`; plus research: `/research/summary`, `/research/rejections`,
  `/research/winner_profile`, `/research/missed_opportunities`, `/research/rsi_distribution`,
  `/research/zone_effectiveness`, `/research/staged_exit`, `/research/log`.

## 6. VERIFY
- Tap logo -> overlay opens; email + AUTHENTICATED badge show when logged in.
- Password masked; privacy note visible; Features/Settings rows render with "Soon" pills.
- Close + Log out work. Theme matches matte-black/silver with the 3 custom fonts.
