# dubizzle CRM design system

Visual system for the **dubizzle cars CRM**: the internal tool sales agents, processors and admins use to manage leads and run service flows (Car Services: Financing, Insurance, Extended Warranty, Service Contract).

## Sources
- 4 CRM screenshots: `uploads/Screenshot 2026-09-03 115406.png`, `…122521.png`, `…124346.png`, `…125456.png` (Insurance / Extended Warranty / Service Contract flows on a lead).
- `uploads/Insurance - CRM Flow_1.html`: an earlier CRM flow mockup, used for the bulk-upload pattern.
- ClickUp tickets z8v0kmvaqp (Finance Rates admin) and z8v0kmvaq3 (Financing C2C flow), workspace 3692463.
- Mockups built from these: `Financing C2C Flow.dc.html`, `Finance Rates Admin.dc.html`.
- **No codebase, Figma file, font files or logo files were provided.** All values are measured from screenshots.

## Index
- `styles.css`: entry point (imports only)
- `tokens/`: fonts.css, colors.css, typography.css, spacing.css, base.css
- `components/`
  - core: Button, IconButton, Tag, Avatar, Icon
  - forms: Field, Input, Textarea, Select, PhoneInput, OptionGroup, UploadButton, OptionCard
  - navigation: TopNav, Tabs, StageProgress
  - data: Card, InfoPair, StageHeader, Table
  - feedback: Dialog, Toast
- `guidelines/`: foundation specimen cards
- `ui_kits/crm/`: click-through lead screen and rates admin screen
- `SKILL.md`: Agent Skill wrapper

### Intentional additions
- **Icon**: a wrapper that renders Lucide icons through a CSS mask so they take on the text colour. The CRM's own icon set wasn't available.
- **Dialog, Toast, Table**: not in the screenshots. Built for the admin mockups, following the CRM's look.

## Content fundamentals
- **Voice:** operational and terse. Labels are nouns ("Payment Amount", "Seller Type"), and buttons are a verb or the destination ("Proceed", "Cancel", "Add Task", "Create Flow", "Lost").
- **Casing:** Title Case for field labels, stage names, tabs and buttons ("Get Payment Link", "Verify Payment"). Sentence case for helper and error text ("This field is required", "Five thousand").
- **Placeholders:** "Select X" for selects and "Enter X" for inputs ("Select Engine", "Enter Buyer Name").
- **Optionality:** written as a grey "(optional)" suffix on the label. Required fields have no asterisk and show a red message after a failed submit.
- **Data formats:**
  - IDs: "REF # 960046"
  - Dates: "03 Sep, 2026, 11:42 AM"
  - Money: "AED 1,047" (always AED, comma thousands)
  - Status pairs: "Interested • Interested I…"
- **Person:** the UI rarely addresses the user. Customer messages say "you" and sign off "— dubizzle Car Services".
- **Emoji:** none. The only decorative mark is the hot-lead flame badge next to the lead name.

## Visual foundations
- **Colour:** white cards on a light-grey page (#f5f5f5). One brand red: #c00000 for actions and active states, #d4000b in the logo.
  - Red appears as solid fill on exactly one primary button per form (Proceed). Otherwise it's a soft pink fill (#fbe6e6) with red text: Call, Add Task, header icon circles, Lost.
  - Entered field values are red; placeholders are grey.
  - IDs and client links are teal (#1a8cb0). Counts and amounts are red.
  - Status uses flat tinted tags: purple for category/lead status, blue for In Progress, green for Completed/Verified, amber for pending, red for missing.
- **Type:** a single geometric sans (Outfit as stand-in). Regular weight for nearly everything; medium for titles and nav. Sizes are large for an admin tool: 17px nav and values, 16px labels, 14px meta.
- **Layout:** 76px sticky white header. Below it, a 380px lead sidebar of stacked cards on the left and a flexible workspace card on the right, 16–20px gutters. Forms use a 2-column grid with 24–32px gaps; the create-flow form uses right-aligned labels.
- **Cards:** white, 12px radius, no border on the grey page, almost no shadow. Inner cards (Service, Payment Info) get a 1px #ececec border. The open stage form gets a 1px pink outline (#f1c9c9).
- **Corners:**
  - 4px: inputs, buttons, tags
  - 6–8px: chips, the Current Stage box
  - 10–12px: cards and quote option cards
  - Round: icon buttons and avatars
- **Borders:** 1px #e0e0e0 on controls, #ececec dividers. Focus and invalid state is a 1px red border, with no glow.
- **Shadows:** essentially flat. A hairline under the header; soft shadows only on popovers, dialogs and drawers.
- **Stage progress:** a row of labelled 4px bars. Done stages are light red, the current one is red, upcoming ones are grey, followed by a pink "Current Stage n/N" box.
- **Backgrounds and imagery:** no gradients, textures or illustrations. Images are limited to small car thumbnails and the UAE flag on phone inputs.
- **Motion:** minimal. 150ms background transitions on hover, no bounces. The stage history panel collapses and expands with a chevron.
- **Hover and press:** solid red goes darker (#a30000, then #8f0000 when pressed). Pink fills deepen to #f1c9c9. White buttons tint to #fafafa. Text tabs go from grey to red when active.
- **Transparency and blur:** only the modal backdrop, rgba(20,20,20,.35). No blur.

## Iconography
- The CRM uses thin outline icons (chevrons, phone, bell, calendar, pencil, refresh) in the Lucide/Feather style, plus a few filled glyphs (the select caret triangle, a WhatsApp mark).
- **Substitution:** I didn't have the CRM's icon files, so this system links **Lucide** from a CDN through the `Icon` component, at 16–20px and inheriting text colour. Header icons sit in 36px pink circles with red glyphs.
- The select caret is a CSS triangle. No emoji. Unicode is only used for "•" separators and "›" breadcrumbs.

## Brand assets
No logo file was supplied, so the wordmark is set in plain type ("dubizzle **cars**" | crm / CRM). Pass the official asset to `TopNav` via its `logo` prop.
