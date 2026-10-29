-- Должности команды управления стрима в назначении на стрим (scope_type = STREAM):
-- LEAD — лидер стрима, ITLEAD — ИТ-лидер стрима, ARCH — архитектор, PM — проектный менеджер.
-- Права: LEAD/ITLEAD — редакторы данных стрима и всех его команд; ARCH/PM — редакторы данных стрима, команды — просмотр.
ALTER TABLE org_memberships ADD COLUMN IF NOT EXISTS position TEXT;
