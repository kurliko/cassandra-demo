"""Zapytania demonstracyjne na danych MovieLens.

Użycie:
  python queries.py              # wszystko
  python queries.py partycja     # 1. odczyt po kluczu partycji
  python queries.py filtr        # 2. zapytania spoza klucza
  python queries.py spojnosc     # 3. ONE / QUORUM / ALL
"""
import sys
import textwrap
import time
from datetime import datetime, timezone

from cassandra import ConsistencyLevel as CL
from cassandra import InvalidRequest, Unavailable
from cassandra.cluster import NoHostAvailable
from cassandra.query import SimpleStatement

from common import ZOLTY, RESET, blad, liczba, naglowek, polacz, sukces

UZYTKOWNIK = 414      # najaktywniejszy użytkownik (2 698 ocen)
FILM = 2571           # Matrix (1999)
UZYTKOWNIK_DEMO = 0   # nie ma go w MovieLens - tu zapisujemy testy


def zmierz(session, zapytanie, parametry=None):
    """Wykonuje zapytanie; zwraca (wiersze, czas w ms)."""
    start = time.perf_counter()
    wynik = list(session.execute(zapytanie, parametry))
    return wynik, (time.perf_counter() - start) * 1000


def tabela(naglowki, wiersze):
    """Prosta tabelka tekstowa (bez dodatkowych bibliotek)."""
    szer = [max(len(str(x)) for x in kol)
            for kol in zip(naglowki, *wiersze)]
    linia = lambda w: "  ".join(f"{str(x):<{s}}" for x, s in zip(w, szer))
    print("  " + linia(naglowki))
    print("  " + "  ".join("-" * s for s in szer))
    for w in wiersze:
        print("  " + linia(w))



def demo_partycja(session):
    naglowek(f"1. Partycja = wszystkie oceny użytkownika {UZYTKOWNIK}")
    print(f"  ratings_by_user WHERE user_id = {UZYTKOWNIK} LIMIT 5")

    wiersze, ms = zmierz(session,
        "SELECT rated_at, title, rating FROM ratings_by_user"
        " WHERE user_id = %s LIMIT 5", (UZYTKOWNIK,))
    tabela(["kiedy", "film", "ocena"],
           [(r.rated_at.strftime("%Y-%m-%d %H:%M"), r.title[:38],
             f"{r.rating:.1f} ★") for r in wiersze])
    print(f"  -> {sukces(f'{ms:.1f} ms')}, najnowsze pierwsze"
          " (CLUSTERING ORDER BY rated_at DESC)")

    # zakres po kluczu klastrującym: oceny z 2018 roku
    wiersze, ms = zmierz(session,
        "SELECT count(*) FROM ratings_by_user"
        " WHERE user_id = %s AND rated_at >= '2018-01-01'",
        (UZYTKOWNIK,))
    print("\n  Oceny z 2018 r. (rated_at >= '2018-01-01'):"
          f" {wiersze[0][0]} w {sukces(f'{ms:.1f} ms')}")

    token = session.execute(
        "SELECT token(user_id) AS t FROM ratings_by_user"
        " WHERE user_id = %s LIMIT 1", (UZYTKOWNIK,)).one()
    print(f"  Token partycji (Murmur3): {token.t}")

    print("\n  Te same oceny, inna tabela"
          " (ratings_by_movie, partycja = film):")
    film = session.execute(
        "SELECT title FROM movies WHERE movie_id = %s", (FILM,)).one()
    wiersze, ms = zmierz(session,
        "SELECT count(*) AS ile, avg(rating) AS srednia"
        " FROM ratings_by_movie WHERE movie_id = %s", (FILM,))
    print(f"  {film.title}: {wiersze[0].ile} ocen,"
          f" średnia {wiersze[0].srednia:.2f} ★"
          f" -> {sukces(f'{ms:.1f} ms')}")



def proba(session, opis, zapytanie):
    """Wykonuje zapytanie i drukuje SUKCES/BŁĄD z wyjaśnieniem."""
    print(f"\n  {opis}")
    print(f"  {ZOLTY}{zapytanie}{RESET}")
    try:
        wiersze, ms = zmierz(session, zapytanie)
        print(f"  -> {sukces()}: {liczba(wiersze[0][0])} wierszy"
              f" w {ms:.0f} ms")
    except InvalidRequest as e:
        komunikat = str(e).split('message="')[-1].rstrip('"}')
        print(f"  -> {blad()} (InvalidRequest):")
        print(textwrap.fill(komunikat, 66, initial_indent="     ",
                            subsequent_indent="     "))


def demo_filtr(session):
    naglowek("2. Zapytania spoza klucza")

    proba(session, "a) Filtr po zwykłej kolumnie:",
          "SELECT count(*) FROM ratings_by_user WHERE rating = 5")
    print("     Cassandra nie wie, w których partycjach szukać"
          "\n     -> musiałaby przeczytać WSZYSTKIE węzły.")

    proba(session, "b) Zakres dat bez klucza partycji:",
          "SELECT count(*) FROM ratings_by_user"
          " WHERE rated_at >= '2018-01-01'")
    print("     Bez user_id nie da się policzyć tokenu"
          "\n     -> nie wiadomo, na którym węźle leżą dane.")

    proba(session, "c) Wymuszenie pełnego skanu:",
          "SELECT count(*) FROM ratings_by_user WHERE rating = 5"
          " ALLOW FILTERING")
    print("     Działa, ale skanuje cały klaster - nie do produkcji."
          "\n     Rozwiązanie: osobna tabela pod to zapytanie"
          " (denormalizacja).")


def opisz_blad(e):
    """Krótki opis wyjątku dla publiczności."""
    if isinstance(e, NoHostAvailable) and e.errors:
        e = next(iter(e.errors.values()))
    if isinstance(e, Unavailable):
        return (f"Unavailable: potrzeba {e.required_replicas},"
                f" żywych {e.alive_replicas}")
    return type(e).__name__


def demo_spojnosc(session):
    naglowek("3. Poziomy spójności (RF = 3, QUORUM = 2)")
    odczyt = ("SELECT title, rating FROM ratings_by_user"
              " WHERE user_id = %s LIMIT 10")
    zapis = ("INSERT INTO ratings_by_user"
             " (user_id, rated_at, movie_id, title, rating)"
             " VALUES (%s, %s, 2571, 'Matrix, The (1999)', 5.0)")

    wyniki = []
    for poziom in (CL.ONE, CL.QUORUM, CL.ALL):
        nazwa = CL.value_to_name[poziom]
        for operacja, cql in (("ODCZYT", odczyt), ("ZAPIS", zapis)):
            stmt = SimpleStatement(cql, consistency_level=poziom)
            params = ((UZYTKOWNIK,) if operacja == "ODCZYT"
                      else (UZYTKOWNIK_DEMO, datetime.now(timezone.utc)))
            start = time.perf_counter()
            try:
                session.execute(stmt, params)
                status, uwagi = sukces(), ""
            except Exception as e:
                status, uwagi = blad(), opisz_blad(e)
            ms = (time.perf_counter() - start) * 1000
            wyniki.append((operacja, nazwa, status, f"{ms:6.1f} ms",
                           uwagi))

    # status zawiera kody kolorów -> wyrównujemy ręcznie
    print(f"  {'OPERACJA':<9}{'SPÓJNOŚĆ':<10}{'WYNIK':<8}"
          f"{'CZAS':<12}UWAGI")
    print("  " + "-" * 62)
    for op, poziom, status, czas, uwagi in wyniki:
        odstep = " " * (8 - len("SUKCES" if "SUKCES" in status
                                else "BŁĄD"))
        print(f"  {op:<9}{poziom:<10}{status}{odstep}{czas:<12}{uwagi}")


DEMA = {"partycja": demo_partycja, "filtr": demo_filtr,
        "spojnosc": demo_spojnosc}

if __name__ == "__main__":
    wybrane = sys.argv[1:] or list(DEMA)
    cluster, session = polacz()
    for nazwa in wybrane:
        DEMA[nazwa](session)
    print()
    cluster.shutdown()
