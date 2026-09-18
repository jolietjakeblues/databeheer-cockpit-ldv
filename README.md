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
- **Datakwaliteit** — cross-checks zoals de RCE-datacatalogus t.o.v. het NDE
  Datasetregister, en triple-tellingen van CHO/CHT.

Bovenaan staat een KPI-rij en gezondheidsbalk (OK/warning/fail/onbekend) over
alle checks heen, en binnen elke sectie staan problemen bovenaan.

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

## Uitbreiden

Nieuwe dienst, workflow of SPARQL-check toevoegen? Voeg een item toe aan
`config/sources.yaml` — geen codewijziging nodig, tenzij het een nieuw type
check betreft (dan een functie toevoegen in `app/checks/`).

## Openstaand / vervolgstappen

- Historische trends (bv. triple-count of pipeline-gezondheid over tijd)
  vragen persistente opslag (bv. SQLite); nu wordt alleen de actuele stand
  getoond, incl. de huidige-status gezondheidsbalk.
- Diepere koppeling met [cho-diff-monitor](https://github.com/cultureelerfgoed/cho-diff-monitor)
  (daadwerkelijke diff-resultaten i.p.v. alleen workflow-status) vraagt een
  TriplyDB-token en is nog niet geïmplementeerd.
- Eventuele databeheer-*acties* (backup herstarten, query's draaien via de
  `rce-cho` MCP) zijn bewust buiten scope gehouden voor v1 — dit is voorlopig
  een read-only cockpit.
- Zonder `GITHUB_TOKEN` loopt de Pipelines-sectie snel tegen GitHub's
  onbeauthenticated rate limit (60 requests/uur) aan — met 15+ workflows
  x 2 API-calls (state + laatste run) is een token in de praktijk nodig.
