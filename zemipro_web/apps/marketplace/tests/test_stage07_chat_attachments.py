"""Stage 07: private media access, EXIF stripping and PostgreSQL immutability."""
from io import BytesIO
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, PngImagePlugin

from apps.marketplace.chat_services import (
    attach_message_image, open_conversation, send_message,
)
from apps.marketplace.models import MessageAttachment, Response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user,
)


def synthetic_image():
    stream = BytesIO()
    image = Image.new('RGB', (32, 24), (50, 100, 220))
    exif = PngImagePlugin.PngInfo()
    exif.add_text('Comment', 'SYNTHETIC_EXIF_MARKER')
    image.save(stream, format='PNG', pnginfo=exif)
    return SimpleUploadedFile(
        'synthetic-photo.png', stream.getvalue(),
        content_type='image/png',
    )


class Stage07PrivateAttachmentTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        setting = override_settings(ZEMIPRO_PRIVATE_MEDIA_ROOT=directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        city = make_city()
        category = make_category()
        self.owner = make_user('stage07-attachment-owner')
        self.worker = make_user('stage07-attachment-worker')
        self.stranger = make_user('stage07-attachment-stranger')
        order = make_order(client=self.owner, category=category, city=city)
        offer = Response.objects.create(
            order=order, worker=self.worker, status=Response.Status.SENT,
        )
        self.conversation, _ = open_conversation(
            response_id=offer.pk, actor=self.owner,
        )
        self.message, _ = send_message(
            conversation_id=self.conversation.pk, actor=self.worker,
            body='Synthetic attachment holder', client_nonce=uuid4(),
        )

    def test_attachment_is_private_sanitized_and_immutable(self):
        image, created = attach_message_image(
            message_id=self.message.pk, actor=self.worker,
            upload=synthetic_image(),
        )
        self.assertTrue(created)
        same, created = attach_message_image(
            message_id=self.message.pk, actor=self.worker,
            upload=synthetic_image(),
        )
        self.assertFalse(created)
        self.assertEqual(same.pk, image.pk)
        self.assertEqual(MessageAttachment.objects.count(), 1)
        url = reverse('marketplace:chat_attachment', args=[image.pk])
        self.client.force_login(self.owner)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertIn('no-store', response['Cache-Control'])
        payload = b''.join(response.streaming_content)
        self.assertTrue(payload.startswith(b'\xff\xd8'))
        self.assertNotIn(b'SYNTHETIC_EXIF_MARKER', payload)
        self.assertNotIn(b'synthetic-photo.png', response.serialize_headers())
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.worker)
        self.worker.is_blocked = True
        self.worker.save(update_fields=['is_blocked'])
        self.assertEqual(self.client.get(url).status_code, 404)
        with self.assertRaises(DatabaseError), transaction.atomic():
            MessageAttachment.objects.filter(pk=image.pk).update(
                file_key='chat-attachments/untrusted.jpg',
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            MessageAttachment.objects.filter(pk=image.pk).delete()
        self.assertEqual(MessageAttachment.objects.count(), 1)

    def test_non_participant_cannot_upload_or_download(self):
        with self.assertRaises(PermissionDenied):
            attach_message_image(
                message_id=self.message.pk, actor=self.stranger,
                upload=synthetic_image(),
            )
        self.assertEqual(MessageAttachment.objects.count(), 0)
        self.client.force_login(self.stranger)
        result = self.client.post(reverse(
            'marketplace:chat_image_upload', args=[self.message.pk],
        ), {'image': synthetic_image()})
        self.assertEqual(result.status_code, 403)
