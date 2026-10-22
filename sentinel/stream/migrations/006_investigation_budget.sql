ALTER TABLE sentinel.investigations
ADD COLUMN deadline_seconds INTEGER NOT NULL DEFAULT 45
CHECK (deadline_seconds BETWEEN 30 AND 300);
