import io

import qrcode
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice


class Command(BaseCommand):
    help = "Create (or reset) the authenticator-app device for a staff user and print its QR code."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--reset", action="store_true", help="Delete existing authenticator devices first.")
        parser.add_argument("--png", help="Also save the QR code as a PNG image at this path.")

    def handle(self, username, reset, png=None, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist.")
        if not user.is_staff:
            raise CommandError(f"User '{username}' is not staff.")

        existing = TOTPDevice.objects.filter(user=user)
        if existing.exists() and not reset:
            raise CommandError("This user already has an authenticator device. Use --reset to replace it.")
        existing.delete()

        device = TOTPDevice.objects.create(user=user, name="Authenticator", confirmed=True)

        qr = qrcode.QRCode(border=1)
        qr.add_data(device.config_url)
        out = io.StringIO()
        qr.print_ascii(out=out, invert=True)

        self.stdout.write(out.getvalue())
        if png:
            qrcode.make(device.config_url).save(png)
            self.stdout.write(f"QR code image saved to: {png}")
        self.stdout.write("Scan the QR code with Google Authenticator / Microsoft Authenticator,")
        self.stdout.write("or enter this URL manually:")
        self.stdout.write(self.style.SUCCESS(device.config_url))
