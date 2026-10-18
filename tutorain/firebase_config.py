import firebase_admin
from firebase_admin import credentials
import os

if not firebase_admin._apps:
    credential_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not credential_path:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set."
        )

    cred = credentials.Certificate(credential_path)

    firebase_admin.initialize_app(cred)