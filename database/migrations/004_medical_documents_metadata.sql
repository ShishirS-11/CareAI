-- CareAI medical document metadata table.
-- Run after migrations 001, 002 and 003.

create table if not exists public.medical_documents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    file_name text not null,
    storage_path text not null unique,
    content_type text not null,
    file_size bigint not null check (file_size > 0 and file_size <= 52428800),
    document_type text not null check (
        document_type in (
            'Lab report', 'Prescription', 'X-ray', 'MRI', 'CT scan',
            'Ultrasound', 'Discharge summary', 'Medical history',
            'Other medical document'
        )
    ),
    document_date date,
    notes text,
    created_at timestamptz not null default now()
);

create index if not exists medical_documents_user_created_idx
    on public.medical_documents (user_id, created_at desc);

alter table public.medical_documents enable row level security;

grant select, insert, update, delete on public.medical_documents to authenticated;

 drop policy if exists "Patients view their own medical document records" on public.medical_documents;
create policy "Patients view their own medical document records"
    on public.medical_documents for select to authenticated
    using ((select auth.uid()) = user_id);

drop policy if exists "Patients add their own medical document records" on public.medical_documents;
create policy "Patients add their own medical document records"
    on public.medical_documents for insert to authenticated
    with check ((select auth.uid()) = user_id);

drop policy if exists "Patients update their own medical document records" on public.medical_documents;
create policy "Patients update their own medical document records"
    on public.medical_documents for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

drop policy if exists "Patients delete their own medical document records" on public.medical_documents;
create policy "Patients delete their own medical document records"
    on public.medical_documents for delete to authenticated
    using ((select auth.uid()) = user_id);
