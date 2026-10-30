# Bangladesh AI nutrition buddy: mindmap and feasibility review

Reviewed 23 October 2026. Input: `mindmap.jpeg` and the product description in this conversation. The directory contains a mindmap, not an implementation; architectural findings concern the proposed design, not inspected code. Recommendations and planning estimates below are judgments, not validated market findings or regulatory determinations.

Scope clarification: the user intends disease tracking to mean storing self-reported diagnoses and using them for food suggestions and cautions, such as flagging a pictured sweet for a user reporting diabetes. Measurement monitoring, diagnosis, deterioration detection and treatment changes are not part of this requirement. References below to those capabilities describe possible scope expansion, not requested features.

Additional confirmed scope: patients should be able to share historical eating-pattern analysis with a doctor during a consultation. The doctor uses this history to support a food-habit assessment. This adds a clinician-facing consultation workflow; it does not imply autonomous diagnosis or continuous monitoring.

## Overall assessment

A Bangla nutrition companion is technically feasible. The proposed combination of universal age coverage, disease-specific guidance, reliable photo nutrition, reinforcement learning, and deficiency forecasting is too broad and insufficiently defined for a responsible first release.

The strongest product promise is: **help people decide what to eat next using familiar Bangladeshi foods, their actual budget, their household situation, and appropriate health constraints.** Food scanning is one way to gather information; it should not define the whole product.

The launch decision should be conditional: proceed with a narrow, evaluated adult companion; defer autonomous clinical management and unsupported health predictions. Commercial viability remains unproven until users return, recommendations are practical, and somebody pays enough to cover delivery and support.

## 1. Defects in the current mindmap

| Mindmap element | Defect or missing assumption | Recommended change |
|---|---|---|
| Food Scanner as the hub | Recognition, nutrition calculation, health reasoning, behavior change and activity tracking appear coupled. A recognition error could contaminate everything downstream. | Make a structured meal record and user goal central. Treat the scanner as an optional input. |
| Extract nutrients from a photo | Images do not reveal exact mass, oil, salt, sugar, ingredients hidden in gravy, or preparation losses. | Recognize candidates, confirm portion and recipe assumptions, then calculate estimates from a curated database. |
| Healthy or bad for this user | A binary judgment hides portion, frequency, missing context and conflicting conditions; it can also shame users. | Explain suitability, uncertainty and one achievable modification. Reserve firm restrictions for justified constraints. |
| Comprehensive health profile | BMI, allergies, disease names and free text are insufficient for clinical personalization. | Use a minimal structured profile, provenance, dates, units, completeness flags, and progressive questions. |
| All ages and ranges | Children, adolescents, pregnant people, frail elders and adults with different diseases require different workflows and evidence. | Treat these as separately designed and validated programs. Start with a defined adult group. |
| RL for meal recommendation | There is no defined reward, safe action space, outcome measurement, or protection from feedback bias. | Start with constraints and explicit preference ranking. Consider carefully evaluated learning later. |
| Predict deficiencies over 30 days | Logged intake is incomplete and does not measure absorption, stores, losses, disease or biochemical status. | Describe possible intake gaps on sufficiently logged days. Do not diagnose or forecast deficiency from logs alone. |
| Predict weight trajectory | Sparse self-reports and uncertain energy intake can produce misleading precision. | Start with observed trends; research forecasts separately with uncertainty and held-out validation. |
| Restaurant menu parsing | Dish names do not disclose recipes, portion weight, allergens or cross-contact. | Offer approximate comparisons and questions to ask the restaurant; never certify allergy safety. |
| Barcode/OCR fallback | A barcode identifies a product only if a reliable catalog has it; label OCR can misread units and serving sizes. | Treat packaged goods as a separate input flow. Allow verified label entry and explicit unknowns. |
| Calorie consumption and burn | Multiple data sources can double-count activity; expenditure is an estimate. | Preserve sources, deduplicate events, distinguish total and active energy, and avoid automatic eat-back budgets. |
| PWA plus wearable integration | Browser delivery does not supply native health-store integration by itself. | Use a PWA to validate the core experience; add a native client or bridge when the use case warrants it. |
| Several cuisines | Expands data and evaluation requirements before local coverage is dependable. | Prioritize the meals eaten by the initial Bangladeshi cohort. |

Photo nutrition is an estimation problem even in research. Nutrition5k used ingredient weights, multiple views and depth data, illustrating how much information is absent from a casual single photograph. It does not establish expected accuracy on Bangladeshi home meals. [Nutrition5k research](https://arxiv.org/abs/2103.03375)

## 2. Decisions to clear before implementation

1. **First user and job:** Is this for a person choosing lunch, a household cook planning meals, or a patient following a dietitian's plan? These jobs imply different products.
2. **Intended use:** General education and habit support, or disease management? State allowed and excluded claims in product copy, support scripts and system behavior.
3. **Disease tracking — clarified:** Store self-reported diagnoses and apply reviewed food-suggestion rules. Decide which conditions and food cautions are supported and what information each rule requires. Measurement monitoring, deterioration detection and treatment changes are outside the requested scope.
4. **Initial conditions:** Which conditions, stages and combinations are actually supported? What happens when a user has an unsupported condition?
5. **Clinical ownership:** Who approves rules, resolves conflicting guidelines, reviews incidents and authorizes changes?
6. **Primary outcome:** Better meal decisions, dietary variety, adherence to a prescribed plan, weight change, or another outcome? Define a small number before choosing models.
7. **Learning:** Does an override correct a dish, portion, preference, price, clinical fact or recommendation? These are distinct events.
8. **Budget:** Is it per person, meal or household, and how often does it change? Which localities and price sources are covered?
9. **User and payer:** Individual, family, clinic, employer, NGO or another sponsor? A beneficiary and a purchaser can differ.
10. **Distribution:** How will the first users discover and trust the app? Partner-led and direct consumer acquisition have different costs.
11. **Human service:** Is a dietitian actually available? State hours and response times; do not imply someone monitors readings continuously.
12. **Data governance:** Where are records processed, who receives them, how long are images retained, and what consent covers learning or research?

## 3. Clinical boundaries and patient records

The confirmed requirement is **record user-reported diagnoses and use them in food suggestions and cautions**, with clear source labels. This is a feasible first-release capability for a defined set of reviewed rules. It does not require building disease monitoring, diagnosis or automatic treatment management.

For example: identify a possible sweet, let the user confirm the food and portion where needed, then apply a diabetes-related caution and offer an appropriate practical alternative. Wording should communicate uncertainty and avoid treating all sweet foods as categorically forbidden. Carbohydrate amount and portion matter, including in foods that do not taste sweet. [CDC meal planning](https://www.cdc.gov/diabetes/healthy-eating/diabetes-meal-planning.html)

Store the condition as self-reported with its recorded date and explicit edits. A reviewed rule should specify its triggering food attributes, required context, warning wording, limitations and source/version. Low-confidence recognition should trigger confirmation rather than a definitive warning. Eating the food anyway can inform coaching preferences but must not deactivate the health rule. If a user reports treating low blood sugar, bypass the ordinary sweets-reduction message and use a separately reviewed safety response; this does not imply ongoing glucose monitoring.

For supported workflows, the model may need condition subtype, stage, relevant medications, clinician targets, measurement timestamps, allergies and reaction history, pregnancy/lactation status and other constraints. Collect only what the selected workflow needs. A person should be able to decline a question; the system should then reduce the specificity of advice.

Separate self-reported, document-extracted and clinician-confirmed facts. Store measurement units and collection times. Validate OCR before accepting lab values or measurements, preserve original values, and flag implausible entries. A stale glucose value is not a current reading. A missing diagnosis is not proof that a disease is absent.

Condition-specific nutrition can conflict. For example, a generic recommendation involving protein, potassium-rich foods or salt substitutes may be unsuitable for some kidney patients. Requirements depend on disease stage, treatment and other clinical information. [CDC: diabetes and kidney disease](https://www.cdc.gov/diabetes/healthy-eating/diabetes-and-kidney-disease-food.html)

Design a clinician-approved response policy for incomplete information, conflicting restrictions, possible acute symptoms, suspected malnutrition and eating-disorder concerns. Where the system cannot safely personalize, it should say so and provide a practical route to appropriate care. Do not suggest medication changes. Record the user's choice without presenting it as clinical approval.

Adult BMI categories cannot serve as one universal nutrition policy. Children need age-appropriate growth assessment; pregnancy and frailty need different interpretations. Do not assume every user wants weight loss. A recommendation system must also avoid imposing increasingly restrictive diets when constraints conflict.

## 4. Bangladesh-specific product and data requirements

### Local food knowledge

Bangladesh already has a Food Composition Table, including an electronic file listed by FAO. It is a useful seed, not a complete product database. Check commercial reuse terms, coverage, provenance, nutrient definitions, missing values and suitability before importing it. [FAO database listing](https://www.fao.org/food-composition/tables-and-databases/detail/%28country--date%29-title-1/en)

The product needs:

- Bangla names, Banglish spellings, regional aliases and canonical food IDs.
- Cooked versus raw states, edible fractions, recipe yields and nutrient retention assumptions.
- Recipe variants for dal, bhorta, khichuri, curries, biryani, snacks, sweets and other common meals.
- Household portions: bati, cups, ladles, rotis, fish pieces and plate portions, with illustrated examples and approximate weights.
- Explicit missing nutrients. Unknown potassium or sodium must not become zero.
- Source, version, review date and confidence in the underlying evidence.
- Affordability estimates tied to locality and observation date, with no unsupported promise of live market prices.

“One bowl” varies by household. Let users calibrate a frequently used bowl or save a household recipe once. Shared cooking also creates a valuable input shortcut: estimate the recipe total, ask how many portions it made, then record what the user ate, including leftovers.

Bangladesh's dietary guidelines offer a national reference for general education, but a general-public guideline is not a substitute for current condition-specific clinical protocols. [FAO: Bangladesh dietary guidelines](https://www.fao.org/nutrition/education/food-dietary-guidelines/regions/countries/bangladesh/en/)

### Language and accessibility

Bangla should shape the workflow from the beginning. Support Bangla script, Banglish and mixed input; test regional food vocabulary and speech recognition in household noise. Confirm consequential quantities and disease terms. A transcription error involving a portion, decimal or negation can change advice.

Use short explanations, optional audio, adjustable text and visual portions. Examples such as “আজ যা আছে” and “আবার এই খাবার” can support the real daily task better than requiring long chat messages. Validate all copy with Bangla-speaking target users and a clinical reviewer.

Plan for low-cost phones, intermittent connectivity, image compression, offline draft logs and retry-safe synchronization. Do not imply an offline health review occurred when only logging was available.

### Household reality

The person using the phone may not buy or cook the food. Ask about access to a kitchen, available ingredients, who controls meals, work or school meals, food preferences and budget. Consider a caregiver account only with separate patient identities, explicit permissions and revocable sharing.

Offer realistic substitutions and portion adjustments. Account for fasting, festivals and shift work without inferring a user's religion. Disease-specific fasting advice belongs in a clinically reviewed pathway.

Affordability is a fundamental design constraint. UNICEF's 2024 Bangladesh report describes widespread child food poverty; advice alone cannot fix inadequate access to food. This supports designing for practical substitutions and potential sponsored programs, not assuming subscription demand. [UNICEF Bangladesh](https://www.unicef.org/bangladesh/en/press-releases/2-3-children-under-five-bangladesh-face-child-food-poverty-unicef)

## 5. Proposed architecture

Start with a modular backend, a relational database, object storage and a background job queue. Separate responsibilities in code; microservices and a custom foundation model are unnecessary starting requirements.

```text
Bangla client: text / voice / photo / repeat meal
                         |
             Authentication and consent
                         |
      Input extraction: speech / vision / OCR
                         |
       User confirms food, portion, key facts
                         |
           Structured, versioned meal record
                         |
  Nutrient calculation + reviewed clinical constraints
                         |
      Candidate generation and feasibility checks
                         |
        Preference, availability and budget ranking
                         |
       Bangla explanation grounded in those results
                         |
        Final validation / uncertainty / escalation
                         |
             User choice and typed feedback
```

The responsibilities should be explicit:

| Component | Responsibility |
|---|---|
| Profile and consent | User, patient and caregiver identities; access; allowed purposes; versioned health facts. |
| Food catalog | Foods, aliases, recipe variants, units, source data and reviews. |
| Nutrient calculator | Deterministic arithmetic from confirmed quantities, with assumptions and missingness. |
| Clinical policy | Clinician-approved constraints, supported populations, required inputs and conflict handling. |
| Recommendation planner | Generate achievable meals and substitutions; handle cases with no suitable candidate. |
| Preference ranker | Rank eligible options by taste, price, availability, effort and explicit user goals. |
| Language model | Interpret input, ask useful questions and explain structured results in Bangla. |
| Safety validation | Check generated text against the approved recommendation, prohibited advice and escalation policy. |
| Operations console | Review content, incidents and datasets; inspect version history; roll back changes. |

Retrieve clinical information only from an approved, versioned knowledge collection. Retrieval can improve grounding but does not guarantee correctness. Have structured outputs for calculations and recommendations; the model should not invent nutrients, diagnoses, targets or citations. High-risk responses can require fixed reviewed wording or human review.

Each recommendation should be reproducible from the relevant meal assumptions, profile version, source data, rule version and model version. Retain enough decision information for incident review without copying sensitive chat and images into unrestricted analytics.

Use minimum necessary context for model calls. Separate public knowledge retrieval from patient memory, with authorization enforced before retrieval. Treat OCR, documents, menu text and retrieved material as untrusted data, not instructions. Do not give the model authority to alter clinical facts or policies directly.

Test both the constraint engine and the language output. Rules can be wrong or incomplete, and a language model can contradict a correct structured result. Establish model-change evaluations, staged rollout, monitoring and a way to disable an unsafe feature.

### PWA and wearables

A PWA is a reasonable way to test logging, chat and camera input. Native health-store integration is a separate engineering commitment. Android Health Connect uses an Android SDK and platform permissions, so do not assume a browser PWA alone can cover it. Defer wearables until they improve an already validated user outcome. [Android Health Connect documentation](https://developer.android.com/health-and-fitness/health-connect/get-started)

## 6. Learning from overrides

Personalization should first update structured memory and ranking, not retrain a model after each conversation.

| Feedback | Appropriate action | Inappropriate inference |
|---|---|---|
| “This is moong dal, not masoor dal.” | Correct the meal; retain a labeled correction with suitable consent. | All future dal images represent moong dal. |
| “I ate half the bowl.” | Correct consumption and recalculate. | The original estimate was verified ground truth. |
| “I don't like fish.” | Save an editable preference and offer alternatives. | Fish is medically unsuitable. |
| “This costs too much.” | Update budget assumptions and ranking. | The user dislikes the dish. |
| “I ate it anyway.” | Log neutrally, ask an optional reason and adapt support. | The food is safe or should be recommended more often. |
| “I no longer have this allergy.” | Request deliberate profile review and apply the clinical verification policy. | Remove the restriction from incidental chat. |
| User likes an answer | Use as experience feedback. | The health recommendation was correct. |

Support view, edit, forget and undo for memory. Distinguish persistent preferences from one-time context, and ask before retaining sensitive facts. Preferences can change and shouldn't require repeated correction forever.

If a learned ranker becomes useful, train and evaluate it on consented data with exposure logging and a clear target. Acceptance is biased by what was shown. Clinical outcomes have delays and confounders; likes and clicks are not valid substitutes. Any later bandit or reinforcement-learning experiment needs a restricted eligible action space, offline evaluation, controlled rollout and clinical oversight. Avoid online experimentation that trades health safety for engagement.

## 7. Privacy and regulation

Bangladesh's official law database lists the **Personal Data Protection Act, 2026**, and states that it repealed the 2025 ordinance and its 2026 amendment. The Act identifies health information as sensitive personal data. Obtain a current local legal assessment of applicable provisions, commencement, implementing rules and operational requirements. [Official Act](https://bdlaws.minlaw.gov.bd/act-details-1692.html?lang=en), [official repeal provision](https://bdlaws.minlaw.gov.bd/act-1692/act-chapter-print-2701.html)

Translate that assessment into architecture: purpose-specific consent, data minimization, access controls, encryption, retention, deletion/export workflows, processor contracts, incident handling and appropriate safeguards for children. Determine cloud hosting, international model processing and cross-border transfer requirements before selecting providers. Do not assume either that all data must stay locally or that international processing is automatically permissible.

Use separate consent for care delivery, product research and model improvement where applicable. Avoid advertising trackers in health flows. Images and documents may contain faces, names or prescriptions; remove unnecessary metadata, crop where appropriate and apply a clear retention policy. Deletion must address derived memories, retrieval indexes and backup retention as well as the primary record, subject to lawful retention requirements.

DGDA's medical-device registration guidance explicitly addresses qualifying standalone software. Disease monitoring, treatment-oriented recommendations and predictive health claims therefore require an intended-use and classification assessment. This review does not establish the app's device class or registration route. A disclaimer alone does not determine classification. [DGDA guidance](https://dgda.gov.bd/sites/default/files/files/dgda.portal.gov.bd/policies/802ec167_9ba7_4f1b_adde_88871d797f08/2024-02-15-08-52-970321e5d385df48394bdd2d06110efa.pdf)

WHO documents risks from inaccurate, biased or incomplete multimodal health outputs and recommends stakeholder involvement and well-defined tasks. That supports bringing a Bangladeshi clinical reviewer into product design and evaluation from the beginning. [WHO guidance announcement](https://www.who.int/news/item/18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models)

## 8. Recommended first release

Default first cohort: Bangla-speaking adults seeking practical, affordable meal guidance, with explicit screening and routing for unsupported clinical needs. If a clinical partner is already available, an alternative is one tightly defined, supervised condition-specific cohort. Do not combine both into an unrestricted medical chatbot.

Build:

1. A short, progressive profile: goal, allergies, relevant supported constraints, food access, budget and preferences.
2. Bangla/Banglish meal entry, recent meals and repeat-meal shortcuts; add voice if target-user testing supports it.
3. Optional photo assistance with editable food and portion confirmation.
4. A reviewed local catalog covering the cohort's common meals; around 100–200 entries is an initial planning hypothesis, not a validated coverage target.
5. One or two affordable next-meal options with assumptions and a plain explanation.
   Include reviewed condition-aware food cautions based on self-reported diagnoses, with confirmation when food identity or relevant ingredients are uncertain.
6. Typed feedback and editable preference memory.
7. Weekly summaries of observed habits and logging coverage, without claims of deficiency or disease prediction.
8. A review console, reporting route, privacy controls and operational monitoring.

Defer: broad all-age clinical advice, general disease management, restaurant macro certainty, deficiency forecasting, autonomous treatment changes, wearables, online RL and broad international cuisines.

The core daily loop should work without a photograph: **tell us what you ate or what food is available → confirm important details → receive a useful next step → tell us what worked.** Do not require complete calorie logging before providing ordinary meal support.

## 9. Main obstacles and launch evidence

| Obstacle | Why it threatens shipping | Evidence to seek |
|---|---|---|
| Local data coverage | A fluent answer can conceal the wrong recipe or portion. | Evaluation against weighed recipes and confirmed portions from target households. |
| Clinical scope | Multi-condition cases can exceed the team's expertise. | Named clinical owner, reviewed policies, exclusions, conflict handling and intended-use assessment. |
| Logging burden | Initial curiosity may not become a daily habit. | Repeated unprompted use and fast repeat-meal entry in a multiweek pilot. |
| Practicality | A correct suggestion may be unaffordable or impossible to cook. | Users can obtain, afford and act on recommendations. |
| Bangla comprehension | Small errors in quantities and health terms can matter. | Tests with intended dialects, literacy levels and noisy speech. |
| Trust | Overconfident mistakes can damage the product quickly. | User understanding of uncertainty; incident response and transparent corrections. |
| Economics | Vision, voice, inference, support and human review add recurring costs. | Measured cost per retained active user and real willingness to pay or sponsor. |
| Distribution | Need does not imply affordable customer acquisition. | A repeatable channel with measured acquisition cost and activation. |
| Governance | Models, rules and food data change. | Versioned evaluation, controlled releases and rollback drills. |

Evaluate recognition, portion estimation, nutrient estimation and recommendation quality separately. Use weighed recipes as a reference for calculation estimates while recognizing that food tables themselves are imperfect; use laboratory measurement where claims require it. A dietitian's visual estimate is not exact nutrient ground truth.

Split evaluation by households and recipe variants, avoiding near-duplicate meal photos across training and testing. Include low-end phones, lighting variation, missing data and unfamiliar meals. Report errors by food group and user segment, not just one overall accuracy percentage. Calibrate uncertainty or use evidence-based categories; a model-generated confidence percentage is not a validated probability.

For recommendation safety, include severe allergies, unknown ingredients, conflicting conditions, stale readings, unsafe weight goals, attempts to override restrictions, urgent symptom language and prompt injection in uploaded text. Require no observed critical failures in the defined release suite and investigate every severe incident. Passing a finite suite does not establish zero real-world risk.

For product viability, measure time to first useful suggestion, meal-entry burden, correction rate, recommendation actionability, week-four retention, support burden and willingness to pay. State denominators clearly. A small pilot can test usability and demand but cannot prove broad clinical efficacy. Any claim of improved medical outcomes needs an appropriately designed study and relevant ethical/regulatory review.

Monthly delivery cost should include inference, vision/OCR, speech, hosting, messaging, payment fees, dietitian time and support. Calculate contribution per paying user after serving any free cohort, then assess acquisition cost and retention. Measure real sessions; do not set price from token cost alone.

## 10. Practical sequence and feasibility

Illustrative planning ranges, assuming a focused small team and available reviewers:

| Stage | Work and exit decision |
|---|---|
| First 2–4 weeks | Interview roughly 15–25 target users and several dietitians/caregivers; choose one job, cohort and channel; test real meal advice manually; clarify intended use. |
| Next 4–8 weeks | Build the core text/repeat-meal loop, initial reviewed catalog, memory controls and logging; benchmark photo assistance separately. |
| Following 6–10 weeks | Run a controlled multiweek pilot, potentially 50–100 participants depending on capacity; review safety, usability, retention and delivery cost. |
| Expansion decision | Ship more broadly only after predefined safety and product gates. Add one condition, age pathway or integration at a time. |

Some work can overlap. A demonstrator can be much faster; a controlled, supportable pilot is reasonably a roughly 3–6 month planning exercise under these assumptions. Medical claims, regulatory requirements, recruitment, data licensing or clinical validation can extend this substantially. There is not enough information to provide a reliable development budget.

The minimum capability mix includes product/user research, client and backend engineering, AI integration/evaluation, Bangladesh nutrition expertise and part-time privacy/regulatory support. Roles can overlap; clinical accountability should remain explicit.

| Proposed capability | Feasibility judgment |
|---|---|
| Bangla meal companion with memory | Feasible now with a narrow scope and good evaluation. |
| Local recipe estimates and practical substitutions | Feasible, with meaningful curation and portion work. |
| Optional photo-assisted logging | Feasible as an uncertain, user-confirmed estimate. |
| Structured condition and measurement tracking | Feasible, with privacy, provenance and clear monitoring boundaries. |
| Disease-specific recommendations | Conditional on a defined cohort, clinical governance, evidence and regulatory assessment. |
| Universal safe food verdict from a photo | Not a credible product promise. |
| Thirty-day micronutrient-deficiency prediction from ordinary logs | Not justified by the proposed inputs. |
| Health optimization learned directly from overrides | Unsafe and poorly specified as an initial design. |
| Commercial success | Unknown until retention, distribution and economics are measured. |

The best version of the idea is a trustworthy companion that understands local meals, remembers constraints appropriately, suggests achievable changes and knows when the available information is insufficient. Its defensibility would come from curated Bangladeshi food knowledge, evaluated Bangla workflows, clinical operations and sustained usefulness—not simply from having a scanner or using reinforcement learning.

## 11. Patient-controlled food history for doctor consultations

This is a strong candidate for a core product workflow: **daily Bangla meal support builds a longitudinal food record; the patient shares a concise, inspectable summary during a consultation.** Its value and novelty should be tested with clinicians and patients rather than assumed. The first goal is useful information within a short consultation, not a comprehensive clinical system.

### Access flow

1. A verified clinician signs in to a clinician account.
2. The patient supplies an app-specific ID or QR code. This locates an access request; it is not itself authorization and should not reveal health information to an unauthorized requester.
3. The patient approves the named clinician, date range, information categories and access duration through an authenticated app action or suitable one-time approval flow.
4. The doctor confirms the intended patient and opens the authorized summary. Matching and verification must accommodate duplicate names and shared phones.
5. The grant expires or is revoked. Access is logged and visible to the patient. Downloaded copies cannot be recalled, so exports require clear disclosure and appropriate clinical retention handling.

Do not use a national identity number as a public lookup secret. Long-term clinic access and delegated caregiver authorization require explicit, separately designed permissions. A patient sharing a screen or a selected report is also a useful initial workflow where portal adoption is difficult.

### What the clinician sees

Start with a one-page summary, a date selector and drill-down to meals. Include:

- Coverage: dates covered, days with any entries, patient-marked complete days, meal counts and missing categories. Patient-marked completeness is still a self-report.
- Most frequently logged foods and food groups, with denominators. Frequency by eating occasion is different from quantity or contribution to energy intake.
- Reported portions, meal timing and weekday/weekend patterns, when sufficiently logged.
- Logged sweets, sweetened drinks, fruit, vegetables and protein sources, using reviewed classifications.
- Relevant self-reported conditions and allergies, clearly distinguished from clinician-confirmed facts.
- Nutrient estimates only where supported, with missing data and recipe/portion assumptions. Incomplete daily logs should not be presented as total daily intake.
- Patient-reported constraints such as budget, household meals and preferences; these can explain why advice was difficult to follow.
- Changes over time only with comparable coverage and methods; a lower count caused by less logging is not evidence of improvement.
- AI-generated discussion prompts linked to the supporting entries, plus clinical notes and plans in a separate section.

Illustrative wording: “In the selected 30 days, 18 days contain entries and 12 were marked complete by the patient. Sweetened tea appears on 11 of the 18 logged days. Sugar quantity is unknown in seven entries.” This is more defensible than “The patient drinks sweetened tea every day.” Counts alone should not be interpreted as diagnoses, causation or verified adherence.

All self-reported dietary assessment contains measurement error. Users may forget snacks or drinks, omit foods they feel judged about, or change behavior because they are logging. The report should assist the doctor's interview, with explicit gaps to clarify. [NCI Dietary Assessment Primer](https://epi.grants.cancer.gov/dietary-assessment-primer/concepts/error/)

### Architecture additions

Use structured consumption events rather than chat transcripts as the source of analytics. Separate a photographed/considered meal, a recommended meal and a meal actually reported eaten. Record consumption time, entry time, source, portion, recipe assumptions, corrections and whether the entry was made by a caregiver. Prevent duplicate records from repeated uploads or offline retries.

Calculate counts, distributions and trends deterministically. The AI can explain these computed results and suggest questions but must not invent observations. Keep the original records inspectable, version corrections and create a dated report snapshot for the consultation. A subsequent correction should not silently rewrite what the doctor previously reviewed.

Add clinician identities, consent grants, scoped authorization, access audit records and consultation notes. A doctor's assessment or approved plan must be distinguishable from an AI draft. If the product later lets clinician-approved targets influence daily suggestions, use an explicit, versioned plan workflow with author, effective dates and change history; do not treat every free-text note as an executable instruction.

An exportable report can precede hospital integrations. If integrations become necessary, HL7 FHIR NutritionIntake offers a relevant model for consumption records, but recipient support and FHIR version must be agreed; adopting the resource alone does not establish interoperability. [HL7 NutritionIntake](https://hl7.org/fhir/nutritionintake.html)

### Pilot and priority

Move historical analysis ahead of wearables, online RL and predictive health features. Pilot a 7/30-day summary and selected report sharing with a small clinical partner group before building a broad clinician portal. Evaluate whether doctors understand coverage, can trace findings to entries, find relevant patterns faster and use the report in counseling. Also evaluate patient logging burden, willingness to share, and incorrect-patient or unauthorized-access failure cases.

This could support a clinic-led acquisition or payment model, but clinician adoption and payment remain hypotheses. The product needs both sides to work: low-effort daily value for the patient and a concise, trustworthy history for the doctor.
