import os
import firebase_admin
from firebase_admin import credentials

if not firebase_admin._apps:

    credential_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if credential_path:
        # Local development: use your service-account JSON file
        cred = credentials.Certificate(credential_path)
        firebase_admin.initialize_app(cred)

    else:
        # Google Cloud Run: use Application Default Credentials
        firebase_admin.initialize_app()