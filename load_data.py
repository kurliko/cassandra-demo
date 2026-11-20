"""Ładowanie danych MovieLens: prepared statements + zapis async.

Użycie:
  python load_data.py                # wszystkie oceny (~100 tys.)
  python load_data.py --oceny 5000   # tylko pierwsze 5 000 ocen
"""
import argparse
import csv
import time
from collections import deque
from datetime import datetime, timezone

from common import liczba, naglowek, polacz, sukces

KATALOG = "dane/ml-latest-small"
OKNO_ASYNC = 256      


def wczytaj(oceny_limit):
    """Czyta pliki CSV; zwraca (filmy, oceny)."""
    filmy = {}
    with open(f"{KATALOG}/movies.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            gatunki = set(r["genres"].split("|")) - {"(no genres listed)"}
            filmy[int(r["movieId"])] = (r["title"], gatunki)

    oceny = []
    with open(f"{KATALOG}/ratings.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            kiedy = datetime.fromtimestamp(int(r["timestamp"]), timezone.utc)
            oceny.append((int(r["userId"]), int(r["movieId"]),
                          float(r["rating"]), kiedy))
            if oceny_limit and len(oceny) >= oceny_limit:
                break
    return filmy, oceny


def zapisz(session, zapytanie, wiersze, nazwa):
    """Wysyła INSERT-y asynchronicznie, maks. OKNO_ASYNC naraz."""
    w_locie = deque()
    for i, wiersz in enumerate(wiersze, 1):
        w_locie.append(session.execute_async(zapytanie, wiersz))
        if len(w_locie) >= OKNO_ASYNC:
            w_locie.popleft().result()  
        if i % 10000 == 0:
            postep = liczba(i)
            print(f"\r  {nazwa:<17}{postep:>8}", end="", flush=True)
    for f in w_locie:
        f.result()         
    print(f"\r  {nazwa:<17}{liczba(len(wiersze)):>8} wierszy")
    return len(wiersze)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oceny", type=int, default=0,
                        help="ile ocen załadować (0 = wszystkie)")
    args = parser.parse_args()

    filmy, oceny = wczytaj(args.oceny)
    cluster, session = polacz()

    do_movies = session.prepare(
        "INSERT INTO movies (movie_id, title, genres) VALUES (?, ?, ?)")
    do_by_user = session.prepare(
        "INSERT INTO ratings_by_user"
        " (user_id, rated_at, movie_id, title, rating)"
        " VALUES (?, ?, ?, ?, ?)")
    do_by_movie = session.prepare(
        "INSERT INTO ratings_by_movie"
        " (movie_id, user_id, rating, rated_at)"
        " VALUES (?, ?, ?, ?)")

    naglowek(f"MovieLens: {liczba(len(filmy))} filmów,"
             f" {liczba(len(oceny))} ocen")
    start = time.perf_counter()

    razem = zapisz(session, do_movies,
                   [(m, t, g) for m, (t, g) in filmy.items()], "movies")
    razem += zapisz(session, do_by_user,
                    [(u, kiedy, m, filmy[m][0], r)
                     for u, m, r, kiedy in oceny], "ratings_by_user")
    razem += zapisz(session, do_by_movie,
                    [(m, u, r, kiedy) for u, m, r, kiedy in oceny],
                    "ratings_by_movie")

    czas = time.perf_counter() - start
    print(f"\n  razem:   {liczba(razem)} zapisów w {czas:.1f} s")
    print(f"  tempo:   {sukces(f'{liczba(razem / czas)} zapisów/s')}")
    cluster.shutdown()


if __name__ == "__main__":
    main()
