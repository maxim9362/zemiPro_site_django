# ZemiPro — Stage 00–02: approved gate scheduling (Ashdod pilot)

**Decision:** owner approved 2026-11-12. **First PUBLIC pilot: Ashdod ONLY**. This file records a **schedule change, NOT successful verification and NOT a waiver**. The 6 districts, 25 city rows and 4 aliases remain technical PostgreSQL data; other cities are not offered publicly. PR #8 remains Draft/NOT_MERGED; no production actions authorized.

## Technical evidence and independent review

- Stage 00: CORE_VERIFIED with remaining follow-ups; PR #6 MERGED.
- Stage 01: LOCAL_VERIFIED with external release gates; PR #7 MERGED.
- Stage 02: technical implementation complete, isolated CI verified: code `f21444d7` 12/12 Ashdod-only targeted, 163/163 full Django, Chrome 45/45, service-layer-only coverage 94.7%, [Django CI](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43171013111), [Docker smoke](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43171022632) both SUCCESS. Documentation SHA `e4776876`: [Django CI](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43172878784) SUCCESS; [Docker smoke](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43172878734) SUCCESS. Older standalone 180-case Chromium run does not verify the final code SHA.
- **Technical gate NOT deferred:** independent targeted **Codex Cloud review of final Ashdod-only diff** and remediation of material findings. Stage 02 formal DONE requires subsequent explicit PR merge authorization by owner. Prior CODE_REVIEW_PASS covered older code.

## Obligations approved for scheduling BEFORE first public Ashdod launch

| Gate | Due | Current factual status | Proof required |
|---|---|---|---|
| Qualified native Hebrew/editorial signoff of shared UI and Ashdod RU/EN/HE content | Before public Ashdod launch | OPEN / RELEASE_DEFERRED_BY_OWNER | Reviewed text and translation acceptance |
| 11 proposed categories and 4 demonstration questionnaires | Before publishing this content | OPEN / RELEASE_DEFERRED_BY_OWNER | Owner/editorial acceptance, or leave unapproved material unpublished |
| Real physical Android/iPhone RTL, menus, forms and phone fields | Before public Ashdod launch | NOT_RUN / RELEASE_DEFERRED_BY_OWNER | Real-device screenshots/interaction results, not Chrome viewport alone |
| Owner acceptance of original screenshots, responsive/RTL UX | Before public Ashdod launch | OPEN / RELEASE_DEFERRED_BY_OWNER | Documented approval from owner |
| Historical/legacy secrets and credentials revocation/rotation | Before public Ashdod launch | OPEN / RELEASE_DEFERRED_BY_OWNER | Provider-level confirmation without exposing secrets |
| Off-host PostgreSQL/media backups and recovery rehearsal | Before public Ashdod launch | NOT_VERIFIED / RELEASE_DEFERRED_BY_OWNER | Actual off-host backups, restore proof; same-host tests insufficient |
| Real monitoring alerts | Before public Ashdod launch | NOT_VERIFIED / RELEASE_DEFERRED_BY_OWNER | Alert receipt confirmed end-to-end |
| Branch protection and release safeguards | Before public Ashdod launch (prefer before merge) | OPEN / RELEASE_DEFERRED_BY_OWNER | Enabled rules or owner-approved equivalent safeguards |
| Publicly trusted staging HTTPS and deployment/rollback test | Before public Ashdod launch | NOT_RUN / RELEASE_DEFERRED_BY_OWNER | Accessible trusted HTTPS staging, operational verification, rollback |
| Production/DNS/Cloudflare/VPS publication | Only with separate release permission | NOT_AUTHORIZED | Explicit owner GO; never automatic |

## Other mandatory due dates retained

- **Stage 00.4 follow-up and confirmed legacy SEO URL inventory BEFORE Stage 08**, not postponed beyond this dependency.
- **Full official CBS locality register, RU/EN/HE editorial verification, no ID/FK disruption BEFORE nationwide rollout**, not required for Ashdod-only pilot.
- **Before Stage 02 technical closure/merge:** independent new-diff Codex review PASS; if necessary fix and re-run targeted CI; obtain explicit owner permission to make PR #8 Ready/merge.
- **Before first public Ashdod pilot:** complete the relevant open release gates with evidence and obtain separate owner deployment approval. A code/CI PASS is not sufficient.

**Stage 02 status:** `TECHNICAL_IMPLEMENTATION_COMPLETE / CI_VERIFIED / OWNER_APPROVED_RELEASE_GATE_DEFERRAL / TARGETED_CODEX_REVIEW_PENDING / PR_DRAFT`. Stage 02 is not formally DONE or DEPLOYED. No code, migrations, DB records, production systems, or GitHub PR state changed by this decision.
