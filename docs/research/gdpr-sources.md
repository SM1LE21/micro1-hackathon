# GDPR sources for the Art. 30 record and the erasure-path table

Research input for ADR 0002. What the law actually requires of the artifact the agent
produces, which of those requirements a static reader of Python can evidence, and which
ones must stay human-only. Also the enforcement and regulator material the README's "why
it matters" paragraph cites.

Written 2026-08-28. Every quote below was fetched on that date; the fetch method is
recorded per source in the Sources table at the bottom. Verbatim article texts live in
`docs/research/sources/gdpr/`, one file per article, each with its own header line.

**Assumption:** the user of this tool is a **controller** within Art. 4(7). Processor-side
records under Art. 30(2) are out of scope. A controller who also acts as a processor for
someone else needs a second record: CNIL says the register *"doit donc clairement distinguer
les deux catégories d’activités"* and, in that case, *"la CNIL vous recommande de tenir 2
registres"* [S6]. The tool does not produce the processor half and says so.

**Assumption:** nothing here is legal advice and the tool never renders a legal conclusion.
The sources decide what the *schema* looks like, not what any given cell should say.

---

## 1. The primary text

Files under `docs/research/sources/gdpr/`. EUR-Lex served an AWS WAF JavaScript challenge
to every non-browser client tried on 2026-08-28 (HTTP 202 with a `challenge.js` body, three
URL forms). The texts were taken instead from the Publications Office cellar copy of the
same CELEX document, `http://publications.europa.eu/resource/celex/32016R0679` with
`Accept: application/xhtml+xml` and `Accept-Language: eng`, which is the authenticated OJ
text EUR-Lex itself renders [S1]. Each file records that.

| File | Contains | Why it is in the pile |
|---|---|---|
| `art-04-definitions.md` | Art. 4(1),(2),(5),(7),(8),(9),(10) | (1) fixes what counts as personal data, which is AMBIGUITIES row 1. (9) and (10) separate *recipient* from *third party*, which decides how the SDK-call column is labelled. (5) defines pseudonymisation, which is what a hashed email is. (8) makes a processor a recipient. |
| `art-05-principles.md` | Art. 5(1)(e), 5(2) | (e) is storage limitation, the principle a stale retention timer breaches. (2) is accountability: the controller must be *able to demonstrate* compliance, which is the whole argument for a code-derived record. |
| `art-15-access.md` | Art. 15, full | A non-goal. Kept so the boundary is checkable rather than asserted. |
| `art-17-erasure.md` | Art. 17, full | The obligation the erasure-path table is about. 17(1) is "erase personal data without undue delay"; 17(3) lists what survives the request. |
| `art-28-processor.md` | Art. 28(3) with (a)-(h) | (g) is the reason an external store gets `external_manual` and not `not_erased`. |
| `art-30-records.md` | Art. 30, full | The output schema. |
| `art-32-security.md` | Art. 32(1) with (a)-(d) | Art. 30(1)(g) points here by reference, so this is the closed list the security cell draws from. |
| `art-44-transfers.md` | Art. 44, first paragraph | Recipients in third countries, Art. 30(1)(e). |
| `recitals-13-26-39-65-66.md` | Recitals 13, 26, 39, 65, 66 | 13 is the SME derogation's stated motive. 26 is the anonymisation line §3.2 turns on. 39 is where "time limits should be established by the controller for erasure or for a periodic review" comes from. 65 and 66 are the right to be forgotten. |

Three lines from the text do more work than the rest.

Art. 30(1)(f): *"where possible, the envisaged time limits for erasure of the different
categories of data"* [S1]. Note **envisaged** and **where possible**. The record asks for an
intention per category of data, not a proof of deletion. The erasure-path table is a
separate artifact that the Regulation does not require and that the founder needs anyway.

Art. 30(3): *"The records referred to in paragraphs 1 and 2 shall be in writing, including
in electronic form."* [S1] Markdown plus validated JSON satisfies the form requirement.
NON-GOALS already rules out DOCX and PDF; this is why that costs nothing.

Recital 39: *"In order to ensure that the personal data are not kept longer than necessary,
time limits should be established by the controller for erasure or for a periodic
review."* [S1] A periodic review is an alternative to a timer. A repository with no purge
job is not automatically in breach, which is the reason the tool reports a verdict and never
the word "compliant".

---

## 2. What the regulators think a record looks like

### 2.1 ICO (UK). Caveat: UK GDPR

The ICO's guidance is written against the UK GDPR, not Regulation 2016/679. The (a)-(g) list
in Art. 30(1) is carried over unchanged apart from (g), which gains *"or, as appropriate, the
security measures referred to in section 28(3) of the 2018 Act"*, and Art. 30(4), where
*"the Commissioner"* replaces the supervisory authority [S21]. The template's extra columns
(the Schedule 1 condition, the retention and erasure policy-document columns) come from the
Data Protection Act 2018 rather than from Art. 30, which the workbook's own Notes sheet says
[S3]. It is still the most concrete column-by-column artifact any authority publishes, so it
is used here as a *shape* reference, not as authority on EU law. The ICO says as much about
its own EDPB links: *"EDPB guidelines are no longer directly relevant to the UK regime and
are not binding under the UK regime."* [S2]

The ICO's controller list [S2] tracks Art. 30(1) item for item, with one addition worth
noticing: it splits (a) into four separate rows (organisation, DPO, joint controllers,
representative), and it glosses (f) as *"the retention schedules for the different
categories of personal data - how long you will keep the data for. This may be set by
internal policies or based on industry guidelines, for instance."* [S2] A retention schedule
is a policy document, not a `timedelta`. The tool's retention cell therefore reports the
timer it found in code as *evidence for* the schedule, never as the schedule.

The ICO's controller template [S3] is an .xlsx. Sheet `Template`, row 9, columns A to AD,
verbatim and in order:

1. Business function
2. Purpose of processing
3. Name and contact details of joint controller (if applicable)
4. Categories of individuals
5. Categories of personal data
6. Categories of recipients
7. Link to contract with processor
8. Names of third countries or international organisations that personal data are transferred to (if applicable)
9. Safeguards for exceptional transfers of personal data to third countries or international organisations (if applicable)
10. Retention schedule (if possible)
11. General description of technical and organisational security measures (if possible)
12. Article 6 lawful basis for processing personal data
13. Article 9 condition for processing special category data
14. Legitimate interests for the processing (if applicable)
15. Link to record of legitimate interests assessment (if applicable)
16. Rights available to individuals
17. Existence of automated decision-making, including profiling (if applicable)
18. The source of the personal data (if applicable)
19. Link to record of consent
20. Location of personal data
21. Data Protection Impact Assessment required?
22. Data Protection Impact Assessment progress
23. Link to Data Protection Impact Assessment
24. Has a personal data breach occurred?
25. Link to record of personal data breach
26. Data Protection Act 2018 Schedule 1 Condition for processing
27. GDPR Article 6 lawful basis for processing
28. Link to retention and erasure policy document
29. Is personal data retained and erased in accordance with the policy document?
30. Reasons for not adhering to policy document (if applicable)

Rows 1-6 of the same sheet carry the controller, DPO and representative contact block
(Name / Address / Email / Telephone), which is Art. 30(1)(a). The `Notes` sheet distinguishes
the two kinds of column: *"Headings highlighted green are required areas of documentation
under Article 30 of the GDPR or Schedule 1 of the Data Protection Act 2018. Headings
highlighted blue are optional areas of documentation that are not required under Article 30
of the GDPR or Schedule 1 of the Data Protection Act 2018."* [S3]

Two of those columns are worth stealing. **Column 20, "Location of personal data"**, is the
closest thing in any official template to what this tool actually produces, and it is one of
the optional ones. **Column 29, "Is personal data retained and erased in accordance with the
policy document?"**, is the erasure-path table's question, asked by a regulator, and left as
a free-text cell for a human to assert. That cell is the product.

The ICO also states the templates are *"not mandatory"* and that *"you should treat the record
as a living document that you update as and when necessary"* [S4]. Drift is the assumed
failure mode, not an edge case.

### 2.2 CNIL (France)

CNIL's page on the register lists the per-activity fields and matches Art. 30(1) with one
gloss on (f): *"les délais prévus pour l'effacement des différentes catégories de données,
c'est-à-dire la durée de conservation, ou à défaut les critères permettant de la
déterminer"* [S6] (the time limits for erasure of the different categories of data, that is
to say the retention period, or failing that the criteria for determining it). "Or failing
that, the criteria" is the escape hatch the tool needs when a repository has no numeric
timer.

CNIL is explicit on form: *"Le RGPD impose uniquement que le registre se présente sous une
forme écrite. Le format du registre est libre et peut être constitué au format papier ou
électronique."* [S6]

The **registre de base** model [S4b] is a per-activity fiche, not a spreadsheet row. Its
sections, in document order:

- Nom de l'activité; date de création de la fiche; date de dernière mise à jour; nom du responsable conjoint du traitement; nom du logiciel ou de l'application (si pertinent)
- Objectifs poursuivis
- Catégories de personnes concernées
- Catégories de données collectées, as checkboxes: État-civil, identité, données d'identification, images · Vie personnelle · Vie professionnelle · Informations d'ordre économique et financier · Données de connexion (ex. adresses Ip, logs, identifiants des terminaux, identifiants de connexion, informations d'horodatage) · Données de localisation · Internet (cookies, traceurs, données de navigation, mesures d'audience) · Autres catégories de données
- Des données sensibles sont-elles traitées ? (Oui / Non, then which)
- Durées de conservation des catégories de données, entered as Jours / Mois / Ans / Autre durée, with: *"Si vous ne pouvez pas indiquer une durée chiffrée, précisez les critères utilisés pour déterminer le délai d'effacement (par exemple, 3 ans à compter de la fin de la relation contractuelle)."* and *"Si les catégories de données ne sont pas soumises aux mêmes durées de conservation, ces différentes durées doivent apparaître dans le registre."* [S4b]
- Catégories de destinataires des données, split three ways: **Destinataires internes** · **Organismes externes** (filiales, partenaires) · **Sous-traitants** (hébergeurs, prestataires et maintenance informatiques)
- Transferts des données hors UE (Oui / Non, then which countries)
- Mesures de sécurité, as checkboxes: Contrôle d'accès des utilisateurs · Mesures de traçabilité · Mesures de protection des logiciels · Sauvegarde des données · Chiffrement des données · Contrôle des sous-traitants · Autres mesures

Four things in that list matter for the schema. Retention is entered **per category of
data**, not per activity, so a store with two retention regimes needs two rows. Recipients
are split into internal, external and **sous-traitants**, which is the split a code reader
can partly make: an outbound SDK call is either an external organism or a processor, and the
code cannot tell which. "Nom du logiciel ou de l'application" is a per-activity field with no
Art. 30 equivalent, which is where a repository name belongs. And **Sauvegarde des données**
is listed as a *security measure*, which is the cleanest justification for AMBIGUITIES row 6:
in CNIL's own model, backups sit under Art. 32, not under the erasure timer.

The older simplified ODS workbook [S5] is still linked from the same page and adds a
`5 - Listes` sheet of dropdown values, including a `Destinataires` list whose entries are
"Service interne qui traite les données", "Sous-traitants", "Destinataires dans des pays
tiers ou organisations internationales", "Partenaires institutionnels ou commerciaux",
"Autre (Préciser)". That is a usable closed vocabulary for the recipient-kind field. The
same workbook's `Garanties` list still offers `Privacy shield` and its country list still
marks `Etats-Unis` as `adéquat`, so it predates *Schrems II*; the vocabulary is worth borrowing, the adequacy data is not.

### 2.3 CNPD (Luxembourg)

The author is in Luxembourg, so the CNPD is the authority that would ask. Its page on
records restates Art. 30(1) verbatim and then says something useful about templates:

> *"The GDPR does not define a unique template or format for the records of processing
> activities. Each controller or processor may therefore use any format, provided that the
> information referred to in article 30 of the GDPR is included. In addition, the data
> protection authorities of France, Belgium and Bavaria also provide a model for the register
> of processing activities."* [S7]

and:

> *"However, you should be aware that none of these models cover all possible situations. It
> is therefore possible, or even recommended, to modify one of these models or create a new
> one to take into account the specific context and particularities of your
> organization."* [S7]

The CNPD publishes no controller template of its own for general business. It publishes one
worked example for associations [S8], a landscape table whose column headers are:
Finalité · Catégories de personnes concernées · Catégories de données traitées · Catégories
de destinataires · Transferts vers des pays tiers · Délais prévus pour l'effacement des
données · Mesures de sécurité organisationnelles et techniques. Seven columns, Art. 30(1)(b)
through (g), with (a) hoisted into a header line above the table. That is the minimum honest
shape and it is what the tool's Markdown render should look like.

### 2.4 Whether a small SaaS is exempt at all: Art. 30(5)

Art. 30(5) exempts organisations under 250 persons unless any of three conditions holds. The
WP29 position paper of 19 April 2018, endorsed by the EDPB, kills the exemption for anyone
running a product:

> *"The WP29 underlines that the wording of Article 30(5) is clear in providing that the three
> types of processing to which the derogation does not apply are alternative ("or") and the
> occurrence of any one of them alone triggers the obligation to maintain the record of
> processing activities."* [S9]

and, in the footnote that defines the term:

> *"The WP29 considers that a processing activity can only be considered as "occasional" if it
> is not carried out regularly, and occurs outside the regular course of business or activity
> of the controller or processor."* [S9]

CNIL puts the same point in one sentence: *"En pratique, cette dérogation est donc limitée à
des cas très particuliers de traitements, mis en œuvre de manière occasionnelle et non
routinière"* [S6]. A SaaS with user accounts processes personal data as its regular course of
business. It is in scope. The paper also softens the burden in a way worth quoting in the
README: *"such organisations need only maintain records of processing activities for the
types of processing mentioned by Article 30(5)"* [S9], and *"For many micro, small and
medium-sized organisations, maintaining a record of processing activities is unlikely to
constitute a particularly heavy burden."* [S9] The burden is not writing the document. The
burden is knowing whether it is true.

One caveat on currency rather than content. The Commission's fourth simplification Omnibus
proposes to raise the threshold to 750 persons and to replace the three triggers with a single
high-risk test. EDPB and EDPS, announcing their joint opinion of 9 July 2025: *"Under the
Proposal, the derogation would apply to an enterprise or organisation employing fewer than 750
people, unless the processing operation carried out is likely to result in a high risk to
individuals’ rights and freedoms, within the meaning of Art.35 GDPR."* [S20] That is a
proposal. **Assumption:** no such amendment had entered into force by 2026-08-28, so the
250-person text quoted above is the one that binds; if it is adopted, this section has to be
re-run against a 750-person threshold and an Art. 35 test, and the answer for a SaaS holding
account data may not change anyway.

---

## 3. Erasure against backups, and anonymisation as a substitute

These two decide AMBIGUITIES rows 5 and 6.

### 3.1 Backups (row 6)

ICO, on the right to erasure [S10]:

> *"If a valid erasure request is received and no exemption applies then you will have to take
> steps to ensure erasure from backup systems as well as live systems. Those steps will depend
> on your particular circumstances, your retention schedule (particularly in the context of its
> backups), and the technical mechanisms that are available to you."* [S10]

> *"The key issue is to put the backup data 'beyond use', even if it cannot be immediately
> overwritten. You must ensure that you do not use the data within the backup for any other
> purpose, ie that the backup is simply held on your systems until it is replaced in line with
> an established schedule. Provided this is the case it may be unlikely that the retention of
> personal data within the backup would pose a significant risk, although this will be context
> specific."* [S10]

The EDPB's coordinated enforcement report on the right to erasure, adopted 10 February 2026
after 32 supervisory authorities questioned 764 controllers through 2025 [S11]:

> *"Depending on the technical settings and risks, it might not always be advisable to modify or
> delete information from back-ups. But, in that case, organisations should have appropriate
> procedures to keep track of erasure requests and comply with them on restored systems, as much
> as possible, in case of a data breach affecting the integrity of the organisation's
> system."* [S11]

> *"Half of the responding SAs raised concerns regarding the deletion of personal data in this
> context. Many controllers were found not to have specific procedures and measures in place to
> handle erasure requests in the context of back-ups, relying either on automatic deletion
> measures (not specific to the erasure requests received) or on the implementation of retention
> periods applicable to the concerned back-ups."* [S11]

and, on scope:

> *"More generally, many controllers also excluded back-up data by default, without providing a
> justification for doing so."* [S11]

CNIL's own national write-up of the same action puts backups next to retention periods as the
two things controllers could not do: *"Les autorités ont également relevé des difficultés
rencontrées par certains responsables de traitement pour déterminer les durées de conservation ou
supprimer les données personnelles des sauvegardes réalisées."* [S13] (The authorities also noted
difficulties encountered by certain controllers in determining retention periods or deleting
personal data from the backups they had made.)

The EDPB's recommendation on retention lands in the record itself: *"Controllers: When documenting
retention periods for instance in the records of processing activities, clearly specify any
applicable legal obligations justifying the retention of personal data for a defined
period."* [S11] The retention cell wants a citation to law next to the number, and the tool can
supply neither. It supplies the number's location in code and leaves the justification empty.

Both authorities treat a backup as governed by its retention schedule and by procedure, not by
an immediate deletion call. Neither says the backup is out of scope. **AMBIGUITIES row 6 holds
as written**: backups are inventoried as a store with a retention timer, and none of the
`erased` / `not_erased` verdicts is rendered for them. Instead of leaving the cell blank, the
row renders `governed_by_retention` with the backup's schedule if one is found in code (cron
expression, lifecycle policy, `RETENTION_DAYS`), and `no_schedule_evidenced` otherwise. The
second value is a real finding: the EDPB found controllers relying on schedules that did not
exist.

Both labels map to `reaches_erasure=false` in the CASES.md tuple. That is the conservative
side: a backup store the agent claims is erased is then a false safe, which is the row that
must be zero. CASES.md currently lists the false side as `not_erased`, `external_manual`,
`no_entry_point`, `unverified`, so the two labels need an errata line there before the scorer
is written. Without it, a backup store with fields yields tuples the scorer cannot classify.

### 3.2 Anonymisation (row 5)

Recital 26 of the GDPR draws the line [S1]:

> *"The principles of data protection should therefore not apply to anonymous information,
> namely information which does not relate to an identified or identifiable natural person or to
> personal data rendered anonymous in such a manner that the data subject is not or no longer
> identifiable. This Regulation does not therefore concern the processing of such anonymous
> information, including for statistical or research purposes."* [S1]

WP29 Opinion 05/2014 on anonymisation techniques [S12]:

> *"Once a dataset is truly anonymised and individuals are no longer identifiable, European data
> protection law no longer applies."* [S12]

> *"An important factor is that the processing must be irreversible."* [S12]

> *"First, anonymisation is a technique applied to personal data in order to achieve irreversible
> de-identification."* [S12]

The same opinion warns against the failure mode a code reader will actually meet, using the AOL
release as the example: *"A typical instance of the misconceptions surrounding pseudonymisation
is provided by the well-known "AOL (America On Line) incident"."* [S12] Replacing a name with an
opaque ID is pseudonymisation, which Art. 4(5) defines as processing that is reversible with
additional information. It is not erasure.

The EDPB found this exact substitution happening in the field [S11]:

> *"A common practice among responding controllers is relying upon anonymisation as a substitute
> for a permanent deletion of personal data."* [S11]

> *"Multiple SAs found that controllers relying on anonymisation for deletion have various degrees
> of success in correctly implementing it. For example, in some cases, they only apply basic
> pseudonymisation or partial masking, although such a process would not fulfil the requirements
> of the GDPR regarding deletion."* [S11]

**AMBIGUITIES row 5 needs a split.** The row currently says anonymisation counts as reaching
erasure if every personal-data field on the path is overwritten irreversibly, flagged
`anonymised`. That is right, and the verifier needs a second verdict to sit next to it. Three
cases, distinguishable by static reading:

- every personal-data field on the store is overwritten with a constant or a non-reversible
  value, and no key linking back to the subject survives: `anonymised`, counts as reaching erasure
- fields are replaced by a hash, a token, a UUID, or an `xxxx`-style mask, or a foreign key to
  the user row survives: `pseudonymised`, maps to `reaches_erasure=false`, and counts as a
  false safe whenever the agent predicted true
- the code calls something named `anonymize_*` but the verifier cannot see what it writes:
  `unverified`, per AMBIGUITIES row 14

The middle case is the one that gets a founder fined, and it is a grep-able idiom
(`hashlib.sha256(user.email)`, `user.email = f"deleted-{user.id}@example.com"`). Worth a
planted synthetic case.

---

## 4. Enforcement: four published decisions

Cases located through enforcementtracker.com [S19], then read at the authority's own source.
Amounts, authorities and dates are from those sources.

| # | Amount | Authority | Date | Subject | Source |
|---|---|---|---|---|---|
| 1 | ~EUR 14,500,000 | Berliner Beauftragte für Datenschutz und Informationsfreiheit (Berlin) | 30 Oct 2019 | Archive system with no facility to remove tenant data that was no longer needed | [S14] |
| 2 | EUR 2,600,000 | Garante per la protezione dei dati personali (Italy) | 10 Jun 2021 | Record of processing omitted data categories the inspection found in the systems, and had no description of security measures | [S16] |
| 3 | EUR 1,100,000 | Landesbeauftragte für den Datenschutz Niedersachsen (Germany) | 26 Jul 2022 | Record of processing missing the technical and organisational measures entry (one of four breaches in a single fine) | [S17] |
| 4 | EUR 500,000 (EUR 300,000 GDPR) | CNIL (France) | 14 Jun 2021 | Deletion requests answered by deactivating the account instead of erasing the data | [S18] |

**1. Deutsche Wohnen SE, Berlin, 30 October 2019, ~EUR 14.5m.** The Berlin authority's own
press release [S14]:

> *"Bei Vor-Ort-Prüfungen im Juni 2017 und im März 2019 hat die Aufsichtsbehörde festgestellt,
> dass das Unternehmen für die Speicherung personenbezogener Daten von Mieterinnen und Mietern
> ein Archivsystem verwendete, das keine Möglichkeit vorsah, nicht mehr erforderliche Daten zu
> entfernen."* [S14]

(At on-site inspections in June 2017 and March 2019 the authority established that the company
used, for storing tenants' personal data, an archive system that provided no facility to remove
data that was no longer needed.) A system that cannot delete is the erasure-path table's whole
subject. **State the status honestly:** the fine was challenged, the Kammergericht Berlin
referred questions to the Court of Justice, and the CJEU ruled on 5 December 2023 in
C-807/21. The Court's press release describes the case as still contested at that point:
*"the real estate company Deutsche Wohnen, which indirectly holds approximately 163 000 housing
units and 3 000 commercial units, is contesting, inter alia, a fine of over € 14 million which
has been imposed on it as a result of its having stored the personal data of tenants for longer
than necessary."* [S15] Cite it as an issued fine under challenge, never as a final one.

**2. Foodinho s.r.l., Garante, 10 June 2021, EUR 2.6m.** The most useful decision on this list,
because the finding is *drift between the register and the systems*. The Garante inspected, then
compared what the systems processed against what the register said. From the decision [S16]:

> *"non risultano indicate talune tipologie di dati personali, il cui trattamento è stato
> accertato nel corso delle attività di controllo. In particolare, non sono elencati i dati
> relativi alle comunicazioni intercorrenti tra i rider e il customer care attraverso chat ed
> email nonché i dati c.d. esterni delle telefonate e la possibilità di accedere al contenuto
> delle stesse, né i dati utilizzati nell'ambito del c.d. sistema d'eccellenza e gli specifici
> dati relativi ai dettagli degli ordini rilevati attraverso l'app."* [S16]

(Certain categories of personal data are not shown, whose processing was established in the
course of the inspection. In particular, the data relating to communications between riders and
customer care through chat and email are not listed, nor the so-called external telephone-call
data and the possibility of accessing their content, nor the data used in the so-called
excellence system and the specific data on order details captured through the app.)

On the security cell:

> *"Il Registro, infine, non contiene la descrizione generale delle misure di sicurezza tecniche
> ed organizzative di cui all'articolo 32, paragrafo 1 del Regolamento (come previsto dall'art.
> 30, par. 1, lett. g) del Regolamento stesso)."* [S16]

The conclusion names the sub-points:

> *"Per i suesposti motivi la società, pertanto, ha violato l'art. 30, par. 1, lett. a), b), c),
> f), g) relativamente alle modalità di redazione e tenuta del registro"* [S16]

The company argued its chat logs, call metadata, scores and order details were not personal
data at all. The Garante disagreed, because each was linkable to a named rider. That argument is
exactly AMBIGUITIES row 1, and it was lost by the controller.

The Garante also refused to let an updated register cure the problem in full, and stated why
the register is not a formality:

> *"Ciò considerato che la tenuta del registro non costituisce un adempimento formale bensì
> parte integrante di un sistema di corretta gestione dei trattamenti dei dati personali
> effettuati."* [S16]

**3. Volkswagen AG, LfD Niedersachsen, 26 July 2022, EUR 1.1m.** One of the four breaches this
single fine covers is an empty Art. 30(1)(g) cell [S17]:

> *"Schließlich fehlte eine Erläuterung der technischen und organisatorischen Schutzmaßnahmen im
> Verzeichnis der Verarbeitungstätigkeiten, was einen Verstoß gegen die Dokumentationspflichten
> nach Artikel 30 DS-GVO darstellte."* [S17]

(Finally, an explanation of the technical and organisational protective measures was missing
from the record of processing activities, which constituted a breach of the documentation
obligations under Article 30 GDPR.)

The other three are missing Art. 13 camera signage on the test vehicle, no Art. 28 processor
contract with the company that carried out the drives, and no Art. 35 DPIA. The release closes:
*"Diese vier Verstöße mit jeweils niedrigem Schweregrad, von denen keiner weiterhin andauert,
sind Gegenstand des Bußgeldbescheides."* [S17] (These four breaches, each of low severity, none
of them still ongoing, are the subject of the fine notice.) The decision shows the cell is
chargeable under Art. 30. It does not show the cell carrying a fine on its own, and the README
sentence has to say four.

**4. Brico Privé, CNIL deliberation SAN-2021-008, 14 June 2021, EUR 500,000.** Soft delete,
found and fined:

> *"lorsqu'une personne demande l'effacement de son compte, la société ne supprime pas les
> données à caractère personnel mais procède uniquement à la désactivation du compte en
> question"* [S18]

(when a person requests the erasure of their account, the company does not delete the personal
data but only deactivates the account in question.)

That sentence is synthetic case S02. The operative part splits the amount: *"une amende
administrative d'un montant de 500 000 (cinq cent mille) euros, qui se décompose comme suit :
300 000 (trois cent mille) euros pour les manquements aux articles 5-1-e), 13, 17 et 32 du
règlement (UE) 2016/679 [...] ; 200 000 (deux cent mille) euros pour les manquements à
l'article 82 de la loi no 78-17 du 6 janvier 1978 [...] et à l'article L. 34-5 du code des
postes et des communications électroniques"* [S18]. EUR 300,000 for the four GDPR breaches,
EUR 200,000 under French law that is not the GDPR. The round number without the split
overstates what Art. 17 cost this company.

Direct retrieval of the Legifrance page failed twice with HTTP 403 for a scripted client; the
quote above was read from the same URL through the WebFetch tool, which reaches it. Recorded so
nobody re-runs curl and thinks the source is dead.

---

## 5. Art. 30(1)(a) to (g): what code can evidence, what only a human can supply

The column that matters is the third one. Everything in it is a claim the verifier must be able
to check against an AST, or it does not belong in the agent's half of the record.

| Item | Art. 30(1) item (abridged) | What static Python analysis can evidence | What only a human can supply | Cell behaviour |
|---|---|---|---|---|
| (a) | name and contact details of the controller, joint controller, representative, DPO | Nothing. A company name in `settings.py` or a `MANIFEST` is a string, not an identity. | All of it. Legal entity, address, whether there is a joint controller, whether a DPO was designated under Art. 37. | Always `requires human completion`. Never suggested. |
| (b) | the purposes of the processing | Nothing that can be verified. A module named `marketing/` or a function `send_promo_email` is a hint, and a hint is how a wrong legal basis gets written. | All of it. AMBIGUITIES row 8. | `requires human completion`, with an optional `observed_module_names` field that is explicitly labelled as not a purpose. |
| (c) | a description of the categories of data subjects and of the categories of personal data | **Categories of personal data: yes.** Field names, ORM column types, JSON blob keys, and the store each lives in, each with `file:line`. Four of the six CASES.md field categories land on a CNIL box (`identifier` and `contact` → État-civil, identité; `financial` → Informations d'ordre économique et financier; `technical` → Données de connexion); `behavioural` fits Internet only partly and `free_text_may_contain` has no box at all, so both render under Autres catégories de données [S4b]. **Categories of data subjects: partly.** A model named `User`, `Customer`, `Employee`, `Rider` is evidence; a shared `Person` table serving three roles is not. | Confirmation of the subject categories, and any category of data held outside the codebase (paper, email inboxes, spreadsheets, a CRM nobody committed). | Fully populated from code with citations. Data-subject categories rendered as `inferred from model name`, human-confirmable at the gate. |
| (d) | the categories of recipients to whom the personal data have been or will be disclosed including recipients in third countries or international organisations | **Yes, as the tool's second headline output.** An outbound SDK call with a personal-data field flowing into it: the Stripe customer create with `email=user.email`, the analytics event, the mail send, the error tracker's `sentry_sdk.set_user({"email": ...})` [S23]. `file:line` for the call and for the field. Art. 4(9) makes these recipients; Art. 4(8) makes the ones acting on instructions processors. | Which recipient is a **processor** and which is an independent controller. Whether a Art. 28(3) contract exists. The recipient's legal name and country. Any recipient the code never touches (an accountant, a payroll provider). | Populated from code as `recipient_candidates` with the evidence line, plus a `kind` field left `unknown` for the human to set to internal / processor / external controller, using the CNIL vocabulary [S5]. |
| (e) | where applicable, transfers of personal data to a third country or an international organisation, including the identification of that third country, and, for Art. 49(1) second subparagraph transfers, the documentation of suitable safeguards | Weak evidence only. A region string (`eu-central-1`, `us-east-1`), a hardcoded API host, a bucket's region in config. This tells you where a *service* is, not where the *processing* is, and it says nothing about the legal basis for the transfer. Art. 44 makes the whole chapter apply including onward transfers, which no static reader can see. | Everything decisive. Whether a transfer occurs, to which country, and under which safeguard (adequacy decision, SCCs, BCRs, an Art. 49 derogation). | `requires human completion`, with an `observed_region_hints` field carrying the raw strings and their `file:line`, marked as not a transfer finding. |
| (f) | where possible, the envisaged time limits for erasure of the different categories of data | **Yes, where a timer exists in code.** A purge job's `timedelta(days=N)` or cutoff arithmetic, a cache TTL, an S3 lifecycle rule in committed config, a `RETENTION_DAYS` constant, a cron schedule. Cited per store, per field category where the code distinguishes them (CNIL requires the split [S4b]). | The retention *policy*: the legal or business justification for the number, and a limit for every category where the code has no timer. ICO calls this a retention schedule set by internal policy or industry guidelines [S2]. EDPB Issue 5 recommends recording the legal obligation next to the period [S11]. | Populated where evidenced, `no_timer_evidenced` otherwise. The tool never invents a number and never calls an absent timer a breach. |
| (g) | where possible, a general description of the technical and organisational security measures referred to in Article 32(1) | **Partly, and only the technical half.** Art. 32(1)(a) names pseudonymisation and encryption: `SECURE_SSL_REDIRECT`, of which Django's settings reference says *"If True, the SecurityMiddleware redirects all non-HTTPS requests to HTTPS"* [S22]; a bucket's `ServerSideEncryptionConfiguration` [S24]; a password hasher setting; an encrypted-field wrapper or an `ssl_require` database option, both third-party idioms seeded into the rule set from the fixtures rather than from vendor docs; a committed backup configuration. Art. 32(1)(c) restoration and (d) regular testing are process, invisible to a reader of application code. | Access control practice, staff training, the sub-processor review, the testing regime, incident response. The organisational half in full. | Populated with the technical measures found, each cited, under a heading that says the list is partial and covers Art. 32(1)(a) only. The rest `requires human completion`. Cases 2 and 3 above are fines that counted this cell being empty. |

Not an Art. 30 item, and the reason the tool exists:

| Extra | What it is | Source of the idea |
|---|---|---|
| Erasure path per store | For every store holding personal data, whether a static call path exists from the erasure entry point to a deletion primitive for that store, with `file:line`, or a verdict saying why not. | Art. 17(1); ICO's "Is personal data retained and erased in accordance with the policy document?" column [S3]; EDPB Issue 6 and the account-closure finding [S11]. |

---

## 6. What this means for the product

1. **The unit of the record is a processing activity, not a table.** CNIL's model is a fiche per
   activity; the CNPD example is one row per activity; the ICO template's first column is
   "Business function". Code gives stores and fields. Grouping them into activities is human
   work. The output schema therefore has an activity layer that stays empty and a store layer
   that is fully populated, and the render shows the empty layer rather than hiding it.

2. **Retention is recorded as an *envisaged time limit*, and only "where possible".** Art. 30(1)(f)
   [S1]. A found `timedelta(days=30)` is evidence for that limit; it is not the limit itself, and
   an absent timer is not a finding of breach. CNIL's "or failing that, the criteria for
   determining it" [S6] is the fallback the schema needs.

3. **Retention splits by category of data, not by store.** CNIL: *"Si les catégories de données ne
   sont pas soumises aux mêmes durées de conservation, ces différentes durées doivent apparaître
   dans le registre."* [S4b] A `users` table where the email is purged at 30 days and the invoice
   reference is kept for ten years is two rows.

4. **Recipients include processors, and an import is not a disclosure.** Art. 4(8) and 4(9) [S1].
   AMBIGUITIES row 7 already says a personal-data field must flow into the call. Art. 28(3)(g)
   makes the contract stipulate that the processor *"at the choice of the controller, deletes or
   returns all the personal data to the controller after the end of the provision of services
   relating to processing"* [S1], which is why an external store is `external_manual` and not
   `not_erased`: the deletion obligation exists, it just does not live in this repository.

5. **The security cell covers Art. 32(1)(a) and says so.** Volkswagen's EUR 1.1m fine covered
   four low-severity breaches, one of them the missing explanation of technical and
   organisational measures in the record [S17]; Foodinho's covered the same omission among
   others [S16]. The cell is chargeable under Art. 30. Filling it with everything a static
   reader can find and labelling the gap is more useful than a hedge.

6. **The record is "in writing, including in electronic form".** Art. 30(3) [S1], CNIL: format is
   free, paper or electronic [S6]. Markdown plus JSON meets that written-form requirement;
   whether the record itself is adequate is not a form question. No document-generation work is
   needed and NON-GOALS stays as written.

7. **Backups are inventory governed by a retention schedule, not an erasure verdict.** ICO's
   "beyond use" [S10] and EDPB Issue 6 [S11] both treat them that way. Change the render from a
   blank verdict to `governed_by_retention` / `no_schedule_evidenced`, because the EDPB's finding
   was that controllers claim schedules they do not have. Both labels map to
   `reaches_erasure=false` in the scored tuple; CASES.md needs that as an errata line.

8. **Anonymisation only reaches erasure when it is irreversible.** WP216: *"the processing must be
   irreversible"* [S12]. Split AMBIGUITIES row 5 into `anonymised` (counts) and `pseudonymised`
   (does not, and counts as a false safe when claimed). Hashing an email is the idiom to plant in
   a synthetic case.

9. **Soft delete is the field's actual failure mode, and a regulator has now said so.** EDPB:
   *"certain controllers had difficulties with differentiating between closing an online user
   account or profile and the right to erasure"* [S11]. Brico Privé's EUR 500,000 fine included
   EUR 300,000 for breaches of Arts. 5-1-e), 13, 17 and 32, the Art. 17 finding being that
   account deletion requests were answered by deactivation [S18]. Cases S02 and S10 are not
   contrived. This is the README's strongest sentence and it is a quote, not a claim.

10. **The 250-employee derogation does not save the target user.** Art. 30(5) conditions are
    alternatives, any one triggers the obligation, and processing in the regular course of
    business is not "occasional" [S9][S6]. The pending Omnibus proposal to move the threshold to
    750 persons is not law [S20]. A SaaS with user accounts owes a record. That is the
    "why it matters" opener, and the same paper's line that the burden is *"unlikely to
    constitute a particularly heavy burden"* [S9] is the setup for the real point: the burden is
    not writing the document, it is knowing whether the document is true. The EDPB found that
    *"some responding controllers do not even report relying on their record of processing
    activities ('ROPA')"* when handling erasure requests, and that the difficulty comes from
    *"the absence of a structured process to map the relevant personal data"* [S11]. That is the
    bottleneck, named by the regulator, in the year the tool was built.

Art. 15 stays out of scope per NON-GOALS. The store map this tool builds is the input a subject-
access export would need, which is why the exclusion is a scope line and not a capability gap.

---

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S1 | Regulation (EU) 2016/679 (GDPR), OJ L 119, 4.5.2016, p. 1 (official OJ text, retrieved from the Publications Office cellar copy of CELEX 32016R0679 after eur-lex.europa.eu returned an AWS WAF challenge; canonical ELI cited) | https://eur-lex.europa.eu/eli/reg/2016/679/oj (retrieved via http://publications.europa.eu/resource/celex/32016R0679) | 2026-08-28 | All verbatim article and recital texts in `sources/gdpr/`; Arts. 4, 5, 15, 17, 28(3), 30, 32(1), 44; Recitals 13, 26, 39, 65, 66 |
| S2 | ICO, "What do we need to document under Article 30 of the UK GDPR?" | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/documentation/what-do-we-need-to-document-under-article-30-of-the-gdpr/ | 2026-08-28 | ICO's controller documentation list; retention-schedule gloss; UK-regime caveat |
| S3 | ICO, "Documentation template for controllers" (.xlsx) | https://ico.org.uk/media2/migrated/2172937/gdpr-documentation-controller-template.xlsx | 2026-08-28 | The 30 template columns quoted in §2.1, verbatim from sheet `Template` row 9; the required/optional distinction from sheet `Notes` |
| S4 | ICO, "How do we document our processing activities?" | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/documentation/how-do-we-document-our-processing-activities/ | 2026-08-28 | "not mandatory"; "living document" |
| S4b | CNIL, "Exemple de registre" / modèle de registre de base (PDF) | https://www.cnil.fr/sites/default/files/atoms/files/registre_rgpd_basique.pdf | 2026-08-28 | The per-activity fiche sections listed in §2.2; the per-category retention rule; backups listed as a security measure |
| S5 | CNIL, "Modèle de registre simplifié" (.ods) | https://www.cnil.fr/sites/cnil/files/atoms/files/registre-traitement-simplifie.ods | 2026-08-28 | Recipient-kind vocabulary from the `5 - Listes` sheet; the `Garanties` and country lists as evidence that the workbook pre-dates Schrems II |
| S6 | CNIL, "Le registre des activités de traitement" | https://www.cnil.fr/fr/RGPD-le-registre-des-activites-de-traitement | 2026-08-28 | Per-activity field list; Art. 30(1)(f) gloss with the "criteria" fallback; free-format rule; scope of the under-250 derogation |
| S7 | CNPD (Luxembourg), "Records of processing activities" | https://cnpd.public.lu/en/professionnels/obligations/registre.html | 2026-08-28 | No unique template required; other authorities' models named; models do not cover all situations |
| S8 | CNPD, "Illustration d'un registre des activités de traitement sur base de l'article 30 du règlement général sur la protection des données" (PDF) | https://cnpd.public.lu/dam-assets/fr/dossiers-thematiques/guidance-associations/CNPD-modele-registre.pdf | 2026-08-28 | The seven-column table shape used as the Markdown render target |
| S9 | Article 29 Working Party, "Position paper on the derogations from the obligation to maintain records of processing activities pursuant to Article 30(5) GDPR", 19 April 2018 (endorsed by the EDPB) | https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/position-paper-derogations-obligation-maintain-records_en (PDF: https://ec.europa.eu/newsroom/article29/redirection/document/51422) | 2026-08-28 | Conditions are alternatives; definition of "occasional"; burden statement |
| S10 | ICO, "Right to erasure" | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/right-to-erasure/ | 2026-08-28 | Erasure from backup systems; "beyond use" |
| S11 | EDPB, "2025 Coordinated Enforcement Action: Implementation of the right to erasure by controllers", adopted 10 February 2026 | https://www.edpb.europa.eu/system/files/2026-02/edpb_cef-report_2025_right-to-erasure_en.pdf | 2026-08-28 | Backups Issue 6; anonymisation Issue 7; ROPA not used for erasure requests; account closure confused with erasure; 32 SAs / 764 controllers |
| S12 | Article 29 Working Party, Opinion 05/2014 on Anonymisation Techniques (WP216), 10 April 2014 | https://ec.europa.eu/justice/article-29/documentation/opinion-recommendation/files/2014/wp216_en.pdf | 2026-08-28 | Anonymised data outside data protection law; irreversibility; the AOL pseudonymisation example |
| S13 | CNIL, "Droit à l'effacement : bilan des contrôles de la CNIL dans le cadre de l'action coordonnée européenne" | https://www.cnil.fr/fr/droit-effacement-bilan-cnil-action-europeenne | 2026-08-28 | French national findings of the 2025 coordinated action, including difficulty deleting personal data from backups |
| S14 | Berliner Beauftragte für Datenschutz und Informationsfreiheit, press release "Berliner Datenschutzbeauftragte verhängt Bußgeld gegen Immobiliengesellschaft", 5 November 2019 (PDF) | https://www.datenschutz-berlin.de/fileadmin/user_upload/pdf/pressemitteilungen/2019/20191105-PM-Bussgeld_DW.pdf | 2026-08-28 | Deutsche Wohnen fine of ~EUR 14.5m, 30 Oct 2019; archive system with no removal facility |
| S15 | Court of Justice of the EU, Press Release No 184/23, judgments in C-683/21 and C-807/21, 5 December 2023 (PDF) | https://curia.europa.eu/site/upload/docs/application/pdf/2023-12/cp230184en.pdf | 2026-08-28 | Status of the Deutsche Wohnen fine as contested; wrongfulness requirement; group-turnover basis |
| S16 | Garante per la protezione dei dati personali, provvedimento 10 June 2021, doc. web n. 9675440 (Foodinho s.r.l.) | https://www.gpdp.it/web/guest/home/docweb/-/docweb-display/docweb/9675440 | 2026-08-28 | Register omitted data categories found in the systems; missing Art. 32(1) description; violation of Art. 30(1)(a),(b),(c),(f),(g); the register is not a formality |
| S17 | Landesbeauftragte für den Datenschutz Niedersachsen, press release "1,1 Millionen Euro Bußgeld gegen Volkswagen", 26 July 2022 | https://lfd.niedersachsen.de/startseite/infothek/presseinformationen/1-1-millionen-euro-bussgeld-gegen-volkswagen-213835.html | 2026-08-28 | Missing technical and organisational measures in the record as an Art. 30 breach |
| S18 | CNIL, délibération de la formation restreinte n° SAN-2021-008 du 14 juin 2021 (Brico Privé), Légifrance | https://www.legifrance.gouv.fr/cnil/id/CNILTEXT000043668709 | 2026-08-28 | Deactivation instead of erasure; the operative part's split of the EUR 500,000 into EUR 300,000 for Arts. 5-1-e), 13, 17 and 32 and EUR 200,000 under Art. 82 of the loi Informatique et Libertés and Art. L. 34-5 CPCE. Direct scripted retrieval returned HTTP 403 twice; read through WebFetch at the same URL |
| S19 | CMS Law.Tax, GDPR Enforcement Tracker | https://www.enforcementtracker.com/ | 2026-08-28 | Case discovery only (filtering decisions citing Art. 30 and Art. 17). No factual claim above rests on this source alone |
| S20 | EDPB, "Targeted modifications of the GDPR: EDPB & EDPS welcome simplification of record keeping obligations and request further clarifications", 9 July 2025 | https://www.edpb.europa.eu/news/news/2025/targeted-modifications-gdpr-edpb-edps-welcome-simplification-record-keeping_en | 2026-08-28 | The proposed 750-person threshold and single high-risk test in the fourth simplification Omnibus; status as a proposal |
| S21 | UK GDPR, Regulation (EU) 2016/679 as it forms part of retained EU law, Article 30, legislation.gov.uk | https://www.legislation.gov.uk/eur/2016/679/article/30 | 2026-08-28 | The two UK divergences from Art. 30: the s. 28(3) DPA 2018 insertion in (1)(g) and "the Commissioner" in (4) |
| S22 | Django 5.2 documentation, "Settings" (`SECURE_SSL_REDIRECT`) | https://docs.djangoproject.com/en/5.2/ref/settings/ | 2026-08-28 | What `SECURE_SSL_REDIRECT` does, as an Art. 32(1)(a) technical-measure signal |
| S23 | Sentry documentation, "Identify Users" (Python SDK) | https://docs.sentry.io/platforms/python/enriching-events/identify-user/ | 2026-08-28 | `sentry_sdk.set_user({"email": ...})` as a personal-data flow into an error tracker |
| S24 | Amazon S3 API Reference, "PutBucketEncryption" | https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutBucketEncryption.html | 2026-08-28 | The `ServerSideEncryptionConfiguration` element as the bucket-encryption signal |
