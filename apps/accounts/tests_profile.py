"""Profile settings page: rendering, styling and updates."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ProfileSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="prof", email="prof@example.com",
            password="s3cret-pass", first_name="Pat",
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("accounts:profile")

    def test_page_renders_sections_and_styled_inputs(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile settings")
        self.assertContains(response, "Profile photo")
        self.assertContains(response, "Personal information")
        self.assertContains(response, "au-settings-head")
        self.assertContains(response, "Change password")
        # Inputs are styled (ProfileForm uses StyledFieldsMixin)
        self.assertContains(response, 'class="form-control"')

    def test_help_texts_are_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Used to sign in")

    def test_saving_updates_the_profile(self):
        response = self.client.post(self.url, {
            "first_name": "Patricia",
            "last_name": "Doe",
            "email": "patricia@example.com",
            "phone": "+1 (555) 010-2030",
        }, follow=True)
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Patricia")
        self.assertEqual(self.user.email, "patricia@example.com")
        self.assertContains(response, "Profile updated")

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(
            username="taken", email="taken@example.com", password="x-passw0rd"
        )
        response = self.client.post(self.url, {
            "first_name": "Pat",
            "email": "taken@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This email is already in use.")

    def test_profile_page_loads_the_crop_toolkit(self):
        response = self.client.get(self.url)
        self.assertContains(response, "vendor/css/cropper.min.css")
        self.assertContains(response, "vendor/js/cropper.min.js")
        self.assertContains(response, "js/avatar-crop.js")
        self.assertContains(response, 'id="au-crop"')
        self.assertContains(response, "Crop your photo")

    def test_file_input_carries_crop_options(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-crop="1"')
        self.assertContains(response, 'data-crop-ratio="1"')
        self.assertContains(response, 'data-crop-size="512"')

    def test_csp_allows_blob_previews(self):
        # The crop modal previews picked files via blob: URLs.
        response = self.client.get(self.url)
        csp = response["Content-Security-Policy"]
        self.assertIn("img-src 'self' data: blob:", csp)
