[English](README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md) · [Ελληνικά](README.el.md) · [Italiano](README.it.md) · [Laconian Doric (reconstructed)](README.grc-x-laconian.md)

# Laconian

Laconian chiede la risposta completa più breve, non semplicemente la risposta più breve.

## Stato

Laconian è un progetto filosofico pubblico e un benchmark aperto in fase di sviluppo attivo.
Il repository contiene attualmente uno scheletro funzionante: una skill portabile, casi smoke
bilingui, quattro bracci di confronto, un percorso di replay offline, valutazione deterministica,
giudizi semantici ciechi facoltativi e un contratto simulato per un adattatore a un provider live.

Non sono ancora disponibili risultati pubblici del benchmark. Le fixture smoke convalidano
l'architettura; non dimostrano che `if` vinca, faccia risparmiare una quantità specifica o
funzioni meglio di un altro braccio.

## Perché «if»?

Plutarco, scrivendo secoli più tardi, tramanda in *Sulla loquacità* 17 (*Moralia* 511A) un
aneddoto su uno scambio scritto con Filippo II. Filippo scrive una minaccia riguardo all'ingresso in Laconia;
i Lacedemoni rispondono per iscritto con una sola parola dorica: `αἴκα`, «se». La lettera stessa
non è sopravvissuta. Ciò che sopravvive è il successivo racconto letterario di Plutarco, non un
documento contemporaneo.

La storia è un'immagine per il progetto, non una prova dell'ipotesi del benchmark. Non è
nemmeno la storia di un ingresso mai avvenuto: in Polibio 9.33 un oratore riconosce che Filippo
entrò in Laconia con un esercito.

## Cosa fa la skill

[`skills/if/SKILL.md`](skills/if/SKILL.md) chiede a un agente di determinare prima la risposta
completa, quindi di rimuovere soltanto ciò che può essere eliminato senza indebolire correttezza,
sicurezza, requisiti, fatti sostanziali, incertezza, sufficienza pratica, chiarezza, tono o
linguaggio naturale.

Rimuove saluti, riformulazioni, narrazione del processo non richiesta, ripetizioni e ornamenti
prima di rimuovere contenuto sostanziale. Conserva i dettagli richiesti e il testo esatto di
codice, comandi, errori, numeri, versioni, URL, identificatori, citazioni e strutture leggibili
dalle macchine quando la forma esatta è importante.

La skill è costituita da un solo file esclusivamente Markdown. Non contiene script, dipendenze,
permessi, riferimenti, risorse, chiamate di rete o istruzioni per strumenti specifici di una
piattaforma.

## Cosa non fa la skill

`if` non trasforma la prosa in linguaggio primitivo, non sostituisce le prove con la certezza,
non nasconde avvertenze sostanziali, non abbrevia le chiamate agli strumenti, non minimizza il
codice, non comprime il contesto di input e non esegue azioni. Non prevale su una richiesta di
un tutorial dettagliato, una struttura fissa, prove, esempi o una lunghezza obbligatoria. Non
promette che ogni agente o modello risponda allo stesso modo.

## Installazione e disinstallazione

La modalità consigliata consiste nell'installare il plugin dal repository con una versione fissata:

```bash
codex plugin marketplace add agent-axiom/laconian --ref v0.1.0-alpha.1 --json
codex plugin add laconian@laconian --json
```

Invocare la skill installata con `$laconian:if`. Se non appare subito, avviare una nuova attività
o riavviare Codex. Verificarne il rilevamento con:

```bash
codex plugin list --marketplace laconian --json
```

Disinstallazione del plugin:

```bash
codex plugin remove laconian@laconian --json
codex plugin marketplace remove laconian --json
```

Per un'installazione autonoma del singolo file con versione fissata:

```bash
(
  set -eu
  skill_dir="$HOME/.agents/skills/if"
  skill_target="$skill_dir/SKILL.md"
  skill_expected_sha256="5c549c7c492c66a6b3ac5560499353b71615ffc6b93c4b1811f741a8f3d54006"
  test ! -L "$skill_dir"
  mkdir -p "$skill_dir"
  test ! -L "$skill_dir"
  test ! -e "$skill_target"
  test ! -L "$skill_target"
  skill_tmp="$(mktemp "$skill_dir/.SKILL.md.XXXXXX")"
  trap 'rm -f "$skill_tmp"' EXIT
  curl -fsSL "https://raw.githubusercontent.com/agent-axiom/laconian/v0.1.0-alpha.1/skills/if/SKILL.md" -o "$skill_tmp"
  if command -v sha256sum >/dev/null 2>&1; then
    skill_actual_sha256="$(sha256sum "$skill_tmp")"
  else
    skill_actual_sha256="$(shasum -a 256 "$skill_tmp")"
  fi
  skill_actual_sha256="${skill_actual_sha256%% *}"
  test "$skill_actual_sha256" = "$skill_expected_sha256"
  chmod 0644 "$skill_tmp"
  ln "$skill_tmp" "$skill_target"
  if ! test "$skill_tmp" -ef "$skill_target"; then
    skill_misdirected="$skill_target/${skill_tmp##*/}"
    if test -f "$skill_misdirected" &&
      test ! -L "$skill_misdirected" &&
      test "$skill_tmp" -ef "$skill_misdirected"; then
      rm "$skill_misdirected"
    fi
    false
  fi
)
```

Il programma di installazione rifiuta un collegamento simbolico sia per la directory della skill
sia per la destinazione e non sovrascrive alcun percorso di destinazione esistente.

Invocare la skill autonoma con `$if`. Verificare il file copiato con:

```bash
test -s "$HOME/.agents/skills/if/SKILL.md"
```

La disinstallazione autonoma accetta soltanto il file regolare non modificato. Rifiuta un
collegamento simbolico sia per la directory della skill sia per il file di destinazione, oltre ai
file modificati o sostituiti; questi casi richiedono un controllo manuale. Rimuove la directory
soltanto se è vuota:

```bash
(
  set -eu
  skill_dir="$HOME/.agents/skills/if"
  skill_target="$skill_dir/SKILL.md"
  skill_expected_sha256="5c549c7c492c66a6b3ac5560499353b71615ffc6b93c4b1811f741a8f3d54006"
  test ! -L "$skill_dir"
  test -d "$skill_dir"
  test -f "$skill_target"
  test ! -L "$skill_target"
  if command -v sha256sum >/dev/null 2>&1; then
    skill_actual_sha256="$(sha256sum "$skill_target")"
  else
    skill_actual_sha256="$(shasum -a 256 "$skill_target")"
  fi
  skill_actual_sha256="${skill_actual_sha256%% *}"
  test "$skill_actual_sha256" = "$skill_expected_sha256"
  rm "$skill_target"
  rmdir "$skill_dir" 2>/dev/null || true
)
```

## Benchmark a quattro bracci

Ogni caso di risposta viene confrontato usando lo stesso modello, prompt utente, impostazioni
di generazione, disponibilità degli strumenti e posizione dell'istruzione. Cambia soltanto
l'istruzione di confronto:

| Braccio | Istruzione aggiunta |
|---|---|
| `baseline` | Nessuna |
| `concise` | Esattamente `Answer concisely.` |
| `caveman` | Uno snapshot offline dell'intera skill Caveman fissato a livello di byte |
| `if` | I byte esatti di `skills/if/SKILL.md` in questo repository |

L'ipotesi principale è `if` rispetto a `concise`. I bracci `baseline` e `caveman` forniscono
contesto; non sono sostituti più facili del confronto principale. L'attivazione e la qualità
della risposta vengono valutate separatamente.

## Soglia di qualità e metriche riportate

I vincoli deterministici vengono verificati prima della brevità. Un giudizio semantico
facoltativo può poi valutare i fatti richiesti e le avvertenze sostanziali senza ricevere il
nome del braccio. Una risposta non valida non può vincere soltanto perché è breve; le differenze
appaiate includono solo le coppie corrispondenti di caso e ripetizione nelle quali entrambe le
risposte superano la soglia di qualità selezionata.

I report mantengono metriche separate per il successo secondo i criteri rigidi e semantici, le
violazioni di valori esatti e formato, gli errori del provider, i tentativi ripetuti, i token o
caratteri di output, i dati di latenza negli artefatti grezzi e la differenza appaiata tra `if`
e `concise`. Non esiste un punteggio composito. Il costo viene stimato soltanto a partire da
uno snapshot dei prezzi esplicito e datato e da una contabilizzazione sufficientemente completa
dei token e della cache del provider. Consultare la [metodologia completa del benchmark](benchmarks/methodology.md).

## Avvio rapido

Il percorso di replay offline non richiede accesso alla rete né credenziali del provider:

```bash
uv sync --all-extras
uv run laconian validate evals/cases/response-smoke.yaml
uv run laconian validate evals/cases/activation-smoke.yaml
uv run laconian validate evals/manifests/replay-smoke.yaml
uv run laconian run evals/manifests/replay-smoke.yaml --results-root benchmarks/results
```

L'ultimo comando stampa la directory univoca dell'esecuzione. Copiare quel percorso in
`RUN_DIR`, quindi calcolare i punteggi e generare il report:

```bash
RUN_DIR="benchmarks/results/PASTE_THE_PRINTED_DIRECTORY_NAME"
uv run laconian score "$RUN_DIR/raw.jsonl" --cases evals/cases/response-smoke.yaml --output "$RUN_DIR/scored"
uv run laconian report "$RUN_DIR/scored/scored.jsonl" --output "$RUN_DIR/report.md"
```

Questi output di replay sono artefatti locali di verifica, non prove pubblicate del benchmark.

### Esecuzione live facoltativa

```bash
export OPENAI_API_KEY="your key"
uv sync --extra openai
uv run laconian run evals/manifests/openai-example.yaml --results-root benchmarks/results
```

Questo comando comporta un costo addebitato dal provider. La disponibilità del modello può
variare in base all'account e alla data. Le chiavi API devono trovarsi soltanto nella variabile
d'ambiente configurata; non inserirle mai nei manifest o nei file dei risultati registrati nel
repository. Un'esecuzione live non è pronta per la pubblicazione finché non sono stati verificati
l'identificatore del modello, gli artefatti grezzi, il metodo e le limitazioni.

## Mappa del repository

| Percorso | Scopo |
|---|---|
| `skills/if/SKILL.md` | L'intera skill portabile |
| `src/laconian_eval/` | Runner indipendente dal provider, valutazione, confine dei giudizi e reportistica |
| `evals/cases/` | Input appaiati in inglese e russo per risposte e attivazione |
| `evals/manifests/` | Configurazione riproducibile dell'esecuzione |
| `evals/baselines/caveman/` | Fixture di benchmark di terze parti fissata e attribuzione |
| `tests/fixtures/` | Dati sintetici di replay e del giudice per i test offline |
| `benchmarks/methodology.md` | Regole per un confronto pubblicabile |
| `benchmarks/results/` | Futuri artefatti pubblici e immutabili delle esecuzioni |
| `docs/` | Indicazioni su progettazione, filosofia e contributo di casi |

## Contribuire

Iniziare da [CONTRIBUTING.md](CONTRIBUTING.md). I nuovi casi devono essere sostenuti da prove,
neutrali rispetto ai bracci e appaiati in inglese e russo. Le affermazioni sul benchmark
richiedono i corrispondenti artefatti grezzi. Le segnalazioni sensibili per la sicurezza seguono
[SECURITY.md](SECURITY.md), non una issue pubblica.

## Licenze

Le licenze seguono la mappa in [NOTICE](NOTICE):

- codice, test, configurazione dei workflow e `skills/if/SKILL.md`: Apache-2.0 secondo [LICENSE](LICENSE);
- file README, documentazione del progetto, casi e manifest di valutazione, metodologia e
  risultati pubblicati: [CC BY 4.0](LICENSES/CC-BY-4.0.txt);
- snapshot fissato di Caveman: [MIT](LICENSES/CAVEMAN-MIT.txt), con provenienza upstream in
  [`evals/baselines/caveman/SOURCE.md`](evals/baselines/caveman/SOURCE.md).

## Fonti storiche e linguistiche

- [Plutarco, *Sulla loquacità* 17 (*Moralia* 511A)](https://www.perseus.tufts.edu/hopper/text?doc=Perseus%3Atext%3A2008.01.0287%3Asection%3D17), per il successivo racconto letterario e `αἴκα`.
- [Eva A. Mitchell, *Laconian Dialect*, Università di Edimburgo](https://era.ed.ac.uk/items/385e1ac5-539c-47f6-94b7-8ab83a94a139), per le testimonianze frammentarie ed eterogenee sul laconico antico.
- [Polibio, *Storie* 9.33](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Polybius/9%2A.html), per la testimonianza antica che Filippo entrò in Laconia con un esercito.
