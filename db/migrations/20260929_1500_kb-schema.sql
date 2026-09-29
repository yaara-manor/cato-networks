create extension if not exists vector;

create table if not exists snapshots (
    id uuid primary key,
    crawled_at timestamptz,
    embedding_model text,
    embedding_dimensions int,
    reranker_model text
);

create table if not exists kb_articles (
    slug text primary key,
    snapshot_id uuid references snapshots,
    title text,
    public_url text,
    site_updated_at timestamptz null,
    content_hash text,
    file_path text
);

create table if not exists passages (
    id uuid primary key,
    article_slug text references kb_articles,
    heading text,
    heading_anchor text,
    position int,
    body text,
    content_hash text,
    search_vector tsvector generated always as (to_tsvector('simple', body)) stored,
    embedding vector(384),
    unique (article_slug, position)
);

create index if not exists passages_search_vector on passages using gin (search_vector);

create table if not exists policies (
    id text primary key,
    title text,
    content_hash text,
    file_path text,
    body text
);
