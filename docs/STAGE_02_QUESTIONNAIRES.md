# ZemiPro — Stage 02.5: configurable service questionnaires

**Status:** `IMPLEMENTED / QA_PENDING`, same Stage 02 branch and Draft PR #8.
No VPS, production database, PSEO, Cloudflare, DNS or live site changes.

## Design

`ServiceQuestionnaire` (per concrete `Subcategory`) holds an editable JSON
**draft**. Its published `QuestionnaireVersion` is a separate row with an
immutable schema and monotonically increasing version number. Publication
requires the explicit **"Опубликовать новые версии выбранных анкет"** action
from Django Admin, which locks the questionnaire row and creates a version
only when its validated draft differs from the existing published schema.

`OrderQuestionnaireAnswer` holds a private order-level snapshot:
`version`, `schema_snapshot` and `answers`. Every answer is keyed by
stable question and option keys. The question's original RU/EN/HE label,
choices and dependency are frozen with that order. Later changes to draft
questions or choice labels cannot alter older order interpretation. Existing
orders without subcategory/questions remain unchanged and valid.

**Schema example** (JSON Admin draft):

```json
[
  {
    "key": "issue",
    "type": "single",
    "labels": {
      "ru": "Где протечка?",
      "en": "Where is the leak?",
      "he": "איפה הנזילה?"
    },
    "required": true,
    "options": [
      {
        "value": "pipe",
        "labels": {
          "ru": "Труба",
          "en": "Pipe",
          "he": "צינור"
        }
      },
      {
        "value": "faucet",
        "labels": {
          "ru": "Кран",
          "en": "Faucet",
          "he": "ברז"
        }
      }
    ]
  }
]
```

Supported types are `text` (max 500 characters), `single`, `multiple`,
`number` (bounded numeric field), `date` (ISO date) and `boolean`.
At most 20 questions and 20 options per choice, required flag, one-level
`depends_on: {"key":"issue","equals":"pipe"}` pointing to an earlier
single/boolean question. No custom script, HTML or arbitrary code is allowed
in schemas; all RU/EN/HE translations are required.

HTTP GET `/api/questionnaire/{service_id}/` returns only **published**
localized schema and stable option IDs. Client builds DOM controls safely,
while Django Form re-constructs choices and dependencies server-side from
the active published version and rejects stale version/tampered options.
Order+snapshot write is one atomic DB transaction. Answers do not appear on
public order cards or APIs, and only owner/authorized assigned worker can
view them in order detail. No change to existing order/contact privacy policy.

## Sample drafts

Operator-controlled `seed_demo_questionnaires` offers four **non-final**
pilot questionnaire templates: `plumbing/leak-repair`,
`tutoring/math-tutoring`, `website-development/landing-page`,
`event-services/event-photography`. Samples cover all six types,
requiredness, translated choices and conditional questions. The sample
seed neither runs in migrations nor production entrypoints, neither deletes
data nor overwrites existing editable drafts. `--publish` is always
explicit, never default.

**Isolated test DB only:**

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py seed_service_catalog
python manage.py seed_demo_questionnaires --plan
python manage.py seed_demo_questionnaires --publish
python manage.py seed_demo_questionnaires --check
python manage.py seed_demo_questionnaires --publish
python manage.py test apps.marketplace.tests.test_stage02_questionnaires
python manage.py test
```

Expected on fresh test DB with catalog: 4 questionnaires, 4 first versions;
repeat `--publish` creates zero versions. Legacy orders and their IDs remain
untouched. Do not execute seed on production.

## Gates

- Independent PostgreSQL CI (Django, Ruff, migration check, idempotent
  seed, full suite) and ephemeral staging Docker smoke — **PENDING**.
- Native-speaker RU/EN/HE editorial review of demonstrative wording, and
  mobile RTL at 320/360/375/390/768 widths — Stage 02.6.
- The entire Stage 02 remains `IN_PROGRESS` until 02.6 integrated
  validation and owner decision. Draft PR #8 **must not be merged**.
