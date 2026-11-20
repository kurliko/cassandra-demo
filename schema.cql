-- Dane: MovieLens (GroupLens, University of Minnesota)
-- prawdziwe oceny filmów: 610 użytkowników, 9 742 filmy

-- NetworkTopologyStrategy: liczba replik osobno dla każdego DC.
CREATE KEYSPACE IF NOT EXISTS movielens
  WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
  };

-- Słownik filmów. Partycja = jeden film.
CREATE TABLE IF NOT EXISTS movielens.movies (
  movie_id int PRIMARY KEY,
  title    text,
  genres   set<text>
);

-- Zapytanie 1: "co ostatnio ocenił użytkownik X?"
--   user_id            -> klucz partycji: wszystkie oceny użytkownika razem
--   rated_at, movie_id -> klucz klastrujący: najnowsze pierwsze;
--                         movie_id, bo w jednej sekundzie bywa kilka ocen
--   title              -> powielony z movies: zamiast JOIN-a
CREATE TABLE IF NOT EXISTS movielens.ratings_by_user (
  user_id  int,
  rated_at timestamp,
  movie_id int,
  title    text,
  rating   float,
  PRIMARY KEY ((user_id), rated_at, movie_id)
) WITH CLUSTERING ORDER BY (rated_at DESC, movie_id ASC);

-- Zapytanie 2: "jak oceniano film Y?"
-- Te same oceny, ale partycja = film (denormalizacja).
CREATE TABLE IF NOT EXISTS movielens.ratings_by_movie (
  movie_id int,
  user_id  int,
  rating   float,
  rated_at timestamp,
  PRIMARY KEY ((movie_id), user_id)
);
