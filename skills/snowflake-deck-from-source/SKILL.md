---
name: snowflake-deck-from-source
description: "Build a short Snowflake-branded deck from a Google Doc, URL, or session findings, with an approved outline, an audience-aware argument, and pushbacks plus talk track in speaker notes. Use when: converting a source document or session findings into a slide deck, condensing a longer artifact into a short pitch. Triggers: build a deck from this doc, use the Snowflake template not blank, put the pushbacks in speaking notes, give me slide text for these points, slides on X and Y, turn this into a presentation"
version: 1.0.0
---

# Skill: snowflake-deck-from-source

Turn a source document, URL, or the current session's findings into a short,
Snowflake-branded deck: an approved outline first, then Snowflake-template
slides, with a grounded talk track and any pushbacks on the customer's stated
position captured in speaker notes rather than on the slide.

## When to Use

- The user wants a deck distilled from a Google Doc, article/URL, or the
  findings already surfaced this session.
- The ask implies argument, not transcription — e.g. "2 slides on data and
  personas," "put the pushbacks in the notes," "make the case for X."
- The output must land on the Snowflake template, not a blank deck.

## When NOT to Use

- The user already has exact slide-by-slide content and just wants it
  rendered — go straight to `snowflake-gslides`.
- The target is a Google Doc, not slides — use `google-doc-formatter`.
- The user wants a full technical writeup, not a short pitch deck — a doc
  handles depth better than slides.

## Relationship to snowflake-gslides

`snowflake-gslides` renders slides from content: template setup, Google
Slides API mechanics, diagrams, append/replace/update modes. This skill does
not touch any of that. This skill's job stops at deciding *what the content
should be* — the outline, the argument, and the notes — when the input is a
source document rather than ready-made slide text. Once the outline is
approved, load `~/.snowflake/cortex/vault/skills/snowflake-gslides/SKILL.md`
and hand it the outline as the md input.

## Prerequisites

- Source material: a Google Doc URL/ID, a URL, or session findings already
  in context.
- `snowflake-gslides` prerequisites (ADC auth, Snowflake template) apply at
  render time — that skill handles them, not this one.

## Workflow

### Phase 1: Ingest and extract the argument

Read the source (Google Doc via `read_document`, URL via fetch, or the
session's own findings). Extract three things explicitly, in writing, before
drafting anything:

1. **Audience** — who reads this and what do they already know.
2. **Their stated position** — the points the audience itself has already
   made in the source. Naming this first is what lets later slides engage
   with their position instead of talking past it.
3. **Competitive/strategic angle** — where Snowflake's answer differs from
   or challenges that position.

### Phase 2: Draft and approve the outline

Produce a one-line-per-slide outline, each line mapped to the source point it
answers. Stop here and get explicit approval before generating any slides.

Why: reworking a nine-line outline is cheap; reworking a rendered deck is
not. Slide edits go through the Slides API, which is fiddly to undo cleanly —
catch structural problems in the outline, not after render.

### Phase 3: Weight toward issues, not basics

Bias slide count toward the audience's open problems and how Snowflake
solves them, not product fundamentals. A short-deck request usually means
the audience already has the basics — spending two of seven slides restating
them is the most common way these decks under-deliver. If the source
material is mostly background, compress it into one slide max.

### Phase 4: Render

Hand the approved outline to `snowflake-gslides` as its md input and follow
that skill's workflow (template selection, mode, build) unmodified.

### Phase 5: Add speaker notes

Apply the Speaker Notes Contract below to every slide.

### Phase 6: Verify claims

Check every factual claim against `cortex search docs` or a documented
customer win. Mark anything unverified rather than asserting it — a deck
often travels without its presenter, so an unmarked guess reads as fact to
whoever forwards it.

## Speaker Notes Contract

Each slide's notes carry three things:

1. **Talk track** — the grounded delivery in the presenter's voice, matching
   what's verifiable, not a repeat of the slide's bullets.
2. **Pushbacks as questions** — where the outline challenges the audience's
   stated strategy, phrase it as a question to ask in the room, not a
   statement on the slide. On-slide criticism of the audience's own strategy
   reads as an attack; the same point asked as a question lands as
   consultative.
3. **Unverified claims** — any claim from Phase 6 that couldn't be confirmed,
   with a note on what source would confirm it.

## Stopping Points

- **After Phase 2**: outline must be explicitly approved before any slide is
  rendered.
- **After Phase 6**: every unverified claim must be either accepted as-is by
  the user or cut — none carry forward silently.

## Output

- The rendered Snowflake-template deck (URL from `snowflake-gslides`).
- An outline-to-source mapping table: slide number, one-line content, and
  the source point/quote it answers — so the reader can trace every slide
  back to where it came from.
