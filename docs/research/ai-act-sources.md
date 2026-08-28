# EU AI Act — source pack for the gated extension

status: research only, 2026-08-28
gate: `.vault/NON-GOALS.md` — "No AI Act rule set in the core. Gated extension: only after the GDPR test-set number is locked (target Saturday 2026-08-29 ~22:00 UTC)."

This file exists so that if the gate opens, the extension is a build job and not a research job. Nothing here authorises writing AI Act code. Verbatim article text lives beside it in `docs/research/sources/ai-act/`; every legal statement below points at one of those files.

## 0. Where the text came from

`eur-lex.europa.eu` serves an AWS WAF JavaScript challenge to both `curl` and WebFetch, so the HTML pages could not be read directly:

- FETCH FAILED: https://eur-lex.europa.eu/eli/reg/2024/1689/oj (HTTP 202, WAF challenge page, 4 attempts)
- FETCH FAILED: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689 (empty body via WebFetch; HTTP 202 via curl, 3 attempts)
- FETCH FAILED: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ%3AL_202601744 (HTTP 202, WAF challenge page, 4 attempts)
- FETCH FAILED: https://www.whitecase.com/insight-alert/eu-ai-omnibus-enters-force-amending-ai-act (HTTP 403)

The same Official Journal manifestation is served without a challenge by the EU Publications Office content repository, and that is what was used [S1][S2]. The EN HTML manifestation of the AI Act is `…/cellar/dc8116a1-3fe6-11ef-865a-01aa75ed71a1.0006.03/DOC_1`, self-identifying in its first line as `L_202401689EN.000101.fmx.xml`; the Digital Omnibus is `…/cellar/b459c07f-86fb-11f1-bf5e-01aa75ed71a1.0006.03/DOC_1`, `L_202601744EN.000101.fmx.xml`. No article text was written from memory. The extraction script stripped HTML tags and joined a bare point marker such as `(a)` to the line following it; each source file repeats that note.

## 1. Timeline as of 2026-08-28 — the critical item

**Answer: the Digital Omnibus was adopted and is in force. It is Regulation (EU) 2026/1744.** It was signed 8 July 2026, published in the Official Journal on 24 July 2026, and entered into force on 27 July 2026 (third day after publication) [S2].

The Commission proposal of 19 November 2025 that the task brief refers to is therefore no longer pending, and the conditional trigger it proposed did not survive. Gibson Dunn, writing after the trilogue deal and before publication [S5]:

> "The proposal contained a set of targeted amendments, most prominently a conditional delay mechanism for high-risk obligations."
>
> "The agreed text replaces the Commission's originally proposed conditional trigger mechanism with these fixed dates."

### Dates that currently bind

| Obligation | Date | Where it says so |
|---|---|---|
| Annex III high-risk systems — Chapter III Sections 1, 2, 3 | **2 December 2027** | AI Act Art. 113(3)(c)(i) as replaced by Reg. 2026/1744 Art. 1(40)(b) [S2] |
| Annex I embedded high-risk systems — same Sections | **2 August 2028** | Art. 113(3)(c)(ii) as replaced [S2] |
| Article 50 transparency (chatbot disclosure, synthetic-content marking, deepfake and AI-text disclosure) | **2 August 2026 — already applicable** | Art. 113, second paragraph, unamended general date; Art. 50 is in Chapter IV and appears in no deferral point [S1][S2]; confirmed [S3][S4] |
| Art. 50(2) machine-readable marking, for systems placed on the market before 2 August 2026 | **2 December 2026** | new AI Act Art. 111(4), inserted by Reg. 2026/1744 Art. 1(39)(b) [S2] |
| Prohibitions (Art. 5) and AI literacy (Art. 4) | 2 February 2025, except the two new prohibitions on non-consensual intimate material and CSAM, which apply from 2 December 2026 | Art. 113(3)(a) as replaced [S2] |
| GPAI model obligations, governance, penalties chapter | 2 August 2025 | Art. 113(3)(b), unamended [S1] |
| Chapter III Section 4 (notified bodies) | 2 August 2025 | Art. 113(3)(b) [S1] |
| Art. 6(5) Commission guidelines on classification | excluded from the deferral, so on the general date | Art. 113(3)(c) opening words as replaced [S2] |
| Art. 102–110 (amendments to other Union acts) | 27 July 2026 | new Art. 113(3)(d) [S2] |

Verbatim, from the amending Regulation [S2]:

> ‘(c) Chapter III, Sections 1, 2, and 3, with the exception of Article 6(5), shall apply from:
> (i) 2 December 2027 as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III; and
> (ii) 2 August 2028 as regards AI systems classified as high-risk pursuant to Article 6(1) and Annex I;’

And the reason, from recital (40) [S2]:

> "For the obligations related to high-risk AI systems laid down in Sections 1, 2 and 3 of Chapter III of Regulation (EU) 2024/1689, the delayed availability of standards, common specifications, and alternative guidance and the delayed establishment of national competent authorities lead to challenges that jeopardise the effective entry into application of those obligations and that risk a significant increase in implementation costs in a way that does not justify maintaining their initial date of application, namely 2 August 2026."

The Commission's own AI Act page carries the same two dates [S3]:

> "Rules for systems used in certain high-risk areas — including biometrics, critical infrastructure, education, employment, migration, asylum and border control — will apply from 2 December 2027."

### What did not move

Article 1 of Regulation (EU) 2026/1744 lists every amendment. Article 50(1) to (6) is untouched; only paragraph 7 (codes of practice) is replaced. Annex III is untouched. Article 6(1) to (3) keeps its 2024 wording. New paragraphs 1a and 1b restate what qualifies as a safety component for the purposes of the whole Regulation — Art. 6(1a) says so expressly ("For the purposes of this Regulation, including paragraph 1 of this Article"), so they also bear on Annex III point 2 and on the Art. 3(14) definition as amended by Art. 1(4)(a). New paragraph 1c is confined to the Annex I route: it disapplies the condition in Art. 6(1), point (b). Article 12, Article 14, Article 26 and Article 27(1) are untouched. The full amendment inventory is in `sources/ai-act/omnibus-2026-1744.md`.

Cooley's post-publication note states the split the same way [S4]:

> "Importantly, the deferral of Annex III obligations does not affect all 2 August 2026 obligations. Article 50 transparency obligations (including chatbot disclosure and deepfake labelling obligations for systems launched from 2 August 2026), GPAI model requirements (already in force since August 2025), the EU AI Office's enforcement powers, and governance body obligations all remain on the 2 August 2026 schedule."

### What is not known

Three gaps, stated rather than guessed:

- No consolidated EN text of Regulation (EU) 2024/1689 incorporating the 2026/1744 amendments was retrieved. Everything above is the original OJ text read against the amending text. Anyone building on this should re-check against a consolidated version once one is published.
- The Commission is required by the new Art. 2(13) to adopt delegated acts by 2 August 2027 specifying where Annex I Section A legislation can limit AI Act requirements [S2]. Whether any such act exists on 2026-08-28 was not checked; it does not bear on Annex III systems.
- The Commission's Guidelines on the Art. 50 transparency obligations, published 20 July 2026 [S6], were not read — only the page announcing them. Nor was the Code of Practice on transparency of AI-generated content, which the Commission found "adequately covers the obligations provided for in Articles 50(2), (4) and (5) AI Act" in an opinion published 9 July 2026 [S7]. If the Art. 50 rule ships, fetch https://digital-strategy.ec.europa.eu/en/policies/guidelines-transparency-ai-generated-content first: the Guidelines are what bounds the "obvious to a reasonably well-informed observer" exception, and therefore the fixture labels.

Assumption: the extension, if built, targets the state of the law on 2026-08-28 and says so in its own output header, because the December 2027 date is a deferral rather than a repeal and a document produced now will be read after it lapses.

## 2. The articles the extension would work from

Each file under `docs/research/sources/ai-act/` is verbatim OJ text with its amendment status in the header.

| File | Covers | Why the extension needs it |
|---|---|---|
| `art-03-definitions.md` | Art. 3(1) AI system, 3(3) provider, 3(4) deployer | The role split decides which obligations attach. A recruiting SaaS that builds its own scoring model is a provider; one that uses a third-party model under its own authority is a deployer; both roles can sit in one repo. |
| `art-06-classification.md` | Art. 6(1) to 6(3) | 6(2) is the Annex III route. 6(3) is the derogation with the profiling carve-out. |
| `annex-iii.md` | Annex III in full | The use-case list. Point 4 is employment; see §4. |
| `art-12-record-keeping.md` | Art. 12 | Logging duty. Art. 12(3)'s minimum log fields apply only to Annex III point 1(a) systems; everything else is governed by 12(1) and 12(2). |
| `art-14-human-oversight.md` | Art. 14 | 14(4)(d) is the override; 14(5) is the two-person rule for biometric identification. This is the article the verifier's approval-node check maps to. |
| `art-26-deployer-obligations.md` | Art. 26 in full | 26(2) named oversight persons with authority; 26(6) logs kept at least six months; 26(7) worker notification; 26(11) telling the affected person they are subject to the system. |
| `art-27-fria.md` | Art. 27(1) | Narrower than commonly assumed. See §5.6. |
| `art-50-transparency.md` | Art. 50 in full | The only article in this pack whose obligations are already applicable and that a call graph can evidence — Arts. 12, 14, 26 and 27 sit in Chapter III Sections 2 and 3, deferred to 2 December 2027. Also the one place where a string in the code comes close to direct evidence. |
| `art-99-penalties.md` | Art. 99(3) and (4) | 35 000 000 EUR / 7 % for Art. 5 breaches; 15 000 000 EUR / 3 % for the operator obligations in 99(4). |
| `art-113-application-dates.md` | Art. 113, original text | Superseded in part; read with the omnibus file. |
| `omnibus-2026-1744.md` | Reg. 2026/1744 recital (40) and the amendments to Arts. 6, 27, 50, 99, 111, 113 | The date arithmetic, and the list of what did not change. |

## 3. What code can evidence, and what it cannot

The line is the same one ADR 0002 already draws for GDPR: the tool reports what is in the call graph and refuses the legal cell. AMBIGUITIES row 8 applies unchanged.

### Evidenceable from static reads

| Signal | How it is found | What it supports | Limits |
|---|---|---|---|
| AI SDK call site | import of an inference client plus a call node; rule set as data, same shape as the GDPR recipient SDK list | "This repository calls a model at `x.py:NN`" | An import alone is not a call. Same discipline as AMBIGUITIES row 7. |
| Model output reaching a write about a person | dataflow-free, name-based path from the call site to an assignment or ORM write on a table already classified as holding personal data by the GDPR pass | "The model's output is stored on the candidate record at `y.py:NN`" | Name-based only. Dynamic dispatch and dict indirection become `unverified`, never `reaches`. |
| Approval node on the path | a function on the path whose name or decorator is in an approval rule set, or a status transition gated on a reviewer field | "The path from the model call to the write passes / does not pass through `approve_candidate` at `z.py:NN`" | Whether that function represents oversight by a competent person with authority (Art. 26(2)) is a human call. The tool reports the node, not its adequacy. |
| Inference logging with timestamps | a logging call on the same path carrying a timestamp and a request or subject identifier | "Inference calls are logged at `w.py:NN` with a timestamp" | Art. 12 asks for logs over the lifetime of the system, and Art. 26(6) for six months of retention. Retention lives in config, cron, or a cloud console — usually outside the repo. Report the write; mark retention `unverified` unless a timer literal is on the path, exactly as the GDPR pass already does for purge jobs. |
| Disclosure string near a chat endpoint | a string literal or template reachable from a route that also reaches a chat completion call | "A disclosure string is rendered on the path from `POST /chat` at `a.py:NN`" | Art. 50(1) turns on whether the person is informed, with an exception where it is obvious to a reasonably well-informed observer. Presence of a string is evidence; sufficiency is not a code fact, and the exception is bounded by the Commission's Art. 50 Guidelines [S6], which this pack has not read. |

### Human-only, never rendered by the tool

- Intended purpose. Art. 6(3)(a) to (d) all begin "the AI system is intended to…" — intent is declared by the provider, not readable from a call graph.
- Provider or deployer. Art. 3(3) turns on placing on the market or putting into service under one's own name or trademark. A repo cannot show a trademark.
- Annex III category. The tool can surface "this write updates `application.status`"; naming that as Annex III point 4(a) is a legal reading of the product, not of the code.
- Risk class. **The product must never state a risk class.** No "high-risk", no "not high-risk", no "out of scope", no "compliant". The cell renders `requires human completion`, and the row carries the code evidence next to it so a lawyer can decide in one pass. This is NON-GOALS, first slice-specific bullet, and it is the sentence with the most downside in the whole tool.
- Whether an approval node is genuine oversight under Art. 14 and Art. 26(2).
- Whether the deployer is a public body or provides a public service, which is what Art. 27(1) actually turns on.

## 4. Annex III and hiring

The hackathon organiser is a recruiting company. That is a fact about the audience, not a claim about their systems; nothing below describes any product of theirs, and the extension would be evaluated on planted synthetic cases exactly as the GDPR arm is.

Annex III point 4 is the entry that makes a recruiting product a candidate for the Annex III route [S1]:

> "4. Employment, workers' management and access to self-employment:
> (a) AI systems intended to be used for the recruitment or selection of natural persons, in particular to place targeted job advertisements, to analyse and filter job applications, and to evaluate candidates;
> (b) AI systems intended to be used to make decisions affecting terms of work-related relationships, the promotion or termination of work-related contractual relationships, to allocate tasks based on individual behaviour or personal traits or characteristics or to monitor and evaluate the performance and behaviour of persons in such relationships."

Two neighbouring entries can also be reached by a hiring or assessment product depending on what it does: point 3 (education and vocational training, including admission, evaluation of learning outcomes, and proctoring-style monitoring of prohibited behaviour during tests) and point 1 (biometrics, including emotion recognition), each in so far as permitted under Union or national law. The exact wording of all eight areas is in `sources/ai-act/annex-iii.md`.

Two things worth holding onto, both from Art. 6(3) [S1]:

- The derogation is available. A system doing a narrow procedural task, or improving the result of a previously completed human activity, or performing a preparatory task, can fall outside high-risk.
- The derogation has a hard floor: "Notwithstanding the first subparagraph, an AI system referred to in Annex III shall always be considered to be high-risk where the AI system performs profiling of natural persons." A ranking or scoring feature over candidates is the obvious place this bites, and it is exactly the kind of call the tool must not make on its own.

## 5. What this means for the extension

1. **The primary artifact changes shape, not machinery.** The AI Act extension is a second rule set over the same `path_exists` verifier, plus one table appended to the record. If it needs a new verifier, it is out of scope for the gate window.

2. **The verifier claim is one sentence and it is structural.** For every model call site *m* and every consequential write *w* about a natural person that is reachable from *m*, the claim under test is `path_exists(m, w, must_pass_through=approval_nodes)`. Concretely: `path_exists(entry=call_site, target=write_primitive, must_pass_through=approval_node_set)` returning false renders the row `no_human_approval_on_path`, with the call site and the write both cited `file:line`. Returning true renders `approval_node_on_path` and cites the node. An unresolvable edge renders `unverified` and counts as *not* passing through approval, mirroring AMBIGUITIES row 14 — guessing towards safety is the failure mode the whole project exists to prevent.

3. **The false-safe row transfers directly.** In the GDPR arm a false safe is "agent says erased, code says no". Here it is "agent says a human approves, code says the write happens unconditionally". Same must-be-zero secondary, same reason.

4. **Article 50 is the only rule here with a date that has already passed, and the cheapest to plant cases for.** A chat endpoint with no disclosure string on the path is a one-file synthetic fixture, the verdict is binary, and the date is 2 August 2026, already past. If the gate opens late and only one rule fits, this is the one that ships.

5. **Logging is two claims, not one.** Whether inference calls are logged with a timestamp is a call-graph fact. Whether those logs are kept for the period Art. 26(6) requires is almost never in the repo. Split the row: `logged: yes (file:line)` and `retention: unverified`. Merging them produces the drift the GDPR arm was built to catch.

6. **Do not put a FRIA row in the output for a private-sector product without reading Art. 27(1).** The duty falls on "deployers that are bodies governed by public law, or are private entities providing public services, and deployers of high-risk AI systems referred to in points 5 (b) and (c) of Annex III" [S1] — creditworthiness and life or health insurance pricing. A private recruiting company deploying an Annex III point 4 system is not in that list on the face of the text. Whether it provides a public service is a human determination; the cell renders `requires human completion` with the article quoted next to it.

7. **Every AI Act row carries a date stamp.** The record must print "law as at 2026-08-28; Annex III obligations apply from 2 December 2027 (Reg. (EU) 2026/1744)". A record with no date is worse than no record once the deferral lapses.

8. **Kill criterion, stated before building.** The extension is one changelog iteration. If it cannot be evaluated on planted cases, or it does not move a metric, it is removed and the CHANGELOG_EVAL row stays with the negative result — NON-GOALS already commits to this. Two or three synthetic fixtures are enough to decide: one with an approval node on the path, one with the approval function defined and never called (the S10 shape, transplanted), one chat endpoint with and without a disclosure string.

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S1 | Regulation (EU) 2024/1689 (Artificial Intelligence Act), OJ L, 2024/1689, 12.7.2024, EN | http://publications.europa.eu/resource/cellar/dc8116a1-3fe6-11ef-865a-01aa75ed71a1.0006.03/DOC_1 (ELI: http://data.europa.eu/eli/reg/2024/1689/oj) | 2026-08-28 | Verbatim text of Arts. 3, 6, 12, 14, 26, 27, 50, 99, 113 and Annex III |
| S2 | Regulation (EU) 2026/1744 (Digital Omnibus on AI), OJ L, 2026/1744, 24.7.2026, EN | http://publications.europa.eu/resource/cellar/b459c07f-86fb-11f1-bf5e-01aa75ed71a1.0006.03/DOC_1 (ELI: http://data.europa.eu/eli/reg/2026/1744/oj) | 2026-08-28 | Adoption status, entry into force, the new Art. 113 dates, Art. 111(4), the full amendment inventory |
| S3 | European Commission, "AI Act \| Shaping Europe's digital future" | https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai | 2026-08-28 | Independent confirmation of 2 December 2027 / 2 August 2028 and of the August 2026 transparency date |
| S4 | Cooley, "Digital AI Omnibus Delays Key Deadlines, Introduces New Rules", cyber/data/privacy insights | https://cdp.cooley.com/digital-ai-omnibus-delays-key-deadlines-introduces-new-rules/ | 2026-08-28 | Post-publication analysis: publication 24 July 2026, in force 27 July 2026, Art. 50 unaffected. Checked today for the conditional trigger: the page does not carry it. |
| S5 | Gibson Dunn, "EU AI Act Omnibus Agreement — Postponed High-Risk Deadlines and Other Key Changes" (dated 27 May 2026, written before publication) | https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/ | 2026-08-28 | The fixed dates replacing the proposed conditional delay mechanism (§1); corroboration that Art. 50 stays on 2 August 2026 and that the Art. 50(2) grace period runs to 2 December 2026 |
| S6 | European Commission, "Guidelines on transparency obligations for providers and deployers of AI systems" (Publication 20 July 2026) | https://digital-strategy.ec.europa.eu/en/library/guidelines-transparency-obligations-providers-and-deployers-ai-systems | 2026-08-28 | Existence and date of the final Art. 50 Guidelines; named as unread in §1 and §3 |
| S7 | European Commission, "Commission opinion on the assessment of the Code of Practice on Transparency of AI-generated Content" (Publication 9 July 2026) | https://digital-strategy.ec.europa.eu/en/library/commission-opinion-assessment-code-practice-transparency-ai-generated-content | 2026-08-28 | The adequacy finding for Art. 50(2), (4) and (5) |
