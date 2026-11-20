"""Wspólne elementy: połączenie z klastrem i kolorowe komunikaty."""
import logging

from cassandra import ConsistencyLevel
from cassandra.cluster import (EXEC_PROFILE_DEFAULT, Cluster,
                               ExecutionProfile)
from cassandra.policies import WhiteListRoundRobinPolicy


logging.getLogger("cassandra").setLevel(logging.ERROR)

# Z hosta widać tylko cass1 (port 9042) - on jest koordynatorem.
KOORDYNATOR = "127.0.0.1"

ZIELONY, CZERWONY, ZOLTY = "\033[92m", "\033[91m", "\033[93m"
POGRUBIONY, RESET = "\033[1m", "\033[0m"


def polacz(keyspace="movielens"):
    """Zwraca (cluster, session) z domyślną spójnością QUORUM."""
    profil = ExecutionProfile(
        load_balancing_policy=WhiteListRoundRobinPolicy([KOORDYNATOR]),
        consistency_level=ConsistencyLevel.QUORUM,
        request_timeout=20,
    )
    cluster = Cluster(
        [KOORDYNATOR],
        protocol_version=5,
        execution_profiles={EXEC_PROFILE_DEFAULT: profil},
    )
    return cluster, cluster.connect(keyspace)


def liczba(n):
    """12345 -> '12 345' (polski zapis)."""
    return f"{n:,.0f}".replace(",", " ")


def naglowek(tekst):
    print(f"\n{POGRUBIONY}=== {tekst} ==={RESET}")


def sukces(tekst="SUKCES"):
    return f"{ZIELONY}{tekst}{RESET}"


def blad(tekst="BŁĄD"):
    return f"{CZERWONY}{tekst}{RESET}"
