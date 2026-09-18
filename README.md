# Databeheer Cockpit LDV

Live dashboard voor het databeheer van de Linked Data Voorziening (LDV) van de
Rijksdienst voor het Cultureel Erfgoed. Combineert in één overzicht:

- **Diensten** — status van LDV-endpoints (Virtuoso/Jena), PoolParty-API's en
  publieke websites.
- **Pipelines** — status van de GitHub Actions-workflows die de LDV gevuld en
  gesynchroniseerd houden (thesauri-backups, ETL's, CHO-diffmonitor, ...).
- **Datakwaliteit** — cross-checks zoals de RCE-datacatalogus t.o.v. het NDE
  Datasetregister, en triple-tellingen van CHO/CHT.

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

- Historische trends (bv. triple-count over tijd) vragen persistente opslag;
  nu wordt alleen de actuele stand getoond.
- Diepere koppeling met [cho-diff-monitor](https://github.com/cultureelerfgoed/cho-diff-monitor)
  (daadwerkelijke diff-resultaten i.p.v. alleen workflow-status) vraagt een
  TriplyDB-token en is nog niet geïmplementeerd.
- Eventuele databeheer-*acties* (backup herstarten, query's draaien via de
  `rce-cho` MCP) zijn bewust buiten scope gehouden voor v1 — dit is voorlopig
  een read-only cockpit.
