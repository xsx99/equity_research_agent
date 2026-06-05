# UI Design Learnings

This note captures reusable UI design lessons from the `/today` trading workstation iterations. The goal is to preserve the reasoning behind "this feels clean" vs "this feels noisy" so future operator-facing UI work can reuse the same heuristics.

## Core Principle

A clean operator UI is usually not about color theme or visual decoration. It is mostly about reading order, information density, and how many decisions the user has to make at once.

## What Made The Reference UI Feel Cleaner

### 1. Default to scan-first, not expand-everything

- The primary surface should let the user scan many symbols quickly.
- Use rows or compact cards for the summary layer.
- Show only one selected item in detail at a time.

Why this matters:
- A workstation is usually used to compare candidates, not to read ten full dossiers at once.
- Expanding every item creates vertical repetition and destroys scan speed.

### 2. One primary task per viewport

- The page should answer one main question first.
- Good example: "Which symbols need attention right now?"
- Details should sit behind selection, not compete with the list.

Why this matters:
- When queue, detail, controls, and diagnostics all have equal emphasis, the UI feels busy even if each individual card is "clean."

### 3. Width should match content density

- If the content is brief and row-like, use a row or compact list.
- Do not stretch a tiny amount of text across a full-width card unless the detail actually uses the width.
- Reserve wide canvases for charts, comparisons, long reasoning blocks, or two-column detail panels.

Why this matters:
- A full-width card with all content stuck in the left 20 percent still feels messy because the layout promises richness but delivers a narrow text stack.

### 4. Stable columns beat repeated vertical label stacks

- Prefer aligned columns such as ticker, status, setup, conviction, and short reasoning.
- Avoid repeating the same `WHY / OUTCOME / IDENTITY / STRATEGY` stack for every row in the default state.
- Repeated labels belong in the selected-item detail pane, not in every list item.

Why this matters:
- Repetition makes the page look longer and noisier without adding new information.

### 5. Summary first, detail second

- Each item should lead with a single summary sentence in operator language.
- Dense metadata should become secondary fields, not compete with the headline.
- Advanced fields and raw IDs should be hidden behind disclosure.

Why this matters:
- The user first needs the conclusion, not the schema.

### 6. Use operator language, never internal taxonomy, on the main surface

- Translate internal IDs into short natural-language labels.
- Show raw strategy IDs, source IDs, and enum values only in advanced sections.
- The primary read should explain what happened, not how the system names it internally.

Why this matters:
- Internal names are implementation details; they add cognitive load and reduce trust when shown as primary copy.

### 7. Fewer visual modes per screen

- Limit the number of interaction patterns active at the same time.
- Avoid mixing large freeform cards, dense audit tables, forms, and repeated disclosures at equal weight in the same viewport.
- Pick one dominant reading mode per section.

Why this matters:
- A screen feels calmer when the user learns one pattern and repeats it.

### 8. Chips and badges should compress state, not multiply noise

- Use badges for short state markers only.
- Keep the number of badges small and consistent.
- Do not use a badge when plain text is clearer.

Why this matters:
- Too many badges create visual chatter and dilute the meaning of the important ones.

### 9. Cleanliness comes from hierarchy, not from dark mode

- Dark mode can look clean, but it is not the reason a UI feels organized.
- The real drivers are spacing, grouping, contrast control, and progressive disclosure.

Why this matters:
- Copying colors without copying the hierarchy will not fix a cluttered layout.

## Anti-Patterns To Avoid

- Expanding every candidate by default.
- Repeating the same labeled sub-sections inside every card.
- Showing raw IDs on the primary surface.
- Giving summary, controls, and diagnostics equal visual priority.
- Using full-width cards for narrow-content summaries.
- Making the user read vertically to compare fields that should be aligned horizontally.

## Default Pattern For Operator Workbenches

When the UI is centered on many symbols or entities:

1. Show a compact queue/list first.
2. Make one row/item selected.
3. Render one focused detail pane for the selected item.
4. Put advanced/debug/audit data behind a disclosure or secondary tab.

This should be the default starting point unless there is a strong reason to do otherwise.

## Pre-Ship Checklist

Before shipping an operator-facing UI, check:

- Can the user tell what needs attention in under 5 seconds?
- Can the user compare multiple rows without opening each one?
- Is only one item fully expanded by default?
- Are internal IDs hidden from the primary surface?
- Does the layout use width intentionally, or are wide cards mostly empty?
- Are summary and detail clearly separated?
- Are advanced diagnostics available without dominating the page?
