# Quiz Platform: Design Guide

How to build new pages that match the "Made" dashboard.

**Source of truth:** `made-dashboard-main.html` (in the same folder as this guide). Every class name, color, and size in this guide comes from that file. If this guide and the file ever disagree, the file wins; update this guide.

**Open it first.** Open the file in a browser, resize the window down to phone width, and click everything (tabs, `+`, Join, search, Filter, `⋯`). The mockup runs on fake data in plain HTML, CSS, and JS, so the patterns carry straight over to React.

---

## 1. The style in one paragraph

**Neo-brutalism with Gettysburg colors.** Everything is a flat, solid block with a **thick black border** and a **hard offset shadow** (no blur). Corners are square. There are no gradients, except the one diagonal-stripe texture on toolbars. Headings are chunky and often uppercase. Color carries meaning (status, active state, primary action) and is not used as decoration. The page always fills the whole screen, and only the list area scrolls.

If a new element could be described as "soft," "rounded," "subtle," or "floating," it's probably off-style.

---

## 2. Design tokens

All tokens are CSS custom properties in `:root`. **Always use the variable, never the raw hex.**

### Colors

| Token | Hex | Where it's used |
|---|---|---|
| `--navy` | `#043371` | Gettysburg blue. Structure and primary actions: logo, **Join** button, `Published` status, class names, menu section labels, toast |
| `--orange` | `#CC4E00` | Gettysburg orange. **Active or selected** state and emphasis: selected tab (Present), counts, rank block, `Shared` tag, search/filter shadow |
| `--sky` | `#8fdbff` | Secondary actions and light accents: **+** button, Filter button, `Draft` status, hover fill on white controls |
| `--sand` | `#f3ebe2` | Page background, and nothing else |
| `--ink` | `#222222` | Text, **every border**, every hard shadow, table header row |
| `--white` | `#ffffff` | Surfaces: the main frame, rows, inputs, menus, popovers |
| `--gray` | `#747474` | Secondary text: meta lines, dim cells, popover section labels, "Not published" |
| `--sapphire` | `#043B82` | Selected **Participate** tab, hover on Join |
| `--cornflower` | `#84BAFF` | Hover on the sky **+** button |
| `--alabaster` | `#F5F5F5` | Hover on white tabs, the "ME" tag, the second color in the stripe texture |

**Color rules**
- **Orange means "this is selected / this is the number you care about."** Don't use it for decoration.
- **Navy means "structure or main action."**
- **Sky means "secondary action" or "light status."**
- Status colors are fixed: **Draft = sky with navy text**, **Published = navy with white text**, **Rank = orange with white text**. Don't invent new status colors without talking to the team first.
- Text on orange must be **white and bold**. That pairing sits right at the WCAG AA 4.5:1 limit, so don't use it for small, thin text.
- Check any new pairing with [WebAIM's contrast checker](https://webaim.org/resources/contrastchecker/). Gettysburg requires **4.5:1 or better**.

### Typography

Load both fonts from Google Fonts. This line is already in the mockup's `<head>`:

```html
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
```

| Role | Font | Size / weight | Example |
|---|---|---|---|
| Display (tabs, logo, row titles, big numbers) | **Archivo Black** | Tabs `clamp(16px, 2.2vw, 28px)` uppercase · Row titles `20px` (`17px` on phones) · Numbers `22px` | `PRESENT`, `Quiz 1 — Big-O Warmup`, `9/10` |
| Body / UI | **Space Grotesk** | `16px`, weight `500` (normal) or `700` (bold UI) | inputs, buttons, cells |
| Labels / eyebrows | Space Grotesk 700 | `11–13px`, **uppercase**, `letter-spacing: 1px` | `STATUS`, `SORT BY`, `PUBLISH TO…` |
| Meta text | Space Grotesk 500 | `13px`, `--gray` | `8 questions · edited 2026-09-26` |

Rules:
- Archivo Black has only one weight. When you use it, set `font-weight: 400`, or the browser will fake a bold version.
- Small labels are always uppercase with letter spacing. Titles are not.

### Borders, shadows, spacing

| Token / value | Use |
|---|---|
| `--b` = `3px solid var(--ink)` | Default border for **everything**: frame, rows, buttons, inputs, menus |
| `2px solid var(--ink)` | Small things only: tags, filter option chips, score bar, menu dividers |
| `--shadow` = `6px 6px 0 var(--ink)` | Big surfaces: the main frame, menus, popovers |
| `3px 3px 0 <color>` | Controls: `--navy` for `⋯` buttons and selects, `--orange` for search/filter, `--ink` for the avatar |
| `4px 4px 0 var(--orange)` | Logo and toast |
| Page padding | `20px 24px 26px` (phones: `12px 10px 14px`), gap `18px` (phones `12px`) |
| Cell padding | `12px 16px` |
| Toolbar padding | `12px 16px` (phones `10px`), gap `12px` |
| Row min-height | `72px` |

**Never** use `border-radius`, blurred `box-shadow`, or `opacity` fades on surfaces.

### Textures

There's one texture: the **diagonal stripes** behind toolbars and filter strips.

```css
background: repeating-linear-gradient(45deg, var(--white), var(--white) 10px, var(--alabaster) 10px, var(--alabaster) 20px);
```

Use it for "control strip" areas only, never behind content.

---

## 3. Page skeleton

Every page uses the same shell: a header on top, then **one bordered frame that fills the rest of the screen**. Inside the frame, the top strips stay fixed and **only the content region scrolls**.

```html
<body>
  <header class="top">
    <div class="logo">QUIZ<span>.</span>PLATFORM</div>
    <div class="user"><span class="name">Taha Sabir</span><div class="avatar">TS</div></div>
  </header>

  <div class="frame">
    <nav class="tabs">…</nav>          <!-- optional: section switcher -->
    <div class="toolbar">…</div>       <!-- optional: search / filter / count -->
    <div class="list">…</div>          <!-- the scrolling content region -->
  </div>

  <div class="toast" id="toast"></div>
</body>
```

The CSS that makes it full-screen (already in the mockup):

```css
html, body { height: 100%; }
body  { display: flex; flex-direction: column; }
.frame { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.list  { flex: 1; overflow-y: auto; }
```

`min-height: 0` on `.frame` is what lets the inner list scroll instead of stretching the page. **Don't remove it.**

> The product name is still TBD (see the SRS). `QUIZ.PLATFORM` is a placeholder; keep the `<span>` around the dot so it stays sky blue.

---

## 4. Components

Class names below match the mockup exactly. Copy the CSS for any component you use from the `<style>` block in `made-dashboard-main.html`.

### Header: `.top`, `.logo`, `.avatar`
- The logo is a navy block tilted `-1.5deg` with an orange shadow. It's the **only** rotated element; don't tilt anything else.
- The avatar is a 44px orange square with the user's initials.
- On phones, the user's name (`.user .name`) is hidden.

### Tab bar: `.tabs`, `.tab`, `.plus`, `.join`
Use it for switching between sibling views on the same page (like Present / Participate).

```html
<nav class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true"  data-tab="present">Present</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="participate">Participate</button>
  <button class="plus" title="New quiz">+</button>
  <button class="join">Join</button>
</nav>
```

- Tabs split the width equally. Action buttons (`.plus`, `.join`) sit at the right and size to their content.
- The selected tab is driven by **`aria-selected="true"`**, not a class. It turns orange (or sapphire for Participate) and gets a thick underline.
- Every tab has a border on its right edge except the last one.
- If a page has no primary action, drop `.plus`/`.join` and change `grid-template-columns` to match the number of tabs.

### Toolbar: `.toolbar`, `.search`, `.filterbtn`, `.pop`, `.opt`, `.count`
This is the standard "find stuff" strip. **Keep it to one line at every screen size.**

```html
<div class="toolbar">
  <div class="search"><span>⌕</span><input placeholder="Search quizzes…"></div>
  <div class="filter-wrap">
    <button class="filterbtn">Filter ▾</button>
    <div class="pop">
      <h4>Show</h4>
      <div class="opts"><button class="opt on">All</button><button class="opt">Owned</button></div>
      <h4>Sort by</h4>
      <div class="opts"><button class="opt on">Last edited</button><button class="opt">A → Z</button></div>
    </div>
  </div>
  <span class="count"><b>4</b><span>quizzes</span></span>
</div>
```

- The search box takes all leftover width (`flex: 1`).
- **Filters and sort go in the popover, not in the strip.** If you add a new filter, add a `<h4>` plus a `.opts` group to `.pop`. Don't add dropdowns to the strip.
- Add `<span class="dot"></span>` inside `.filterbtn` whenever a filter or sort is set to something other than its default.
- `.pop.open` shows the popover. It closes when the user clicks outside it. On phones it stretches across the full toolbar.
- `.count` always shows the number of results currently visible. On phones it stacks into a number over a word.

### Data list: `.list`, `.head`, `.row`, and cells
This is the main content pattern: a table built with CSS grid, where **the header and the rows share one `grid-template-columns`**.

```html
<div class="list present">
  <div class="head"><div>Status</div><div>Quiz</div><div class="mid">Class</div><div class="wide">Owner</div><div></div></div>
  <div class="row">
    <div class="status draft">draft</div>
    <div class="title"><strong>Quiz 1 — Big-O Warmup</strong><span class="meta">8 questions · edited 2026-09-26</span></div>
    <div class="cell mid"><span class="cls none">Not published</span></div>
    <div class="cell wide"><span class="tag me">ME</span></div>
    <div class="kebab-wrap"><button class="kebab">⋯</button></div>
  </div>
</div>
```

| Piece | Purpose |
|---|---|
| `.head` | Black header row that sticks to the top of `.list` while it scrolls |
| `.status` + `draft` / `published` / `rank` | Full-height colored first column. It's the first thing the eye lands on |
| `.title strong` | Row title in Archivo Black. Hovering the row underlines it in orange |
| `.meta` | Grey summary line under the title. **Hidden on desktop** (the columns show that info) and **shown on tablet and phone** (where the columns are hidden) |
| `.cell` / `.cell.dim` | Normal cell / grey bold cell for numbers and dates |
| `.tag` / `.tag.me` | Small bordered label. Orange = shared, alabaster = mine |
| `.cls` / `.cls.none` | Navy class name / grey italic "Not published" |
| `.score` + `.bar` | Big `9/10` number with a small orange progress bar |
| `.kebab` | The `⋯` row-actions button (use `→` for rows that just open something) |

**Adding a new list:** give the container a modifier class (like `.list.students`) and define that class's column grid for all three screen sizes (see §5). Mark each column `.mid` (hide on phones) or `.wide` (hide on tablets and phones), or leave it unmarked (always visible).

### Row menu: `.menu`
The dropdown that opens from `⋯`. Sections are split by a navy `.sub-label` (like "Publish to…"), and options inside a section are indented with `.class-opt`.
- The menu is positioned with `position: fixed`, calculated from the button, so the scrolling list never clips it. It flips upward when it's near the bottom of the screen. Reuse `openMenu()` from the mockup.
- It closes when the user clicks outside it **or scrolls the list**.

### Buttons
| Kind | Look | When |
|---|---|---|
| Primary | `.btn`: orange with white text, 3px border, sky shadow | The one main action in a panel (e.g. **GO →**) |
| Structural action | Navy block (like `.join`) | Top-level actions in the tab bar |
| Secondary | Sky block (like `.plus`, `.filterbtn`) | Create, filter, and other secondary actions |
| Row action | White with a navy shadow (`.kebab`) | Actions on a single row |
| Option chip | `.opt` / `.opt.on` (navy when on) | Choices inside popovers |

**Press state:** move the button by its shadow size and remove the shadow (`transform: translate(3px,3px); box-shadow: none;`). It should feel like physically pushing the block.

### Inline panel: `.join-panel`
A navy strip that slides open under the tab bar for short one-field tasks (like entering a session code). Use this instead of a modal whenever the task is one input and one button.

### Empty state: `.empty`
Centered bold text. Tell the user what to do, and highlight the action in orange: `Nothing here. Hit <b>+</b> to make a quiz.` If a search returned nothing, say so: `No quizzes match "sql".`

### Toast: `.toast`
A navy bar at the bottom center for quick confirmations ("Share link copied"). It shows for 1.8s. Call `toast("message")`.

---

## 5. Responsive rules

Phones are the **primary** device (SRS §4.1), so check phone width first, not last.

| Width | What changes |
|---|---|
| **> 1150px** (desktop) | All columns visible; `.meta` hidden |
| **≤ 1150px** (tablet) | `.wide` columns hidden; `.meta` line appears under titles; grid drops to about 4 columns |
| **≤ 640px** (phone) | `.head` and `.mid` columns hidden; grid is `status · title · action`; smaller page padding; tab text `13px`, `+` shrinks to `44px`; toolbar stays one line; popover spans full width |

Rules:
- **Nothing may overflow sideways at 360px.** Test with Chrome DevTools at 360 and 390 wide.
- If text gets cut off on phones, shorten the label (we changed "Recently edited" to "Last edited") before shrinking the font.
- Keep touch targets around **40px tall**. The `⋯` button (38px) is the smallest in the mockup; don't go below it.

---

## 6. Interaction patterns

- **One source of state, re-render the region.** The mockup keeps `tab`, `filter`, `sort`, and `query` in variables and re-renders the list. In React this becomes `useState`, and the same idea applies.
- **Search filters as the user types.** Don't add a "Search" submit button.
- **Everything that opens also closes** on outside click. Popovers and menus also close when the list scrolls.
- **Give feedback for every action** with a toast or a visible state change.
- Switching tabs resets sort to its default and closes any open popover.

---

## 7. Accessibility (do these, the mockup is not finished here)

The mockup skips some of this, so **add it when you build the real page:**

- [ ] **Focus styles.** Add a visible `:focus-visible` outline to every interactive element, e.g. `outline: 3px solid var(--orange); outline-offset: 2px;`. The mockup doesn't have this yet.
- [ ] Give icon-only buttons an `aria-label`: `⋯` → `aria-label="Quiz actions"`, `+` → `aria-label="New quiz"`, `⌕` search → `aria-label="Search quizzes"`.
- [ ] Tabs use `role="tablist"` / `role="tab"` / `aria-selected`, as shown above.
- [ ] Popovers and menus: `aria-expanded` on the trigger, and close on `Esc`.
- [ ] Clickable rows (Participate) must also work from the keyboard. Use a real `<button>` or link inside the row, not just `onclick` on a `div`.
- [ ] Never rely on color alone: status blocks always include the word (`DRAFT`, `PUBLISHED`).

---

## 8. Moving this into React

The SRS stack is **React + FastAPI**. When porting:

1. Put the `:root` tokens and the shared component CSS in one global stylesheet (e.g. `src/styles/theme.css`) and import it once. **Don't copy tokens into individual components.**
2. Put the Google Fonts `<link>` in `index.html`.
3. `class` → `className`. Keep the **same class names** so this guide stays accurate.
4. Replace the mockup's `innerHTML` template strings with JSX. The mockup builds HTML from strings; **don't do that with real user data** (quiz titles, names), because it opens you up to XSS. JSX escapes text for you.
5. Pull out reusable components: `<TabBar>`, `<Toolbar>`, `<FilterPopover>`, `<DataList columns=… rows=…>`, `<RowMenu>`, `<StatusCell>`, `<Toast>`.
6. Replace the fake data arrays (`MADE`, `PART`, `CLASSES`) with API calls.

---

## 9. Do / Don't

| Do | Don't |
|---|---|
| 3px ink borders on every surface and control | Thin gray borders, or borderless cards |
| Hard offset shadows (`6px 6px 0`) | Blurred / soft shadows |
| Square corners | `border-radius` |
| Solid color blocks from the token list | Gradients (except the stripe texture), new hex values |
| Orange for "selected" and key numbers | Orange as a decorative accent |
| Uppercase letter-spaced small labels | Uppercase long sentences |
| Archivo Black for titles and numbers | Archivo Black for paragraphs |
| One bordered frame that fills the screen | Floating cards in the middle of empty space |
| Filters inside the Filter popover | Rows of dropdowns in the toolbar |
| Test at 390px first | Designing desktop-only and "fixing mobile later" |

---

## 10. New-page checklist

- [ ] Uses the page skeleton: header + one `.frame` that fills the screen; only the content region scrolls
- [ ] Only token colors (`var(--…)`), no raw hex
- [ ] Archivo Black for display text, Space Grotesk for everything else
- [ ] All surfaces and controls have 3px ink borders and hard shadows; no rounded corners
- [ ] Status and active states follow the color rules (orange = selected, navy = structure, sky = secondary)
- [ ] Lists use `.head` + `.row` with a shared grid, with columns tagged `.mid`/`.wide`
- [ ] Works at 1440, 1000, and 390 wide with no sideways scrolling
- [ ] Empty state written, and every action gives feedback
- [ ] Focus outlines, `aria-label`s, and keyboard access added (§7)
- [ ] Checked against `made-dashboard-main.html` side by side

Questions or want to change a token? Bring it to the team first so every page stays consistent.
