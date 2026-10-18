import os
import firebase_admin
from firebase_admin import credentials

FIREBASE_PROJECT_ID = "tutorain-tutor-portal"

if not firebase_admin._apps:

    credential_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if credential_path:
        # Local development: use the service-account JSON file
        cred = credentials.Certificate(credential_path)

        firebase_admin.initialize_app(
            cred,
            options={
                "projectId": FIREBASE_PROJECT_ID,
            },
        )

    else:
        # Google Cloud Run: use its service identity
        firebase_admin.initialize_app(
            options={
                "projectId": FIREBASE_PROJECT_ID,
            },
        )