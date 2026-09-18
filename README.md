# Databeheer Cockpit LDV

Live dashboard voor het databeheer van de Linked Data Voorziening (LDV) van de
Rijksdienst voor het Cultureel Erfgoed. Combineert in één overzicht:

- **Diensten** — status van LDV-endpoints (Virtuoso/Jena), PoolParty-API's en
  publieke websites.
- **Pipelines** — status van de GitHub Actions-workflows die de LDV gevuld en
  gesynchroniseerd houden (thesauri-backups, ETL's, CHO-diffmonitor, ...).
  Kijkt niet alleen naar de laatste run-conclusie, maar ook of de workflow
  nog actief is (GitHub schakelt geplande workflows automatisch uit na 60+
  dagen inactiviteit in de repo) en of de laatste run niet te lang geleden is
  t.o.v. de verwachte cron-cadans.
- **Datakwaliteit** — cross-check RCE-datacatalogus t.o.v. het NDE
  Datasetregister, plus per TriplyDB-dataset (13 stuks: CHO, CHT, ABR,
  datacatalog, CEO, TOOI, ...) de triple count, laatste update en TriplyDB's
  eigen `hasDataQualityIssues`-vlag.

Bovenaan staat een KPI-rij en gezondheidsbalk (OK/warning/fail/onbekend) over
alle checks heen, en binnen elke sectie staan problemen bovenaan.

Onder de gezondheidsbalk staat een **Trends**-sectie: per dataset een
sparkline en een "problemen over tijd"-grafiek, gebaseerd op een SQLite-
historie (`data/history.sqlite`, 90 dagen bewaartermijn).

Bouwt voort op de aanpak van
[service-dashboard](https://github.com/cultureelerfgoed/service-dashboard),
maar als live webapp met een configureerbare bronnenlijst
(`config/sources.yaml`) in plaats van een periodiek gegenereerde README.

## Draaien

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # vul optioneel POOLPARTY_TOKEN / GITHUB_TOKEN in
uvicorn app.main:app --reload
```

Dashboard is dan bereikbaar op <http://127.0.0.1:8000>.

## Trendhistorie: lokaal schrijven vs. read-only op Render

De SQLite-historie kan op twee manieren gevuld worden:

1. **Lokaal / eigen server met schijf**: de live app schrijft zelf bij elke
   refresh naar `data/history.sqlite`. Standaardgedrag, geen extra config.
2. **Host zonder persistente schijf (bv. Render free tier)**: zet
   `HISTORY_REMOTE_URL` in `.env` (of als Render env var) op de raw URL van
   `data/history.sqlite` op de `data`-branch van deze repo. De app leest die
   dan read-only uit (elke 5 minuten opnieuw opgehaald) en schrijft zelf
   niets. Het bijhouden van die branch gebeurt door
   `.github/workflows/record-history.yml`, die onafhankelijk van waar de
   live app draait elke 30 minuten alle checks uitvoert en de historie
   commit naar de `data`-branch (los van `master`, geen ruis in de
   commit-geschiedenis van de code).

## Deployen op Render

Dit repo bevat een `render.yaml`-blueprint. In Render: New → Blueprint →
deze repo selecteren. Zet daarna handmatig de env vars die niet in git
horen (`GITHUB_TOKEN`, evt. `POOLPARTY_TOKEN`) via het Render-dashboard —
`render.yaml` markeert ze als `sync: false` zodat ze niet worden overschreven.
`HISTORY_REMOTE_URL` staat al goed in de blueprint.

## Uitbreiden

Nieuwe dienst, workflow of SPARQL-check toevoegen? Voeg een item toe aan
`config/sources.yaml` — geen codewijziging nodig, tenzij het een nieuw type
check betreft (dan een functie toevoegen in `app/checks/`).

## Openstaand / vervolgstappen

- Diepere koppeling met [cho-diff-monitor](https://github.com/cultureelerfgoed/cho-diff-monitor)
  (daadwerkelijke diff-resultaten i.p.v. alleen workflow-status) vraagt een
  TriplyDB-token en is nog niet geïmplementeerd.
- Eventuele databeheer-*acties* (backup herstarten, query's draaien via de
  `rce-cho` MCP) zijn bewust buiten scope gehouden voor v1 — dit is voorlopig
  een read-only cockpit.
- Zonder `GITHUB_TOKEN` loopt de Pipelines-sectie snel tegen GitHub's
  onbeauthenticated rate limit (60 requests/uur) aan — met 15+ workflows
  x 2 API-calls (state + laatste run) is een token in de praktijk nodig.
