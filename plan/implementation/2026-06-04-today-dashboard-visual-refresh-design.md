# Today Dashboard Visual Refresh Design

## Context

The current `/today` workstation already surfaces most of the intended V2 trading data, but the UI still reads as a loose stack of similarly weighted cards, tables, and tab groups. The main operator complaints are:

- density is out of control
- important content does not stand out
- navigation and drill-down flow are not obvious

This is no longer primarily a missing-data problem. It is an information architecture, visual hierarchy, and page composition problem.

The active code already moved `Trades` toward a ticker-first workspace, but the surrounding page shell still makes the experience feel noisy and fragmented. This spec defines a redesign focused on clarifying the workstation without changing the meaning of the underlying trading artifacts.

## Goals

- Reduce perceived density on `/today` without hiding critical operating information.
- Establish a clear visual reading order so operators can understand current state within a few seconds.
- Make the page feel like a hybrid of a trading command center and a research workspace:
  - top of page: compact, status-driven, operational
  - body of page: evidence-oriented, readable, decision-supportive
- Promote the selected ticker workspace to the primary canvas rather than one section among many.
- Demote secondary tables and controls so they do not compete with the main decision surface.
- Reuse the current server-rendered FastAPI + Jinja architecture and existing presenter payloads where practical.

## Non-Goals

- This spec does not add new trading, risk, candidate, or portfolio data fields.
- This spec does not redesign the persistence model or require new API endpoints.
- This spec does not require a client-side SPA or JS-heavy interaction model.
- This spec does not redefine the business meaning of tabs such as `Trades`, `Candidates`, or `Risk & Macro`.
- This spec does not attempt a full product-wide visual redesign outside `/today`.

## Primary Approach

Recommended approach: `hybrid command center`.

Instead of treating `/today` as a sequence of peer sections, the redesign should make the page read in layers:

1. `Operator Strip`
2. `Primary Workspace`
3. `Evidence Modules`
4. `Secondary Data Surfaces`

This is preferred over:

- a pure visual cleanup of the current structure, which would improve cosmetics without fixing reading order
- a reading-first research layout, which would improve calmness but weaken active session control

The chosen direction matches the user-approved priorities:

- first fix density
- then fix hierarchy
- then fix flow

## Information Architecture

### Page Reading Order

The page should answer these questions in order:

1. `Do I need to act right now?`
2. `What object am I currently working on?`
3. `Why is that the current focus?`
4. `What secondary data do I need if I want to inspect or operate further?`

The page should no longer ask the operator to scan multiple unrelated white cards before finding the main work surface.

### Layer 1: Operator Strip

The top of the page should become a dense but controlled status strip split into two groups.

#### Left group: action-driving session status

This group should hold only the highest-priority metrics:

- open alerts
- action items or actionable ticker count
- buying power
- gross exposure
- day PnL or other short-horizon session signal

#### Right group: session context

This group should hold context needed to interpret the session:

- trade date
- macro regime
- risk appetite
- job or pipeline status

The existing pattern of three similarly sized context chips plus a second equally loud KPI row should be replaced by grouped status rails with visibly different priority.

### Layer 2: Primary Workspace

Below the operator strip, the main content area should become a single primary workspace rather than multiple same-weight cards.

Recommended structure:

- left column: queue or navigator surface
- right column: main decision canvas

The first implementation can keep this centered on the ticker-first `Trades` workspace, because that is the clearest place to establish a dominant reading order.

### Layer 3: Evidence Modules

Inside the main decision canvas, details should be separated by purpose rather than presented as a single stream of subcards.

Two evidence groups should be visually distinct:

- `Decision Support`
  - latest conclusion
  - signal summary
  - catalyst / timeline / trend evidence
- `Risk and Execution`
  - risk manager stance
  - position state
  - order / execution state

This split prevents research evidence and execution state from flattening into one undifferentiated pile.

### Layer 4: Secondary Data Surfaces

Long tables, filter controls, and operational list management should remain available but move below the main decision rhythm or behind secondary tab sections.

This primarily applies to:

- `Candidates`
- `Risk & Macro` exposure tables
- bulk controls and long-form list views

These surfaces remain important, but they should not dominate first-view attention.

## Navigation Hierarchy

The current page effectively contains two tab systems with similar visual weight:

- global workstation tabs
- local selected-ticker detail tabs

That makes navigation ambiguous.

The redesign should establish a strict hierarchy:

### Primary navigation

The top-level workstation tabs remain, but with lower visual aggression than the main workspace content. They should read as navigation chrome, not as the main event on the page.

### Secondary navigation

Ticker-detail sections such as `Timeline`, `Trend`, `Decisions`, and `Risk` should use a lighter local control pattern than the global tabs. Acceptable patterns include:

- a lower-contrast segmented control
- compact inline tabs
- collapsible sections where open/closed state is clearer than tab switching

The critical rule is that local view switching must not look equivalent to page-level navigation.

## Card Hierarchy

The current page overuses one generic white-card treatment. The redesign should define three explicit card tiers.

### Hero panels

Use for the main decision surface, especially:

- selected ticker latest conclusion
- top-level current focus summary

Only one or two hero panels should be visible in the main viewport.

### Support modules

Use for supporting evidence and current state:

- signal summary
- risk manager summary
- position / execution state
- compact timeline or trend modules

These should be quieter than hero panels but more legible than raw tables.

### Data surfaces

Use for:

- large tables
- filters
- manual request operations
- exposure lists

These should prioritize scanning and operating efficiency, not narrative emphasis.

## Typography and Spacing System

The page currently feels noisy partly because too many text elements speak at similar volume. The redesign should standardize typography and spacing across the page.

### Typographic levels

Define four consistent text levels:

- page title
- section heading
- module heading
- label / metadata text

Metadata and helper text should be clearly quieter than operator conclusions.

### Spacing rhythm

Define spacing at three levels:

- section spacing
- module spacing
- row / control spacing

This rhythm should be reused across `Overview`, `Trades`, `Risk & Macro`, and `Candidates` rather than each area drifting into its own density pattern.

### Empty states

Empty and unavailable states should be brief and visually quiet:

- `No live alerts.`
- `No material changes.`
- `No ticker selected.`
- `Unavailable.`

These should not consume the same visual weight as active decision content.

## Trades Workspace Rules

The ticker-first workspace should remain the center of gravity for this redesign.

### Ticker rail

The left-side ticker rail should become a stable navigation surface rather than a stack of text-heavy mini-cards.

Each ticker card should show only:

- ticker
- current decision label
- short `why now`
- one compact state badge

Secondary metadata such as company fallback text, repetitive unavailable text, or long raw identifiers should be reduced or reformatted.

### Detail canvas

The right-side detail area should begin with a clear hero conclusion block. Below that, supporting information should break into purpose-specific modules rather than one long downward stream.

Recommended order:

1. latest conclusion
2. signal / evidence module
3. risk / execution module
4. local detail navigation or collapsible history sections

### Local detail controls

The current local tab row should be visually demoted and may be converted to a lighter segmented control or collapsible section group if that produces a clearer vertical rhythm.

## Secondary Surface Rules

### Candidates

The active universe filter should not default to a full wall of inputs. The initial view should emphasize a summary of the active filter and only expose full editing controls when the operator intends to act.

`Manual requests` should read as a focused operation module, not as one more row group inside a larger noisy section.

### Risk & Macro

The first view should surface:

- risk config version
- binding constraints
- top exposure summary

Long raw exposure tables should remain available but visually secondary.

### Overview and Portfolio

These sections should remain present, but their default card weight should not compete with the active selected-ticker workspace unless the chosen top-level tab makes them primary.

## Delivery Boundaries

This redesign is intentionally limited to template composition and styling strategy.

### In scope

- `src/templates/today.html` structure and section composition
- `src/static/style.css` visual tokens, layout rules, card hierarchy, spacing, and local/global navigation differentiation
- limited route/template wiring needed to support reorganized rendering, if existing data is already available
- responsive behavior adjustments for the new shell

### Out of scope

- schema changes
- new persistence tables
- major presenter/business-logic rewrites
- new front-end framework adoption
- heavy JavaScript interaction

## Implementation Strategy

This work should be delivered in controlled phases.

### Phase 1: Global shell and visual system

Build the shared layout shell first:

- operator strip
- top-level page rhythm
- card hierarchy
- typography and spacing tokens
- navigation hierarchy

### Phase 2: Trades primary canvas

Refactor the current ticker-first `Trades` workspace into the new dominant canvas using the new shell rules.

### Phase 3: Secondary surfaces

Apply the visual system and density controls to:

- `Candidates`
- `Risk & Macro`
- `Overview`
- `Portfolio`

### Phase 4: Polish and responsive pass

Finalize:

- narrow-screen behavior
- overflow behavior for tables and rails
- empty states
- visual consistency across sections

## Risks and Constraints

### Risk: CSS-only approach will underdeliver

If the work is constrained to styling without template restructuring, the page will likely remain fundamentally noisy.

### Risk: over-restructuring could break existing semantics

The redesign should preserve current data meaning and route semantics. Structural changes should stay in the presentation layer unless a small template-supporting presenter adjustment is clearly justified.

### Risk: no visual-system baseline means continued drift

If the redesign touches individual sections without first establishing layout and hierarchy rules, the page will regress into section-by-section inconsistency.

## Verification Criteria

The redesign should be considered successful if the resulting page makes these outcomes true:

- within about five seconds, an operator can identify current session state and the main focus object
- the first viewport clearly distinguishes primary content from supporting and secondary content
- the `Trades` workspace feels like a working canvas rather than a tall text stack
- `Candidates` and `Risk & Macro` remain accessible but no longer dominate initial attention
- empty states do not create major visual noise
- the page remains readable on both desktop and narrower layouts

## Recommendation

Proceed with a presentation-layer redesign that allows meaningful template restructuring, but keep data semantics and business logic stable.

This is the highest-leverage change because the current pain is not missing capability; it is the lack of a strong visual and structural opinion about what matters first.
