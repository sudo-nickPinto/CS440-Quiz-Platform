# Quiz Platform: Design Guide

How to build new pages that match the Quiz Platform mockups.

**Sources of truth** (both in the same folder as this guide):

| File | What it defines |
|---|---|
| `landing-main.html` | The **current palette** (softened, September 30, 2026), the black title-bar treatment, line weights, the scrolling landing layout, and the inline sign-in. |
| `made-dashboard-main.html` | The **app shell and data patterns**: tabs, toolbar, filter popover, data list, row menu. Moved onto the softened palette on September 30, 2026; the previous version is `old/made-dashboard-main-v1.html`. |

Every class name, color, and size in this guide comes from those two files. If this guide and a file disagree, the file wins; update this guide.

**Open them first.** Open both files in a browser, resize to phone width, and click everything: on the landing page, Sign in (then ×/Esc), the chapter rail, and the header links; on the dashboard, the tabs, `+`, Join, search, Filter, and `⋯`. Both mockups are plain HTML, CSS, and JS running on fake data, so the patterns carry straight over to React.

> **Status:** The softened palette and the rules in §2 were chosen by Taha on September 30, 2026. The tints and deep orange were nudged slightly more saturated the same day. The team has not signed off on them yet. Bring token changes to the team before changing them again.

---

## 1. The style in one paragraph

**Soft neo-brutalism with Gettysburg colors.** Everything is a flat, solid block with a **dark ink border** and a **hard offset shadow** (no blur). Corners are square. Headings are chunky. The page is **calm**: big areas use warm paper, sand, pale sky, and apricot, while **full-strength navy and orange only appear on small pieces** (buttons, timers, selected states, rank numbers). Black shows up as **thin title bars**, never as big blocks. Color carries meaning and is not decoration.

If a new element could be described as "soft-cornered," "blurry," or "floating," it's off-style. If it could be described as "loud," "glaring," or "screaming," it's also off-style: tone it down to a tint.

---

## 2. Design tokens

All tokens are CSS custom properties in `:root`. **Always use the variable, never the raw hex.**

### 2.1 Colors

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#fcf9f4` | **Surfaces** (the main frame, cards, inputs, menus). Replaces pure white, which caused glare. |
| `--sand` | `#ecdfd0` | **Page background**, rail background, card footers, and neutral fills. |
| `--sky-soft` | `#c2e6f8` | **Main soft fill**: headline highlight, the device band, the closing CTA section, marked-correct answers, input suffixes, joined-student chips. |
| `--apricot` | `#f6d2b6` | **Second soft fill**, the warm partner to pale sky: alternating chapters and card headers. Also the text color for right-hand labels on black title bars. |
| `--navy` | `#043371` | Gettysburg blue. **Small structural pieces only**: logo block, selected options (picked answer, chosen class, 20s timer), eyebrow text, links, toast. |
| `--orange-deep` | `#bf4c0c` | Gettysburg orange for **filled blocks**: primary buttons, timers, rank blocks, the selected Present tab, the big chapter number, "correct" labels, focus outline. White text on it is about 4.9:1, so keep that text bold. |
| `--orange` | `#CC4E00` | Brand orange, used **only as the hover state** of `--orange-deep` buttons. |
| `--ink` | `#222222` | Text, **every border**, every hard shadow, and the **black title bars**. |
| `--gray` | `#666666` | Secondary text: meta lines, fine print, chapter eyebrows. At least 4.5:1 on paper. |
| `--sky` | `#8fdbff` | Bright sky. **Only** the dot in the `QUIZ.PLATFORM` logo. Never a fill. |

Retired tokens: `--white` `#ffffff`, `--alabaster` `#F5F5F5`, `--sapphire` `#043B82`, `--cornflower` `#84BAFF`, and the old sand `#f3ebe2`. They survive only in `old/`; don't use them.

### 2.2 Color rules

These are the rules that fixed the eye strain. Follow them on every page.

1. **Big areas get tints; strong colors stay small.** Any area bigger than a button (panels, bands, sections) uses `--paper`, `--sand`, `--sky-soft`, or `--apricot`. Full navy and orange fill only small pieces. **One exception:** the dashboard's selected tab is solid (Present deep orange, Participate navy), because it's the main "you are here" signal.
2. **Orange never touches blue.** A deep-orange block must not share an edge with navy or pale sky; keep an ink border or neutral paper between them. Orange next to black or apricot is fine.
3. **Pale sky and apricot take turns.** Alternate them across sections (hero band sky, chapters alternate paper and apricot, CTA sky) so the page has rhythm without getting loud.
4. **Black is for title bars.** Use `--ink` as a fill only for thin label strips: panel headers, the classroom-screen title bar, the sign-in card header, and the dashboard's table header row. Never as a section background, and never as a full-width band between sections (that reads as a heavy border). The row menu's "Publish to…" label stays **navy**, not black.
5. **Text on color:** white/paper text goes on `--orange-deep`, `--navy`, and `--ink`. Navy or ink text goes on the tints. Labels on black bars are paper on the left, apricot on the right.
6. **Status colors** (dashboard): Draft = pale sky with navy text, Published = navy with paper text, Rank = deep orange with paper text. Don't invent new status colors without the team.
7. Check any new pairing with [WebAIM's contrast checker](https://webaim.org/resources/contrastchecker/). Gettysburg requires **4.5:1 or better**.

### 2.3 Typography

Load both fonts from Google Fonts (already in each mockup's `<head>`):

```html
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
```

| Role | Font | Size / weight | Example |
|---|---|---|---|
| Hero headline | **Archivo Black** | `clamp(38px, 5.4vw, 76px)`, `line-height: 1.22`, `letter-spacing: -1.5px` | `Ask the room.` |
| Section headline (`h2`) | Archivo Black | `clamp(28px, 3.6vw, 46px)`; chapters `clamp(26px, 3vw, 38px)` | `Write it like a slide.` |
| Display bits | Archivo Black | Dashboard tabs `clamp(16px, 2.2vw, 28px)` uppercase · Row titles `20px` · Timers/numbers `16–26px` · Chapter number `96px` | `PRESENT`, `0:12`, `01` |
| Body / UI | **Space Grotesk** | `16–18px`, weight `500`, or `700` for UI | lede, buttons, inputs |
| Labels / eyebrows | Space Grotesk 700 | `11–13px`, **uppercase**, `letter-spacing: 1px` | `GETTYSBURG USERNAME`, `CHAPTER 01` |
| Meta / fine print | Space Grotesk 500 | `12–13px`, `--gray` | `Google asks for your password.` |

Rules:
- Archivo Black has only one weight. Set `font-weight: 400`, or the browser fakes a bold.
- Small labels are always uppercase with letter spacing; titles are not.
- **Headline highlight:** the key phrase of a headline sits in a `.hl` box (`--sky-soft` background, navy text, 3px ink border, `box-decoration-break: clone` so wrapped lines each get a box). Use one per headline at most. Card titles can color one word `--orange-deep` instead ("Pull up a **seat.**").

### 2.4 Borders, shadows, spacing

| Token / value | Use |
|---|---|
| `--b` = `3px solid var(--ink)` | **Major lines**: the frame, section dividers, cards, panels, buttons, inputs. |
| `--b-thin` = `2px solid var(--ink)` | **Inner lines**: between chapters, inside cards (rows, option chips, footers), tags, small squares. |
| `--shadow` = `6px 6px 0 var(--ink)` | Frame, panels, big cards. Sign-in cards use `8px 8px 0`. |
| `4px 4px 0 var(--ink)` | Primary buttons, the logo, the toast. |
| `3px 3px 0 var(--ink)` | Secondary controls: header Sign in, inputs, Google button, small buttons. |
| Page padding | Landing: `0 24px 26px` (phones `0 10px 14px`). Dashboard: `20px 24px 26px` (phones `12px 10px 14px`). |
| Section padding (`.wrap`) | `clamp(40px, 6vw, 84px) clamp(18px, 4vw, 48px)`, `max-width: 1180px`, centered. |
| Header height | `--head-h: 78px` (phones `64px`). |

- **Shadows are ink only.** The old orange and sky shadows (logo, buttons, search) are retired, because a colored shadow next to a colored block creates the orange-on-blue buzz.
- Keep lines thin between areas. A section change is one 3px line, not a thick strip.
- **Never** use `border-radius`, blurred `box-shadow`, or gradients (except the stripe texture below).

**How the dashboard was moved to this palette** (use the same mapping for any older page): `--white` → `--paper`; old sand → `#ecdfd0`; `--sky` fills (Draft status, `+`, Filter button, hovers) → `--sky-soft`; small `--orange` fills (count, rank, Shared tag, avatar, score bar) → `--orange-deep`; `--alabaster` (ME tag, tab hover, stripes) → `--sand`; gray → `#666666`; every colored shadow → an ink shadow; row and status dividers → 2px. **Selected tabs** stay solid, like the original: Present is deep orange and Participate is navy, both with paper text and a 4px underline. The **Join** button stays navy and hovers to ink. The row menu's "Publish to…" label stays navy.

### 2.5 Textures

There's one texture: the **diagonal stripes** behind the dashboard toolbar and filter strips.

```css
background: repeating-linear-gradient(45deg, var(--paper), var(--paper) 10px, var(--sand) 10px, var(--sand) 20px);
```

Use it for control strips only, never behind content.

---

## 3. Page skeletons

There are two skeletons. **App pages** use the fixed frame; the **landing page** scrolls.

### 3.1 App pages (dashboard, lobby, results): fixed frame

A header on top, then **one bordered frame that fills the rest of the screen**. Inside the frame, the top strips stay fixed and **only the content region scrolls**.

> **Draft exception (October 6, 2026):** the quiz editor, host live view, and both results pages (`*-v2.html`) let the frame grow and the **page** scroll, so no bordered panel has its own scrollbar. If the team accepts this, it replaces the fixed frame for those pages; the dashboard still uses the fixed frame.

```html
<body>
  <header class="top">
    <div class="logo">QUIZ<span>.</span>PLATFORM</div>
    <div class="user"><span class="name">Taha Sabir</span><div class="avatar">TS</div></div>
  </header>
  <div class="frame">
    <nav class="tabs">…</nav>          <!-- optional -->
    <div class="toolbar">…</div>       <!-- optional -->
    <div class="list">…</div>          <!-- the scrolling region -->
  </div>
  <div class="toast" id="toast"></div>
</body>
```

```css
html, body { height: 100%; }
body  { display: flex; flex-direction: column; }
.frame { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.list  { flex: 1; overflow-y: auto; }
```

`min-height: 0` on `.frame` is what lets the inner list scroll instead of stretching the page. **Don't remove it.**

### 3.2 Landing page: scrolling frame with sticky header

The landing page is the one exception: the whole page scrolls.

```html
<header class="top">                <!-- position: sticky; top: 0; background: var(--sand) -->
  <a class="logo" href="#top">QUIZ<span>.</span>PLATFORM</a>
  <nav class="nav">…section links…</nav>
  <button class="signin-top" data-signin>Sign in</button>
</header>
<main class="frame" id="top">
  <section class="hero">…</section>
  <section class="chapters" id="how">…</section>
  <section id="who">…</section>
  <section class="cta">…</section>
</main>
<footer>…</footer>
```

- Sections stack inside one frame, split by `.frame > section + section { border-top: var(--b); }`.
- Section backgrounds follow the rhythm in §2.2: hero paper, then the device band in pale sky, chapters alternating paper and apricot, "Who it's for" paper, and the CTA in pale sky.
- The header nav links hide under 1150 px.

> The product name is still TBD (see the SRS). `QUIZ.PLATFORM` is a placeholder; keep the `<span>` around the dot.

---

## 4. Components

Copy the CSS for any component you use from the file listed next to it.

### Shared

**Header: `.top`, `.logo`, `.signin-top`, `.avatar`** (both files)
- The logo is a navy block tilted `-1.5deg` with a **4px ink shadow**. It's the **only** rotated element; don't tilt anything else. (Offset stacks of cards use `translate`, not rotation.)
- Logged out: a paper `.signin-top` button (navy text, ink shadow). While sign-in is open it turns ink with paper text and looks pressed (`aria-expanded="true"`).
- Logged in: the avatar, a 44px `--orange-deep` square with initials. On phones, the user's name is hidden.

**Panel with black title bar: `.panel`, `.panel-top`, `.panel-body`** (`landing-main.html`)
The standard way to show a piece of the app inside a page.
```html
<div class="panel">
  <div class="panel-top"><span>Lobby · CS 216</span><span>Waiting</span></div>
  <div class="panel-body">…</div>
</div>
```
`.panel-top` is ink with 12px uppercase paper text; the right-hand label is apricot. The body uses 2px inner lines.

**Primary button: `.btn`, `.go-btn`** (`landing-main.html`)
Deep orange, paper text, 3px border, `4px 4px 0` ink shadow; hover goes to `--orange`. Only one per panel.

**Buttons, all kinds**

| Kind | Look | When |
|---|---|---|
| Primary | Deep orange, ink shadow | The one main action (Sign in with Gettysburg, Continue, Start →) |
| Secondary | Paper with ink shadow (`.signin-top`, `.g-btn`), hover `--sky-soft` | Header sign-in, alternate options |
| Text link | Navy, 2px underline, hover underline turns deep orange (`.g-link`) | Low-priority alternates ("Or pick a Google account") |
| Structural (dashboard) | Navy block (`.join`) | Top-level actions in the tab bar |
| Row action (dashboard) | Paper with ink shadow (`.kebab`) | Actions on a single row |
| Option chip | `.opt` / `.opt.on` (navy when on) | Choices inside popovers and pickers |

**Press state:** move the button by its shadow size and drop the shadow (`transform: translate(4px,4px); box-shadow: none;`), so it feels like pushing a block.

**Toast: `.toast`** (both files)
A navy bar at the bottom center with a 4px ink shadow, for quick confirmations. It shows for 1.8s; call `toast("message")`.

### Landing page (`landing-main.html`)

**Hero: `.hero-top`, `.hl`, `.hero-side`**
The eyebrow, then a two-line headline with the highlight box, then a row with the lede on the left and the primary button on the right. On desktop (over 1150 px) the hero is held at `min-height: 490px`: the headline is centered in its row and the lede/button sit at the top of theirs, which gives the roomier spacing. Under 1150 px it's a normal stack.

**Device band: `.devices`, `.screen`, `.phone`**
A pale-sky band showing the classroom screen (black title bar with a deep-orange timer) next to a phone. The phone's picked answer is navy. On phones the big screen is hidden.

**Chapter rail: `.chapters`, `.rail`, `.chapter`**
A sticky left rail (sand) with the big deep-orange chapter number, the chapter title, and four square markers: current is deep orange, done is ink, upcoming is paper. JS updates it as chapters cross the middle of the screen. Chapters alternate paper and apricot and are split by 2px lines. Under 1150 px the rail becomes a sticky bar under the header.

**Inline sign-in: `.login-card`** (the landing page's way to sign in; there is no separate login page)
- Every sign-in trigger has `data-signin` and `aria-controls="loginCard"`.
- **Opening:** the eyebrow and headline scale down as one piece, anchored top-left, and move to the left center; JS picks a scale between 0.45 and 0.82 so the headline fits beside the card. The lede and button fade out. The card glides in from the right, and its parts fade up one after another. The eyebrow text changes to "Sign in · Gettysburg accounts only".
- **Closing:** ×, Esc, or the header button reverses it and returns focus. `#signin` in the URL opens it directly.
- **Motion is transform and opacity only.** Never animate `font-size`, grid columns, or height on a headline; text re-wraps every frame and looks broken.
- The card is absolutely positioned inside `.hero-top`, so it never changes the closed layout.
- Under 1150 px the card replaces the lede and button below the headline. With `prefers-reduced-motion` everything switches instantly.

**Gettysburg username field: `.user-field`**
```html
<label class="lbl" for="user">Gettysburg username</label>
<div class="user-field"><input id="user" autocomplete="username" placeholder="yourname"><span>@gettysburg.edu</span></div>
<p class="err" role="alert"></p>
```
The `@gettysburg.edu` suffix is fixed in a pale-sky cell. Sign-in is identifier-first: the username goes to Auth0 as a login hint and **Google asks for the password**. There is never a password field. Show errors in deep orange under the field (another domain, empty, invalid characters), and accept a full `@gettysburg.edu` address typed into the field.

**Who cards and CTA: `.who-card`, `.cta`**
Two cards with tinted headers (apricot, pale sky), then a pale-sky CTA band with a headline and the primary button.

### App shell (`made-dashboard-main.html`)

**Tab bar: `.tabs`, `.tab`, `.plus`, `.join`**
Switches between sibling views (Present / Participate).
```html
<nav class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true"  data-tab="present">Present</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="participate">Participate</button>
  <button class="plus" title="New quiz">+</button>
  <button class="join">Join</button>
</nav>
```
- Tabs split the width equally; action buttons size to their content.
- The selected tab is driven by **`aria-selected="true"`**, not a class. It's solid with paper text and a 4px underline: deep orange for Present, navy for Participate. Unselected tabs hover to sand.
- Drop `.plus`/`.join` on pages without a primary action and adjust `grid-template-columns`.
- Taha rejected switching between Present and Participate inside a lobby. Presenter and participant lobbies are separate pages.

**Toolbar: `.toolbar`, `.search`, `.filterbtn`, `.pop`, `.opt`, `.count`**
The standard "find stuff" strip. **Keep it to one line at every screen size.**
- Search takes the leftover width, and it filters as you type (no Search button).
- **Filters and sort go in the Filter popover, never as dropdowns in the strip.**
- Add `<span class="dot"></span>` inside `.filterbtn` when a filter or sort isn't at its default.
- `.count` shows how many results are visible.

**Data list: `.list`, `.head`, `.row`, cells**
A table built with CSS grid where **the header and rows share one `grid-template-columns`**.

| Piece | Purpose |
|---|---|
| `.head` | Black header row that sticks to the top of `.list` (the original black title bar). Rows below it are split by 2px lines. |
| `.status` + `draft` / `published` / `rank` | Full-height colored first column that always includes the word |
| `.title strong` | Row title in Archivo Black; hover underlines it in orange |
| `.meta` | Gray summary line; hidden on desktop, shown on tablet and phone |
| `.cell` / `.cell.dim` | Normal cell / gray bold cell for numbers and dates |
| `.tag` / `.tag.me` | Small bordered label |
| `.score` + `.bar` | Big `9/10` with a small progress bar |
| `.kebab` | The `⋯` row-actions button (`→` for rows that just open) |

Mark columns `.mid` (hidden on phones) or `.wide` (hidden on tablets and phones), or leave them unmarked (always visible).

**Row menu: `.menu`**
Opens from `⋯`. Sections are split by a **navy** `.sub-label` ("Publish to…"), and indented `.class-opt` options hover to apricot. It's positioned with `position: fixed` so the list never clips it, flips upward near the bottom, and closes on outside click or scroll. Reuse `openMenu()`.

**Inline panel: `.join-panel`**
A pale-sky strip that opens under the tab bar for one-field tasks like a session code; use it instead of a modal. It has a black `SESSION CODE` label chip, a paper input with an ink shadow, and a deep-orange **GO →** button.

**Empty state: `.empty`**
Centered bold text that tells the user what to do: `Nothing here. Hit + to make a quiz.` or `No quizzes match "sql".`

**Scrollbars: never the browser default**
Avoid scrolling boxes inside bordered panels: let the page scroll, and make text areas grow with their content. Anything that still scrolls uses this block (thin square ink thumb, sand page track, no arrow buttons). Keep the standard `scrollbar-*` properties inside the `@supports` wrapper: in Chrome they override the `::-webkit-scrollbar` rules and bring the arrow buttons back.

```css
@supports not selector(::-webkit-scrollbar){
  html{scrollbar-width:thin;scrollbar-color:var(--ink) var(--sand)}
  *{scrollbar-width:thin;scrollbar-color:var(--ink) transparent}
}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
html::-webkit-scrollbar,html::-webkit-scrollbar-track,
body::-webkit-scrollbar,body::-webkit-scrollbar-track{background:var(--sand)}
::-webkit-scrollbar-thumb{background:var(--ink);border:3px solid transparent;background-clip:content-box}
::-webkit-scrollbar-button{display:none;width:0;height:0}
::-webkit-scrollbar-corner{background:transparent}
```

---

## 5. Responsive rules

Phones are the **primary** device (SRS §4.1), so check phone width first.

| Width | What changes |
|---|---|
| **> 1150px** (desktop) | Landing: header nav visible, 490px hero, side-by-side inline sign-in, sticky side rail. Dashboard: all columns, `.meta` hidden. |
| **≤ 1150px** (tablet) | Landing: nav hidden, rail becomes a sticky top bar, chapters stack, sign-in card drops below the headline. Dashboard: `.wide` columns hidden, `.meta` shown. |
| **≤ 640px** (phone) | Smaller page padding and logo, full-width primary buttons, the classroom screen hidden in the device band, compact rail markers. Dashboard: `.head` and `.mid` hidden, grid becomes `status · title · action`, popover spans full width. |

Rules:
- **Nothing may overflow sideways at 360px.** Test at 360 and 390 wide.
- Form grids need `grid-template-columns: minmax(0, 1fr)`, and inputs inside flex rows need `min-width: 0; width: 100%`, or they push the layout wider on phones.
- If text gets cut off on phones, shorten the label before shrinking the font.
- Keep touch targets around **40px tall**; 38px (`⋯`) is the minimum.

---

## 6. Interaction and motion

- **One source of state, re-render the region.** In React this is `useState`.
- **Search filters as the user types.**
- **Everything that opens also closes** on outside click and Esc. Popovers and menus also close when their list scrolls.
- **Give feedback for every action** with a toast or a visible state change. Loading buttons show text such as "Opening Google…" and set `aria-busy="true"`.
- Switching tabs resets sort to its default and closes any open popover.
- **Motion:** animate `transform` and `opacity` only. Use `cubic-bezier(.22, 1, .36, 1)` for things arriving, and quick fades (0.2–0.3s) for things leaving. Stagger small groups by about 50ms. Every animation needs a `prefers-reduced-motion` fallback that switches instantly.

---

## 7. Accessibility

- [x] **Focus styles:** `:focus-visible { outline: 3px solid var(--orange-deep); outline-offset: 2px; }` is in both mockups; the dashboard search box shows it with `:focus-within`.
- [ ] Icon-only buttons get an `aria-label`: `⋯` → `Quiz actions`, `+` → `New quiz`, `×` → `Close sign-in`.
- [ ] Tabs use `role="tablist"` / `role="tab"` / `aria-selected`.
- [ ] Triggers for popovers, menus, and the sign-in card set `aria-expanded` and `aria-controls`. Closed panels are `inert`. Esc closes, and focus returns to the trigger.
- [ ] Error messages use `role="alert"`; toasts use `role="status"` with `aria-live="polite"`.
- [ ] Decorative mockups inside pages (device band, panels) get `aria-hidden="true"`.
- [ ] Clickable rows must work from the keyboard (a real `<button>` or link inside the row).
- [ ] Never rely on color alone: status blocks always include the word (`DRAFT`, `PUBLISHED`).

---

## 8. Moving this into React

The SRS stack is **React + FastAPI**. When porting:

1. Put the `:root` tokens (§2.1) and the shared component CSS in one global stylesheet (e.g. `src/styles/theme.css`) and import it once. **Don't copy tokens into individual components.**
2. Put the Google Fonts `<link>` in `index.html`.
3. `class` → `className`. Keep the **same class names** so this guide stays accurate.
4. Replace the mockups' `innerHTML` template strings with JSX. **Never build HTML strings from real user data** (quiz titles, names); JSX escapes text for you.
5. Pull out reusable components: `<Header>`, `<Panel title right>`, `<PrimaryButton>`, `<UsernameField>`, `<InlineSignIn>`, `<ChapterRail>`, `<TabBar>`, `<Toolbar>`, `<FilterPopover>`, `<DataList>`, `<RowMenu>`, `<StatusCell>`, `<Toast>`.
6. Wire `<InlineSignIn>` to Nick's Auth0 flow: pass `login_hint: username + "@gettysburg.edu"` and restrict to the Gettysburg Google connection. The UI never collects a password.
7. Replace the fake data (`MADE`, `PART`, `CLASSES`, demo names and scores) with API calls.

---

## 9. Do / Don't

| Do | Don't |
|---|---|
| Paper, sand, pale sky, and apricot for big areas | Pure white surfaces or large saturated fills |
| Full navy/orange on small pieces only | Big navy panels or big orange tabs |
| Keep orange and blue apart with an ink border or neutral gap | Orange blocks touching navy or pale sky |
| Black for thin title bars | Black section backgrounds or thick black bands |
| 3px for major lines, 2px inside | 3px everywhere, or thin gray borders |
| Ink hard shadows (`6px 6px 0`) | Colored or blurred shadows |
| Square corners | `border-radius` |
| Page scroll, or the shared thin ink scrollbar (§4) | Default browser scrollbars inside bordered panels |
| Transform/opacity animations with a reduced-motion fallback | Animating font-size, grid columns, or height |
| Username field + Google hand-off | A password field |
| Test at 390px first, then 360 | Designing desktop-only |

---

## 10. New-page checklist

- [ ] Uses the right skeleton: fixed frame for app pages, scrolling frame for the landing page (§3)
- [ ] Only token colors (`var(--…)`), no raw hex, and no retired tokens (`--white`, `--sky` fills)
- [ ] Big areas are tints; navy and orange only on small pieces; orange never touches blue (§2.2)
- [ ] Black only as thin title bars
- [ ] Archivo Black for display text, Space Grotesk for everything else
- [ ] 3px major lines, 2px inner lines, ink hard shadows, no rounded corners
- [ ] Works at 1440, 1000, 390, and 360 wide with no sideways scrolling
- [ ] No default browser scrollbars: no scrolling boxes inside panels, otherwise the shared scrollbar block (§4)
- [ ] Empty states written, every action gives feedback, loading states set `aria-busy`
- [ ] Focus outlines, `aria-label`s, `aria-expanded`, Esc-to-close, and keyboard access (§7)
- [ ] Motion is transform/opacity only, with a reduced-motion fallback
- [ ] Checked side by side against `landing-main.html` and `made-dashboard-main.html`

Questions or want to change a token? Bring it to the team first so every page stays consistent.
