from django.db import migrations

SQL = """
CREATE TRIGGER stage07_appeal_no_delete BEFORE DELETE ON moderation_complaint_appeal
FOR EACH ROW EXECUTE FUNCTION zemipro_stage06_immutable();
CREATE FUNCTION zemipro_stage07_appeal_decision_guard() RETURNS TRIGGER AS $$
BEGIN
 IF OLD.status <> 'pending' AND (NEW.status IS DISTINCT FROM OLD.status
 OR NEW.decided_by_id IS DISTINCT FROM OLD.decided_by_id
 OR NEW.decided_at IS DISTINCT FROM OLD.decided_at) THEN
  RAISE EXCEPTION 'appeal decision is immutable';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER stage07_appeal_decision_guard BEFORE UPDATE ON moderation_complaint_appeal
FOR EACH ROW EXECUTE FUNCTION zemipro_stage07_appeal_decision_guard();
"""
REVERSE = """
DROP TRIGGER stage07_appeal_decision_guard ON moderation_complaint_appeal;
DROP FUNCTION zemipro_stage07_appeal_decision_guard();
DROP TRIGGER stage07_appeal_no_delete ON moderation_complaint_appeal;
"""


class Migration(migrations.Migration):
    dependencies = [('moderation', '0005_stage07_complaints')]
    operations = [migrations.RunSQL(SQL, reverse_sql=REVERSE)]
