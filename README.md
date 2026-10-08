# Bulk Certificate Generator

Backend API that accepts one request for many recipients and generates a PDF certificate for each valid person from a single template. Invalid recipients and individual generation errors are recorded on the job and do not discard the certificates that succeeded.

The stack is Python, FastAPI, and SQLite through SQLAlchemy.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate the virtual environment with `.venv\Scripts\activate`.

The default database file is `data/certificates.db`. Generated PDFs are written under `data/certificates/`. Both paths are created on startup.

To use another relational database, install a driver and set `DATABASE_URL` before starting the app. Postgres example:

```bash
export DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/certificates
```

`psycopg` is not installed by default. SQLite is enough to run the app and the tests.

## Run the application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 47231
```

Interactive docs are at [http://127.0.0.1:47231/docs](http://127.0.0.1:47231/docs). A health check is at `/health`.

Useful environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/certificates.db` | SQLAlchemy database URL |
| `CERTIFICATE_STORAGE_DIR` | `./data/certificates` | Directory for generated PDFs |

## Run tests

```bash
pytest
```

The tests use a temporary SQLite file and a temporary PDF directory. They do not touch `data/`.

## Submit a certificate generation request

`POST /api/certificate-jobs`

Send the shared certificate fields once, plus the full recipient list. The response is `202` with a job id. Generation continues after the response, so poll the job before downloading files.

```bash
curl -s -X POST http://127.0.0.1:47231/api/certificate-jobs \
  -H 'Content-Type: application/json' \
  -d @examples/request.json
```

Example body:

```json
{
  "title": "Certificate of Completion",
  "event_name": "Backend Engineering Workshop",
  "issuer": "Aereo Academy",
  "issued_on": "2026-10-08",
  "recipients": [
    {"name": "Ada Lovelace", "email": "ada@example.com", "detail": "Track: API design"},
    {"name": "Grace Hopper", "email": "grace@example.com", "detail": "Track: Systems"}
  ]
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `event_name` | yes | Printed on every certificate. 1–200 characters. |
| `issuer` | yes | Organisation name printed on every certificate. |
| `issued_on` | yes | ISO date (`YYYY-MM-DD`). |
| `title` | no | Defaults to `Certificate of Completion`. |
| `recipients` | yes | 1–1000 people. |
| `recipients[].name` | per person | Required for that person to succeed. |
| `recipients[].email` | no | Stored, printed, and checked when present. |
| `recipients[].detail` | no | Extra line on that person's certificate, up to 200 characters. |

A malformed body (missing event, empty list, bad date, more than 1000 recipients) returns `422` and does not create a job.

A recipient who fails validation still belongs to the job. That row is marked `failed` with a reason, and everyone else is still generated.

## Check job status

`GET /api/certificate-jobs/{job_id}`

```bash
curl -s http://127.0.0.1:47231/api/certificate-jobs/JOB_ID
```

The payload includes:

- `status`: `queued`, `processing`, `completed`, `completed_with_errors`, or `failed`
- `total`, `succeeded`, `failed`, `pending`
- `progress_percent`
- `certificates`: one entry per recipient, with `status`, `error`, and `download_url` when a PDF exists

`completed` means every certificate succeeded. `completed_with_errors` means at least one succeeded and at least one failed. `failed` means none succeeded.

## Retrieve generated certificates

One PDF:

```bash
curl -s -o ada.pdf http://127.0.0.1:47231/api/certificate-jobs/JOB_ID/certificates/CERTIFICATE_ID
```

The `download_url` on each successful certificate is that path. A failed or unfinished certificate returns `409`. An unknown id returns `404`.

Every successful PDF in the job, after the job has finished:

```bash
curl -s -o certificates.zip http://127.0.0.1:47231/api/certificate-jobs/JOB_ID/archive
```

The archive is omitted while the job is still `queued` or `processing` (`409`). If every recipient failed, the archive route returns `404`.

## Project layout

| Path | Role |
| --- | --- |
| `app/api.py` | HTTP routes |
| `app/service.py` | Job creation and the generation loop |
| `app/validation.py` | Per-recipient rules |
| `app/pdf.py` | The one certificate template |
| `app/models.py` | `jobs` and `certificates` tables |
| `tests/` | The required behaviours |

## Design decisions

**One request creates one job.** The client does not call the API once per person. The job row is the handle used to read progress and download results. Each recipient is a `certificates` row linked to that job, which is what makes partial success visible.

**Generation runs after the response.** FastAPI `BackgroundTasks` picks up the job after `202` is returned. A few hundred PDFs would otherwise hold the HTTP call open until the slowest file finished. The worker moves the job from `queued` to `processing`, commits each recipient, then sets a terminal status.

A synchronous handler would be fewer moving parts, and it would be fine for a handful of names. It fights the bulk requirement as soon as a client sends a large list, because the caller has no job id until every PDF is done. A separate queue such as Celery would survive a process restart and could run on more than one machine. It also needs a broker, which this assignment does not need in order to show the job model. The in-process task is the middle of those two: the API contract is already asynchronous, and the worker function can be moved to a queue later without changing the tables or the routes. A crash during `processing` can leave a job in that state until something reruns it. The worker refuses to start a job that is not `queued`, so a rerun has to set the status back first.

**Invalid people are failed rows, not a rejected batch.** The request shape is checked up front (`422`). Name, email, and detail are checked per recipient inside the worker. One empty name or one bad email does not throw away the valid PDFs in the same list. The job status lists each failure reason.

**One template, drawn in code.** `app/pdf.py` is the only layout. Recipient name, email, detail, event, issuer, date, and certificate id are the fields it prints. There is no template editor and no second design. ReportLab writes a normal PDF with built-in fonts, so there is no extra binary to install.

**SQLite is the default relational database.** The models are ordinary tables (`jobs`, `certificates`) mapped with SQLAlchemy. Tests and local runs need no database server. Point `DATABASE_URL` at Postgres when you want a server database; the queries do not use SQLite-only SQL.

**Stored files stay behind the API.** PDFs live on disk under the storage directory. Downloads go through the API, which checks the job, the certificate status, and that the path stays inside the storage directory.

## Tests and what they cover

| Test | Assignment item |
| --- | --- |
| `test_create_generation_job_returns_queued_progress` | Creating a generation job |
| `test_request_shape_is_validated` | Input validation of the request |
| `test_invalid_recipient_does_not_block_valid_ones` | Invalid recipient data inside an otherwise valid job |
| `test_certificate_generation_and_retrieval` | Certificate generation and retrieving PDFs |
| `test_job_status_reports_progress_before_and_after_generation` | Job status and progress |
| `test_one_generation_failure_does_not_stop_the_job` | One certificate failing while the others continue |
| `test_all_invalid_recipients_mark_the_job_failed` | A job where nothing could be generated |
