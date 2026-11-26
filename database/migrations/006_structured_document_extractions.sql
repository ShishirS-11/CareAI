-- CareAI structured document extraction. Run once in Supabase SQL Editor.
create table if not exists public.medical_document_extractions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    document_id uuid not null references public.medical_documents(id) on delete cascade,
    extraction_json jsonb not null default '{}'::jsonb,
    review_status text not null default 'pending'
        check (review_status in ('pending', 'approved', 'rejected')),
    model_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    reviewed_at timestamptz,
    constraint medical_document_extractions_json_object
        check (jsonb_typeof(extraction_json) = 'object')
);
create index if not exists idx_medical_document_extractions_user_document
    on public.medical_document_extractions(user_id, document_id, created_at desc);
alter table public.medical_document_extractions enable row level security;
drop policy if exists "Patients can view their own document extractions" on public.medical_document_extractions;
create policy "Patients can view their own document extractions"
    on public.medical_document_extractions for select to authenticated
    using (auth.uid() = user_id);
drop policy if exists "Patients can create their own document extractions" on public.medical_document_extractions;
create policy "Patients can create their own document extractions"
    on public.medical_document_extractions for insert to authenticated
    with check (auth.uid() = user_id and exists (
        select 1 from public.medical_documents d
        where d.id = document_id and d.user_id = auth.uid()
    ));
drop policy if exists "Patients can update their own document extractions" on public.medical_document_extractions;
create policy "Patients can update their own document extractions"
    on public.medical_document_extractions for update to authenticated
    using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "Patients can delete their own document extractions" on public.medical_document_extractions;
create policy "Patients can delete their own document extractions"
    on public.medical_document_extractions for delete to authenticated
    using (auth.uid() = user_id);
grant select, insert, update, delete on public.medical_document_extractions to authenticated;
