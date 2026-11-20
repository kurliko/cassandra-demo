# Apache Cassandra: demo klastra 3 węzłów

Lokalny klaster **Apache Cassandra 5.0** (3 węzły w Dockerze) i skrypty w Pythonie,
które pokazują:

- model danych: klucz partycji, klucz klastrujący, denormalizację (te same dane w dwóch tabelach),
- różnicę między zapytaniem po kluczu partycji a zapytaniem bez klucza (`ALLOW FILTERING`),
- poziomy spójności `ONE`, `QUORUM` i `ALL`, także po awarii jednego węzła,
- powrót węzła i dosłanie zaległych zapisów (*hinted handoff*).

Dane to prawdziwy, publiczny zbiór **MovieLens** (oceny filmów): 610 użytkowników,
9 742 filmy, 100 836 ocen.

## Zawartość repozytorium

| Plik | Co zawiera |
|---|---|
| `docker-compose.yml` | 3 węzły Cassandry (`cass1` = seed), mały heap, healthchecki, start po kolei |
| `schema.cql` | keyspace `movielens` (NetworkTopologyStrategy, RF = 3) i tabele `movies`, `ratings_by_user`, `ratings_by_movie` |
| `load_data.py` | ładuje MovieLens z plików CSV (prepared statements, zapis asynchroniczny) |
| `queries.py` | zapytania demonstracyjne: `partycja`, `filtr`, `spojnosc` |
| `common.py` | połączenie z klastrem (domyślny poziom spójności QUORUM) |
| `requirements.txt` | zależności Pythona (`cassandra-driver`) |
| `dane/ml-latest-small/` | dane MovieLens (CSV) |

## Wymagania

- **Docker** z **Docker Compose v2** (polecenie `docker compose`):
  - Linux: Docker Engine,
  - Windows: Docker Desktop z backendem WSL2 (komendy uruchamiamy w terminalu WSL),
  - macOS: Docker Desktop.
- **Python 3.10+**.
- **ok. 4–5 GB wolnego RAM-u** dla Dockera (każdy węzeł zużywa ok. 1,2 GB).
- Wolny port **9042** na hoście.

Javy nie trzeba instalować: jest w obrazie Dockera `cassandra:5.0`.

## Instalacja (jednorazowo)

```bash
git clone <adres-repozytorium> cassandra-demo
cd cassandra-demo
```

Środowisko Pythona:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Obraz Cassandry (ok. 540 MB):

```bash
docker pull cassandra:5.0
```

## Uruchomienie klastra

```bash
docker compose up -d --wait
```

Węzły startują po kolei (`cass1` → `cass2` → `cass3`), całość trwa ok. 1–2 minut.
`--wait` kończy się, gdy wszystkie trzy są zdrowe. Sprawdzenie:

```bash
docker exec cass1 nodetool status
```

Gotowe, gdy są trzy wiersze zaczynające się od `UN` (Up, Normal).

## Demo krok po kroku

Wszystkie komendy uruchamiaj w katalogu repozytorium, z aktywnym środowiskiem
(`source .venv/bin/activate`).

**1. Schemat i dane**

```bash
docker exec -i cass1 cqlsh < schema.cql
python load_data.py
```

Ładowanie zapisuje ok. 211 tys. wierszy (każda ocena trafia do dwóch tabel)
i trwa ok. pół minuty.

**2. Zapytania**

```bash
python queries.py partycja    # odczyt po kluczu partycji (oceny użytkownika 414, film Matrix)
python queries.py filtr       # zapytania bez klucza partycji: błąd i ALLOW FILTERING
docker exec cass1 nodetool getendpoints movielens ratings_by_user 414   # repliki partycji
```

**3. Poziomy spójności i awaria węzła**

```bash
python queries.py spojnosc    # 6× SUKCES
docker stop cass3             # awaria jednego węzła
python queries.py spojnosc    # ONE i QUORUM działają, ALL: Unavailable
```

Zapisy testowe z `spojnosc` trafiają do użytkownika `0`, którego nie ma w MovieLens.

**4. Powrót węzła i hinted handoff**

```bash
python load_data.py --oceny 5000     # zapis, gdy cass3 nie działa
docker start cass3
docker exec cass1 nodetool status    # poczekaj, aż cass3 będzie UN
docker logs cass1 2>&1 | grep "Finished hinted handoff"
python queries.py spojnosc           # znowu 6× SUKCES
```

**5. (Opcjonalnie) Konsola CQL i śledzenie zapytań**

```bash
docker exec -it cass1 cqlsh
```

```sql
TRACING ON;
SELECT title, rating FROM movielens.ratings_by_user WHERE user_id = 414 LIMIT 3;
```

## Uwagi techniczne

- **Port:** z hosta dostępny jest tylko port węzła `cass1` (9042). Skrypty łączą się
  wyłącznie z nim (`WhiteListRoundRobinPolicy` w `common.py`), bo pozostałe węzły
  podają sterownikowi wewnętrzne adresy sieci Dockera, które z hosta (np. z Docker
  Desktop) bywają nieosiągalne. Dlatego w demo zatrzymuje się `cass3`, a nie `cass1`.
- **Pamięć:** `MAX_HEAP_SIZE=512M` i limit 1,5 GB na kontener, żeby 3 węzły zmieściły
  się na laptopie. Produkcyjnie heap ma kilka–kilkanaście GB.
- **Szybszy start:** `ring_delay_ms=5000` i `skip_wait_for_gossip_to_settle=0`
  przyspieszają dołączanie węzłów. To ustawienia tylko do celów demonstracyjnych.
- **Windows (WSL2):** jeśli WSL ma mało pamięci, można ją zwiększyć w pliku
  `%UserProfile%\.wslconfig` (`[wsl2]`, `memory=10GB`), a potem `wsl --shutdown`.

## Rozwiązywanie problemów

| Objaw | Co zrobić |
|---|---|
| `Cannot connect to the Docker daemon` | Uruchom Dockera (Docker Desktop) i poczekaj, aż wystartuje. |
| Węzeł `unhealthy` albo nie wstaje | `docker compose logs cass2 \| tail -40`, potem ponownie `docker compose up -d --wait`. |
| Kontener kończy się kodem 137 | Zabrakło pamięci: zwolnij RAM albo zwiększ limit Dockera/WSL. |
| `NoHostAvailable` w Pythonie | `cass1` nie działa lub jeszcze startuje: `docker compose ps`. |
| `ModuleNotFoundError: cassandra` | Aktywuj środowisko: `source .venv/bin/activate`. |
| Brak keyspace’u `movielens` | Najpierw wczytaj schemat (krok 1). |
| Po `docker start cass3` ALL nadal zwraca błąd | Węzeł jeszcze nie jest `UN`: odczekaj 10–20 s. |

## Sprzątanie

```bash
docker compose stop        # zatrzymanie (dane zostają)
docker compose down -v     # usunięcie kontenerów i danych
```

## Dane i licencja

Zbiór **MovieLens ml-latest-small** pochodzi z [GroupLens](https://grouplens.org/datasets/movielens/)
(University of Minnesota). Wolno go używać do celów niekomercyjnych, z podaniem źródła:

> F. Maxwell Harper and Joseph A. Konstan. 2015. The MovieLens Datasets: History and Context.
> ACM Transactions on Interactive Intelligent Systems (TiiS) 5, 4: 19:1–19:19.
> https://doi.org/10.1145/2827872

Pełne warunki licencji: `dane/ml-latest-small/README.txt`. Gdyby danych zabrakło,
można je pobrać ponownie:

```bash
mkdir -p dane && curl -L -o dane/ml-latest-small.zip https://files.grouplens.org/datasets/movielens/ml-latest-small.zip
python3 -c "import zipfile; zipfile.ZipFile('dane/ml-latest-small.zip').extractall('dane')"
```
