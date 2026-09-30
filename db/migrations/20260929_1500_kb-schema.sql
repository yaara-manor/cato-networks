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

create table if not exists accounts (
    customer_id text primary key,
    company text not null,
    tier text not null,
    email_domain text not null unique,
    registered_admin_contact text not null unique,
    country text null
);

create table if not exists tickets (
    ticket_id text primary key,
    created_at timestamptz not null,
    channel text not null,
    customer_id text not null references accounts(customer_id),
    customer_name text not null,
    requester_email text not null,
    company text not null,
    tier text not null,
    site_id text null,
    product_area text not null,
    priority text not null,
    subject text not null,
    body text not null,
    status text not null
);

create index if not exists tickets_customer_created_idx on tickets (customer_id, created_at);
create index if not exists tickets_customer_site_idx on tickets (customer_id, site_id);
