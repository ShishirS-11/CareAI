-- Grant the authenticated patient role access to the patient-owned tables.
-- Row Level Security remains enabled and limits every row to auth.uid() = user_id.

grant usage on schema public to authenticated;
grant select, insert, update, delete on table
    public.patient_profiles,
    public.consultations,
    public.consultation_messages,
    public.health_conditions,
    public.patient_allergies,
    public.current_medications,
    public.previous_prescriptions,
    public.medical_documents,
    public.health_timeline_events,
    public.summary_reports
to authenticated;

-- Keep the existing limited unauthenticated profile check working; no patient
-- health-record tables are granted to anon.
grant select on table public.patient_profiles to anon;
