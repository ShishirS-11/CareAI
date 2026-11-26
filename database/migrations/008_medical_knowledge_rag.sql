
-- CareAI Medical Knowledge RAG
-- Shared, curated medical reference material only.
-- Never insert patient-uploaded documents into this table.

create extension if not exists vector with schema extensions;

create table if not exists public.medical_knowledge_chunks (
    id uuid primary key default gen_random_uuid(),
    source_id text not null,
    source_title text not null,
    source_url text,
    category text,
    chunk_index integer not null,
    content text not null,
    embedding extensions.vector(768) not null,
    metadata jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, chunk_index)
);

create index if not exists medical_knowledge_source_idx
    on public.medical_knowledge_chunks(source_id);

create index if not exists medical_knowledge_category_idx
    on public.medical_knowledge_chunks(category);

create index if not exists medical_knowledge_embedding_idx
    on public.medical_knowledge_chunks
    using hnsw (embedding extensions.vector_cosine_ops);

alter table public.medical_knowledge_chunks enable row level security;

drop policy if exists "Authenticated patients can read active medical knowledge"
    on public.medical_knowledge_chunks;

create policy "Authenticated patients can read active medical knowledge"
    on public.medical_knowledge_chunks
    for select
    to authenticated
    using (is_active = true);

grant select on public.medical_knowledge_chunks to authenticated;

-- Only the server's service-role client should ingest or modify
-- shared medical knowledge. Never expose its key to Streamlit.
grant all on public.medical_knowledge_chunks to service_role;

create or replace function public.match_medical_knowledge(
    query_embedding extensions.vector(768),
    match_count integer default 5,
    filter_category text default null
)
returns table (
    id uuid,
    source_id text,
    source_title text,
    source_url text,
    category text,
    content text,
    similarity double precision
)
language sql
stable
set search_path = ''
as $$
    select
        m.id,
        m.source_id,
        m.source_title,
        m.source_url,
        m.category,
        m.content,
        1 - (m.embedding OPERATOR(extensions.<=>) query_embedding)
            as similarity
    from public.medical_knowledge_chunks m
    where m.is_active = true
      and (
          filter_category is null
          or m.category = filter_category
      )
    order by
        m.embedding OPERATOR(extensions.<=>) query_embedding
    limit greatest(1, least(match_count, 20));
$$;

grant execute on function public.match_medical_knowledge(
    extensions.vector(768), integer, text
) to authenticated;

grant execute on function public.match_medical_knowledge(
    extensions.vector(768), integer, text
) to service_role;
