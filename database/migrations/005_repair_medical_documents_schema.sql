-- Reconcile the original 001 medical_documents table with the metadata
-- columns expected by the current upload/extraction services.
-- Run after 003_medical_document_storage_replacement.sql and 004 metadata SQL.
-- Safe to re-run. Existing document_name values are preserved.

alter table public.medical_documents
    add column if not exists file_name text,
    add column if not exists content_type text,
    add column if not exists file_size bigint,
    add column if not exists notes text;

update public.medical_documents
set file_name = coalesce(nullif(file_name, ''), document_name)
where file_name is null or file_name = '';

update public.medical_documents
set content_type = coalesce(nullif(content_type, ''), 'application/octet-stream')
where content_type is null or content_type = '';

-- Legacy rows may not have a known byte size. Keep file_size nullable for those
-- rows; all new uploads populate the actual byte count.
alter table public.medical_documents
    alter column file_name set not null,
    alter column content_type set not null;

create unique index if not exists medical_documents_storage_path_unique_idx
    on public.medical_documents(storage_path);

create index if not exists medical_documents_user_created_idx
    on public.medical_documents(user_id, created_at desc);

alter table public.medical_documents enable row level security;
grant select, insert, update, delete on public.medical_documents to authenticated;

drop policy if exists "Patients view their own medical document records" on public.medical_documents;
drop policy if exists "Patients add their own medical document records" on public.medical_documents;
drop policy if exists "Patients update their own medical document records" on public.medical_documents;
drop policy if exists "Patients delete their own medical document records" on public.medical_documents;

create policy "Patients view their own medical document records"
    on public.medical_documents for select to authenticated
    using ((select auth.uid()) = user_id);
create policy "Patients add their own medical document records"
    on public.medical_documents for insert to authenticated
    with check ((select auth.uid()) = user_id);
create policy "Patients update their own medical document records"
    on public.medical_documents for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);
create policy "Patients delete their own medical document records"
    on public.medical_documents for delete to authenticated
    using ((select auth.uid()) = user_id);
