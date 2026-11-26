-- CareAI patient-only database foundation.
-- Run this file in Supabase SQL Editor for a NEW CareAI project.
-- No doctor accounts, doctor portal, appointment booking, or hospital workflows.

create extension if not exists pgcrypto;

-- Patient profile linked to Supabase Auth.
create table if not exists public.patient_profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    full_name text,
    date_of_birth date,
    sex text,
    phone text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint patient_profiles_sex_check
        check (sex is null or sex in ('female', 'male', 'intersex', 'prefer_not_to_say', 'other'))
);

-- Ongoing or completed symptom consultations.
create table if not exists public.consultations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    title text,
    status text not null default 'in_progress',
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint consultations_status_check
        check (status in ('in_progress', 'completed', 'abandoned'))
);

-- Conversation history. Agent-internal reasoning should not be stored here.
create table if not exists public.consultation_messages (
    id uuid primary key default gen_random_uuid(),
    consultation_id uuid not null references public.consultations(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    sender text not null,
    message_text text not null,
    created_at timestamptz not null default now(),
    constraint consultation_messages_sender_check
        check (sender in ('patient', 'assistant'))
);

-- Patient-reported conditions and diagnoses from their own records.
create table if not exists public.health_conditions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    condition_name text not null,
    status text not null default 'active',
    diagnosed_on date,
    notes text,
    source text not null default 'patient_reported',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint health_conditions_status_check
        check (status in ('active', 'resolved', 'historical'))
);

create table if not exists public.patient_allergies (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    allergen text not null,
    reaction text,
    severity text,
    notes text,
    source text not null default 'patient_reported',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint patient_allergies_severity_check
        check (severity is null or severity in ('mild', 'moderate', 'severe', 'unknown'))
);

-- Current medications are separate from historical prescriptions.
create table if not exists public.current_medications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    medication_name text not null,
    dosage text,
    frequency text,
    started_on date,
    ended_on date,
    prescribing_clinician text,
    notes text,
    source text not null default 'patient_reported',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint current_medications_dates_check
        check (ended_on is null or started_on is null or ended_on >= started_on)
);

-- Previous prescriptions remain historical unless the patient confirms they are current.
create table if not exists public.previous_prescriptions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    medication_name text not null,
    dosage text,
    frequency text,
    prescribed_on date,
    prescribed_for text,
    prescribing_clinician text,
    source_document_id uuid,
    notes text,
    created_at timestamptz not null default now()
);

-- Metadata for patient-uploaded reports, prescriptions, and other medical records.
-- Actual files belong in a private Supabase Storage bucket configured separately.
create table if not exists public.medical_documents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    document_name text not null,
    document_type text not null,
    storage_path text not null,
    document_date date,
    extracted_text text,
    extraction_status text not null default 'pending',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint medical_documents_extraction_status_check
        check (extraction_status in ('pending', 'completed', 'failed'))
);

-- Link a previous prescription to its source document after both records exist.
alter table public.previous_prescriptions
    drop constraint if exists previous_prescriptions_source_document_id_fkey;
alter table public.previous_prescriptions
    add constraint previous_prescriptions_source_document_id_fkey
    foreign key (source_document_id)
    references public.medical_documents(id) on delete set null;

create table if not exists public.health_timeline_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    event_date date not null default current_date,
    event_type text not null,
    title text not null,
    details text,
    source text not null default 'patient_reported',
    related_document_id uuid references public.medical_documents(id) on delete set null,
    created_at timestamptz not null default now()
);

-- Doctor-ready summaries are generated for the patient to review and download.
create table if not exists public.summary_reports (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    consultation_id uuid references public.consultations(id) on delete set null,
    report_title text not null default 'CareAI Health Summary',
    report_content jsonb not null,
    generated_at timestamptz not null default now(),
    reviewed_by_patient_at timestamptz,
    pdf_storage_path text
);

-- Indexes for common patient-scoped queries.
create index if not exists consultations_user_started_idx
    on public.consultations (user_id, started_at desc);
create index if not exists consultation_messages_consultation_created_idx
    on public.consultation_messages (consultation_id, created_at);
create index if not exists health_conditions_user_idx
    on public.health_conditions (user_id);
create index if not exists patient_allergies_user_idx
    on public.patient_allergies (user_id);
create index if not exists current_medications_user_idx
    on public.current_medications (user_id);
create index if not exists previous_prescriptions_user_date_idx
    on public.previous_prescriptions (user_id, prescribed_on desc);
create index if not exists medical_documents_user_date_idx
    on public.medical_documents (user_id, document_date desc);
create index if not exists health_timeline_user_date_idx
    on public.health_timeline_events (user_id, event_date desc);
create index if not exists summary_reports_user_generated_idx
    on public.summary_reports (user_id, generated_at desc);

-- Enable row-level security on every patient-data table.
alter table public.patient_profiles enable row level security;
alter table public.consultations enable row level security;
alter table public.consultation_messages enable row level security;
alter table public.health_conditions enable row level security;
alter table public.patient_allergies enable row level security;
alter table public.current_medications enable row level security;
alter table public.previous_prescriptions enable row level security;
alter table public.medical_documents enable row level security;
alter table public.health_timeline_events enable row level security;
alter table public.summary_reports enable row level security;

-- Patients can access only rows belonging to their authenticated account.
-- Profile policies.
drop policy if exists "Patients manage their own profile" on public.patient_profiles;
create policy "Patients manage their own profile"
    on public.patient_profiles for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- Direct user-owned tables.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'consultations',
        'health_conditions',
        'patient_allergies',
        'current_medications',
        'previous_prescriptions',
        'medical_documents',
        'health_timeline_events',
        'summary_reports'
    ] loop
        execute format('drop policy if exists %I on public.%I', 'Patients manage own ' || table_name, table_name);
        execute format(
            'create policy %I on public.%I for all using (auth.uid() = user_id) with check (auth.uid() = user_id)',
            'Patients manage own ' || table_name,
            table_name
        );
    end loop;
end $$;

-- Messages must belong to a consultation owned by the same authenticated patient.
drop policy if exists "Patients manage their own consultation messages" on public.consultation_messages;
create policy "Patients manage their own consultation messages"
    on public.consultation_messages for all
    using (
        auth.uid() = user_id
        and exists (
            select 1 from public.consultations c
            where c.id = consultation_id and c.user_id = auth.uid()
        )
    )
    with check (
        auth.uid() = user_id
        and exists (
            select 1 from public.consultations c
            where c.id = consultation_id and c.user_id = auth.uid()
        )
    );

-- Automatically create an empty patient profile when a user signs up.
create or replace function public.handle_new_careai_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.patient_profiles (user_id, full_name)
    values (new.id, coalesce(new.raw_user_meta_data ->> 'full_name', ''))
    on conflict (user_id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_careai_auth_user_created on auth.users;
create trigger on_careai_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_careai_user();

-- Keep updated_at accurate on editable records.
create or replace function public.set_careai_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'patient_profiles',
        'consultations',
        'health_conditions',
        'patient_allergies',
        'current_medications',
        'medical_documents'
    ] loop
        execute format('drop trigger if exists set_updated_at on public.%I', table_name);
        execute format(
            'create trigger set_updated_at before update on public.%I for each row execute procedure public.set_careai_updated_at()',
            table_name
        );
    end loop;
end $$;
