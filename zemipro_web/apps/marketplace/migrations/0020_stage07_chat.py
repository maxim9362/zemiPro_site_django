"""Stage 07.1: isolated, server-authorized conversations, messages and images."""
import uuid

from django.db import migrations, models
import django.db.models.deletion


GUARD = """
CREATE OR REPLACE FUNCTION zemipro_stage07_message_original_guard() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.conversation_id IS DISTINCT FROM OLD.conversation_id
        OR NEW.sender_id IS DISTINCT FROM OLD.sender_id
        OR NEW.body IS DISTINCT FROM OLD.body
        OR NEW.client_nonce IS DISTINCT FROM OLD.client_nonce
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.delivered_at IS DISTINCT FROM OLD.delivered_at
    THEN
        RAISE EXCEPTION 'original chat messages are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER stage07_message_original_guard BEFORE UPDATE
    ON marketplace_message FOR EACH ROW
    EXECUTE FUNCTION zemipro_stage07_message_original_guard();
"""
REVERSE = """
DROP TRIGGER IF EXISTS stage07_message_original_guard ON marketplace_message;
DROP FUNCTION IF EXISTS zemipro_stage07_message_original_guard();
"""


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0019_stage06_work_events')]

    operations = [
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('response', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='conversation', to='marketplace.response',
                )),
            ],
            options={
                'db_table': 'marketplace_conversation',
                'ordering': ['-created_at', '-pk'],
            },
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('body', models.TextField()),
                ('client_nonce', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('delivered_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('conversation', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='messages', to='marketplace.conversation',
                )),
                ('sender', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sent_chat_messages', to='accounts.user',
                )),
            ],
            options={
                'db_table': 'marketplace_message',
                'ordering': ['created_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='message',
            constraint=models.UniqueConstraint(
                fields=('conversation', 'sender', 'client_nonce'),
                name='chat_message_nonce_unique',
            ),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(
                fields=['conversation', 'pk'], name='chat_message_page_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(
                fields=['conversation', 'sender', '-created_at'],
                name='chat_msg_actor_time_idx',
            ),
        ),
        migrations.CreateModel(
            name='MessageAttachment',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('file_key', models.CharField(
                    editable=False, max_length=120, unique=True,
                )),
                ('content_sha256', models.CharField(editable=False, max_length=64)),
                ('byte_size', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='attachments', to='marketplace.message',
                )),
            ],
            options={
                'db_table': 'marketplace_message_attachment',
                'ordering': ['pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='messageattachment',
            constraint=models.UniqueConstraint(
                fields=('message', 'content_sha256'),
                name='chat_attachment_digest_unique',
            ),
        ),
        migrations.RunSQL(GUARD, reverse_sql=REVERSE),
    ]
