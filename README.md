# Eco-Travel Advisor

A conversational agent for sustainable tourism planning, built with Rasa Open
Source (NLU + Core), a Neon PostgreSQL backend, and a Streamlit frontend. The
assistant helps travellers plan low-carbon trips by recommending eco-certified
accommodation, low-carbon transport, verified carbon offset programs, and
community-friendly cultural experiences, while estimating the carbon footprint
of travel options and escalating complex cases to a human advisor.

## Architecture

- Rasa NLU: `DIETClassifier` pipeline with lookup tables for cities and
  transport modes.
- Rasa Core: stories and rules, manual slot filling, a two-stage fallback that
  re-prompts with quick-reply buttons before offering human handover.
- Action server (`actions/actions.py`): adaptive trip intake, weighted
  recommendations, carbon estimation via the Climatiq API (with a standard
  emission-factor fallback), real road-distance refinement for ground transport
  via OpenRouteService (geocoded with OpenCage), human handover with full
  context packaging, and failure auditing.
- Database (Neon PostgreSQL): catalogue tables (eco hotels, transport options,
  offset programs, cultural experiences, FAQ with full-text search) plus
  conversation tables (sessions, messages, trip plans, handover requests,
  preferences, action log), seeded at scale with Faker.
- Frontend (Streamlit): a Chat page with dynamic quick-reply buttons and
  colour-coded carbon result cards (green / amber / red), an Eco dashboard with
  analytics, and a Trip history page.

## Configuration

No secret is stored in the source. Configuration is resolved from Google Colab
Secrets when running in Colab, and from environment variables (a `.env` file)
when running with Docker. Copy `.env.example` to `.env` and fill in:

- `DATABASE_URL` (Neon connection string) — required
- `CLIMATIQ_API_KEY` — optional (falls back to standard emission factors)
- `OPENCAGE_API_KEY`, `ORS_API_KEY` — optional location services
- `NGROK_AUTH_TOKEN` — only for the Colab tunnelling demo

## Run with Docker

```
git clone <your-repo-url>
cd eco_travel
cp .env.example .env        # then edit .env with your values
docker compose up --build
```

Then open the Streamlit interface at http://localhost:8501. The Rasa API is on
port 5005; the action server runs on the internal network only and is not
publicly exposed.

The database is hosted on Neon and must contain data. If you have not already
created and seeded it from the Colab notebook, do it once from Docker (the
action server image ships the schema and seeding code):

```
docker compose run --rm action_server \
  python -c "import db, seed; db.create_tables(); seed.seed_all()"
```


## Run the database setup (once)

From a Python 3.8 environment with the application dependencies installed:

```
python -c "import db; db.create_tables()"
python -c "import db; db.reset_data()"   # optional, clears existing rows
python -c "import seed; seed.seed_all()" # seeds large synthetic volumes
```

## Tests

- `rasa test nlu --nlu tests/test_nlu.yml --config config.yml --out results`
- `rasa test core --stories tests/test_stories.yml`
- `pytest -q` (unit tests for services and actions; external calls are mocked)

## Future extensions (documented, not implemented)

- Deployment to HuggingFace Spaces (Docker SDK) as a zero-cost public demo.
- Multilingual support through an additional language model in the NLU pipeline.
- Voice interaction using Whisper for speech-to-text and gTTS for speech output.
- Server-side conversation persistence via a Rasa SQL tracker store on Neon.

## Deploy to HuggingFace Spaces (zero-cost cloud)

The project can be hosted on HuggingFace Spaces using the Docker SDK, which the
brief recommends as a free demonstration platform:

1. Create a new Space and choose the Docker SDK.
2. Push this repository to the Space (or connect the GitHub repo).
3. In the Space settings, add the same variables as the local `.env`
   (`DATABASE_URL`, `CLIMATIQ_API_KEY`, `OPENCAGE_API_KEY`, `ORS_API_KEY`) as
   private Secrets, so no key is committed.
4. Expose the Streamlit port (8501) as the Space app port.

For development, Pyngrok can tunnel the local Streamlit or Rasa server for a
quick shareable demo without deploying.

## Optional spaCy pipeline

`config_spacy.yml` provides a spaCy tokeniser and featuriser variant of the NLU
pipeline. Install `spacy` and `en_core_web_md`, then train with
`rasa train --config config_spacy.yml`. The default `config.yml` (Rasa's
standard DIET pipeline) is recommended and is what the tests use.
