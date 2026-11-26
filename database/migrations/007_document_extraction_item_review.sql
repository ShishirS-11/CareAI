-- CareAI: per-item patient review for structured document findings.
-- Run once in Supabase SQL Editor after migration 006.
create table if not exists public.medical_document_extraction_items (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    document_id uuid not null references public.medical_documents(id) on delete cascade,
    extraction_id uuid not null references public.medical_document_extractions(id) on delete cascade,
    item_type text not null check (item_type in ('investigation', 'medication')),
    item_index integer not null check (item_index >= 0),
    item_json jsonb not null default '{}'::jsonb
        check (jsonb_typeof(item_json) = 'object'),
    review_status text not null default 'pending'
        check (review_status in ('pending', 'approved', 'rejected')),
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint medical_document_extraction_items_unique
        unique (extraction_id, item_type, item_index),
    constraint medical_document_extraction_items_owner_check
        check (user_id is not null)
);

create index if not exists idx_doc_extraction_items_user_status
    on public.medical_document_extraction_items(user_id, review_status, created_at desc);
create index if not exists idx_doc_extraction_items_document
    on public.medical_document_extraction_items(document_id, extraction_id);

alter table public.medical_document_extraction_items enable row level security;

drop policy if exists "Patients can view their own extraction items"
    on public.medical_document_extraction_items;
create policy "Patients can view their own extraction items"
    on public.medical_document_extraction_items for select to authenticated
    using (auth.uid() = user_id);

drop policy if exists "Patients can create their own extraction items"
    on public.medical_document_extraction_items;
create policy "Patients can create their own extraction items"
    on public.medical_document_extraction_items for insert to authenticated
    with check (
        auth.uid() = user_id
        and exists (
            select 1 from public.medical_documents d
            where d.id = document_id and d.user_id = auth.uid()
        )
        and exists (
            select 1 from public.medical_document_extractions e
            where e.id = extraction_id and e.user_id = auth.uid()
              and e.document_id = document_id
        )
    );

drop policy if exists "Patients can update their own extraction items"
    on public.medical_document_extraction_items;
create policy "Patients can update their own extraction items"
    on public.medical_document_extraction_items for update to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

drop policy if exists "Patients can delete their own extraction items"
    on public.medical_document_extraction_items;
create policy "Patients can delete their own extraction items"
    on public.medical_document_extraction_items for delete to authenticated
    using (auth.uid() = user_id);

grant select, insert, update, delete
    on public.medical_document_extraction_items to authenticated;
