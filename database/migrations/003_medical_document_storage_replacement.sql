-- CareAI private medical-document storage bucket.
-- Run after 001_initial_schema.sql and 002_authenticated_table_permissions.sql.
-- Files are private and each authenticated patient can access only their own folder.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'careai-medical-documents',
    'careai-medical-documents',
    false,
    52428800,
    array[
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/tiff',
        'application/dicom',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ]
)
on conflict (id) do update set
    public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

 drop policy if exists "Patients can read own CareAI medical files" on storage.objects;
drop policy if exists "Patients can upload own CareAI medical files" on storage.objects;
drop policy if exists "Patients can update own CareAI medical files" on storage.objects;
drop policy if exists "Patients can delete own CareAI medical files" on storage.objects;

create policy "Patients can read own CareAI medical files"
    on storage.objects for select to authenticated
    using (
        bucket_id = 'careai-medical-documents'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );

create policy "Patients can upload own CareAI medical files"
    on storage.objects for insert to authenticated
    with check (
        bucket_id = 'careai-medical-documents'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );

create policy "Patients can update own CareAI medical files"
    on storage.objects for update to authenticated
    using (
        bucket_id = 'careai-medical-documents'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    )
    with check (
        bucket_id = 'careai-medical-documents'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );

create policy "Patients can delete own CareAI medical files"
    on storage.objects for delete to authenticated
    using (
        bucket_id = 'careai-medical-documents'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );
