import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials


# Firebase project used by both local and hosted environments
FIREBASE_PROJECT_ID = "tutorain-tutor-portal"

# Your local Firebase service-account file
LOCAL_CREDENTIALS_PATH = Path(
    r"F:\Djnago_tutorain\TutorainPrivate\firebase-service-account.json"
)


def initialize_firebase():
    # Reuse Firebase if it has already been initialized
    if firebase_admin._apps:
        return firebase_admin.get_app()

    # Option 1: Use credentials supplied through an environment variable
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if credentials_path and Path(credentials_path).is_file():
        credential = credentials.Certificate(credentials_path)

        return firebase_admin.initialize_app(
            credential,
            {"projectId": FIREBASE_PROJECT_ID},
        )

    # Option 2: Automatically use your local credentials on Windows
    if LOCAL_CREDENTIALS_PATH.is_file():
        credential = credentials.Certificate(
            str(LOCAL_CREDENTIALS_PATH)
        )

        return firebase_admin.initialize_app(
            credential,
            {"projectId": FIREBASE_PROJECT_ID},
        )

    # Option 3: On Cloud Run, use its assigned service account
    return firebase_admin.initialize_app(
        options={"projectId": FIREBASE_PROJECT_ID}
    )


app = initialize_firebase()