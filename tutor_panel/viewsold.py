import json
from datetime import datetime, timezone

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from firebase_admin import auth, get_app, firestore
from tutorain import firebase_config

from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

import secrets
import hashlib
import time

from django.utils.crypto import constant_time_compare



@ensure_csrf_cookie
def login_page(request):
    if request.session.get("firebase_uid"):
        return redirect("tutor_panel:dashboard")

    return render(request, "tutor_panel/login.html")

@require_POST
@csrf_protect
def firebase_login(request):
    stage = "starting"

    try:
        # 1. Read the request
        stage = "reading request"
        data = json.loads(request.body)
        id_token = data.get("idToken")

        if not id_token:
            return JsonResponse({
                "success": False,
                "error": "Missing login token."
            }, status=400)

        # 2. Verify Firebase Authentication
        stage = "verifying Firebase token"

        decoded_token = auth.verify_id_token(
            id_token,
            app=get_app()
        )

        uid = decoded_token["uid"]
        email = (decoded_token.get("email") or "").strip().lower()

        if not email:
            return JsonResponse({
                "success": False,
                "error": "Email address not found."
            }, status=401)

        # 3. Check admin BEFORE checking Firestore tutor documents
        admin_emails = getattr(settings, "ADMIN_EMAILS", [])

        if isinstance(admin_emails, str):
            admin_emails = [admin_emails]

        admin_emails = [
            address.strip().lower()
            for address in admin_emails
            if address and address.strip()
        ]

        if email in admin_emails:
            request.session.flush()

            request.session["firebase_uid"] = uid
            request.session["firebase_email"] = email
            request.session["user_role"] = "admin"

            return JsonResponse({
                "success": True,
                "redirect_url": "/tutor_panel/admin/"
            })


        # 4. Check the tutor in Firestore
        # 4. Connect to Firestore
        stage = "connecting to Firestore"
        db = firestore.client(app=get_app())

        # 5. Check whether this is a registered student
        stage = "checking student account"

        student_query = (
            db.collection("students")
            .where("firebase_uid", "==", uid)
            .limit(1)
            .stream()
        )

        student_doc = next(student_query, None)

        if student_doc is not None:
            student_data = student_doc.to_dict() or {}

            student_status = (
                student_data.get("status") or ""
            ).strip().lower()

            if student_status != "active":
                return JsonResponse({
                    "success": False,
                    "error": "Your student account is inactive. Please contact the administrator."
                }, status=403)

            # Create a new student session
            request.session.flush()

            request.session["firebase_uid"] = uid
            request.session["firebase_email"] = email
            request.session["user_role"] = "student"
            request.session["student_doc_id"] = student_doc.id

            return JsonResponse({
                "success": True,
                "redirect_url": "/firebase-student-dashboard/"
            })

        # 6. If no student was found, continue with the existing tutor check
        stage = "reading tutor document"
        tutor_ref = db.collection("tutors").document(email)
        tutor_doc = tutor_ref.get()

        stage = "reading tutor document"
        tutor_ref = db.collection("tutors").document(email)
        tutor_doc = tutor_ref.get()

        if not tutor_doc.exists:
            # Parent accounts are matched to guardian_email on student records.
            parent_matches = list(
                db.collection("students").where("guardian_email", "==", email).stream()
            )
            active_matches = [
                doc for doc in parent_matches
                if (doc.to_dict() or {}).get("status", "Active").strip().lower() == "active"
            ]
            if active_matches:
                request.session.flush()
                request.session["firebase_uid"] = uid
                request.session["firebase_email"] = email
                request.session["user_role"] = "parent"
                return JsonResponse({
                    "success": True,
                    "redirect_url": "/tutor_panel/parent/"
                })
            return JsonResponse({
                "success": False,
                "error": (
                    "Your tutor or parent account was not found. "
                    "Ask Tutorain administration to add your email to the student record."
                )
            }, status=403)

        tutor_data = tutor_doc.to_dict() or {}

        tutor_status = (
            tutor_data.get("status") or ""
        ).strip().lower()

        # 5. Check tutor approval
        if tutor_status != "approved":
            return JsonResponse({
                "success": False,
                "error": (
                    "Your account is pending approval. "
                    "Please contact the administrator."
                )
            }, status=403)

        # 6. Create the tutor session
        request.session.flush()

        request.session["firebase_uid"] = uid
        request.session["firebase_email"] = email
        request.session["user_role"] = "tutor"

        return JsonResponse({
            "success": True,
            "redirect_url": "/tutor_panel/dashboard/"
        })

    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid request data."
        }, status=400)

    except Exception as e:
        print(
            f"FIREBASE LOGIN ERROR at stage '{stage}': "
            f"{type(e).__name__}: {e}",
            flush=True
        )

        return JsonResponse({
            "success": False,
            "error": (
                "Login failed. Please try again "
                "or contact the administrator."
            )
        }, status=401)

def dashboard(request):
    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")

    email = request.session.get("firebase_email", "").lower()

    # Only tutors can access this dashboard
    if request.session.get("user_role") != "tutor":
        return redirect("tutor_panel:admin_dashboard")

    try:
        db = firestore.client(app=get_app())
        tutor_ref = db.collection("tutors").document(email)
        tutor_doc = tutor_ref.get()

        if not tutor_doc.exists:
            request.session.flush()
            return redirect("tutor_panel:login")

        tutor_data = tutor_doc.to_dict() or {}

        if (tutor_data.get("status") or "").strip().lower() != "approved":
            request.session.flush()
            return redirect("tutor_panel:login")

    except Exception as e:
        print("DASHBOARD ERROR:", repr(e), flush=True)
        return redirect("tutor_panel:login")

    return render(
        request,
        "tutor_panel/dashboard.html",
        {
            "tutor_email": email,
        }
    )



def admin_dashboard(request):
    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")

    email = request.session.get("firebase_email", "").strip().lower()

    admin_emails = getattr(settings, "ADMIN_EMAILS", [])

    if isinstance(admin_emails, str):
        admin_emails = [admin_emails]

    admin_emails = [
        address.strip().lower()
        for address in admin_emails
        if address and address.strip()
    ]

    if (
        request.session.get("user_role") != "admin"
        or email not in admin_emails
    ):
        return redirect("tutor_panel:login")

    return render(
        request,
        "tutor_panel/admin_dashboard.html",
        {
            "admin_email": email,
        }
    )


def logout_page(request):
    request.session.flush()
    return redirect("tutor_panel:login")

def manage_tutors(request):
    # 1. Check administrator login
    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")

    user_email = (
        request.session.get("firebase_email") or ""
    ).strip().lower()

    # Get administrator email addresses safely
    admin_emails = getattr(settings, "ADMIN_EMAILS", [])

    if isinstance(admin_emails, str):
        admin_emails = [admin_emails]

    admin_emails = [
        email.strip().lower()
        for email in admin_emails
        if email and email.strip()
    ]

    if (
        request.session.get("user_role") != "admin"
        or user_email not in admin_emails
    ):
        return redirect("tutor_panel:admin_dashboard")

    # 2. Connect to Firestore
    db = firestore.client(app=get_app())

    # 3. Handle POST requests
    if request.method == "POST":

        action = request.POST.get("action", "").strip().lower()
        tutor_email = (
            request.POST.get("tutor_email") or ""
        ).strip().lower()

        # --------------------------------------------------
        # A. APPROVE, REJECT, OR SET TUTOR TO PENDING
        # --------------------------------------------------
        if action in ["approve", "reject", "pending"]:

            if not tutor_email:
                messages.error(request, "Tutor email is missing.")
                return redirect("tutor_panel:manage_tutors")

            tutor_ref = db.collection("tutors").document(tutor_email)
            tutor_document = tutor_ref.get()

            if not tutor_document.exists:
                messages.error(request, "Tutor not found.")
                return redirect("tutor_panel:manage_tutors")

            tutor_data = tutor_document.to_dict() or {}

            # Determine the new status.
            # Password setup is not required for administrator approval.
            if action == "approve":
                new_status = "Approved"

            elif action == "reject":
                new_status = "Rejected"

            else:
                new_status = "Pending"

            # Update tutor status in Firestore
            try:
                tutor_ref.update({
                    "status": new_status
                })

            except Exception as e:
                print(
                    "TUTOR STATUS UPDATE ERROR:",
                    repr(e),
                    flush=True,
                )

                messages.error(
                    request,
                    "Could not update the tutor status. "
                    "Please try again."
                )

                return redirect("tutor_panel:manage_tutors")

            # Send approval email when approved
            if new_status == "Approved":

                tutor_name = tutor_data.get("name", "Tutor")

                try:
                    email_sent = send_mail(
                        subject=(
                            "Congratulations! Your Tutorain Account Is Approved"
                        ),
                        message = (
                            f"Hello {tutor_name},\n\n"
                            "Congratulations!\n\n"
                            "Your Tutorain tutor account has been approved "
                            "by the administrator.\n\n"
                            "You can now log in to the Tutorain Tutor Portal "
                            "using your registered email address and password.\n\n"
                            "Login to the Tutor Portal:\n"
                            "https://www.tutorain.com/tutor_panel/\n\n"
                            "If you have not set your password yet, please "
                            "complete the password setup process first.\n\n"
                            "We look forward to working with you.\n\n"
                            "Regards,\n"
                            "Tutorain Team"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[tutor_email],
                        fail_silently=False,
                    )

                    if email_sent == 1:
                        messages.success(
                            request,
                            f"{tutor_name} has been approved, "
                            "and the approval email was sent successfully."
                        )

                    else:
                        messages.warning(
                            request,
                            f"{tutor_name} has been approved, "
                            "but the email could not be confirmed as sent."
                        )

                except Exception as e:
                    print(
                        "TUTOR APPROVAL EMAIL ERROR:",
                        repr(e),
                        flush=True,
                    )

                    messages.warning(
                        request,
                        f"{tutor_name} has been approved, but the approval "
                        "email could not be sent."
                    )

            else:
                messages.success(
                    request,
                    f"Tutor {tutor_email} status changed to {new_status}."
                )

            return redirect("tutor_panel:manage_tutors")

        # --------------------------------------------------
        # B. REGISTER A NEW TUTOR
        # --------------------------------------------------
        elif action == "register":

            name = (request.POST.get("name") or "").strip()
            email = (
                request.POST.get("email") or ""
            ).strip().lower()
            phone = (request.POST.get("phone") or "").strip()
            subject = (request.POST.get("subject") or "").strip()

            # Validate required fields
            if not all([name, email, phone, subject]):
                messages.error(
                    request,
                    "Please fill in all required fields."
                )
                return redirect("tutor_panel:manage_tutors")

            # Basic email validation
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError

            try:
                validate_email(email)
            except ValidationError:
                messages.error(
                    request,
                    "Please enter a valid email address."
                )
                return redirect("tutor_panel:manage_tutors")

            tutor_ref = db.collection("tutors").document(email)

            # Prevent duplicate Firestore records
            if tutor_ref.get().exists:
                messages.error(
                    request,
                    "A tutor with this email already exists in Firestore."
                )
                return redirect("tutor_panel:manage_tutors")

            new_user = None
            firestore_saved = False
            stage = "starting"

            try:
                # Step 1: Create Firebase Authentication account
                stage = "creating Firebase Authentication user"

                new_user = auth.create_user(
                    email=email,
                    app=get_app(),
                )

                # Step 2: Generate password-setting link
                stage = "generating password-setting link"

                password_link = auth.generate_password_reset_link(
                    email,
                    app=get_app(),
                )

                # Step 3: Save tutor details in Firestore
                stage = "saving tutor details to Firestore"

                tutor_ref.set({
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "subject": subject,
                    "status": "Pending",
                    "password_setup_completed": False,
                    "created_at": datetime.now(timezone.utc),
                })

                firestore_saved = True

                # Step 4: Send invitation email
                stage = "sending invitation email"

                email_sent = send_mail(
                    subject="Welcome to Tutorain - Set Your Password",
                    message=(
                        f"Hello {name},\n\n"
                        "Your Tutorain tutor account has been created.\n\n"
                        "Please use the link below to set your password:\n\n"
                        f"{password_link}\n\n"
                        "Your account is currently pending administrator approval.\n\n"
                        "Regards,\n"
                        "Tutorain Team"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )

                if email_sent != 1:
                    raise RuntimeError(
                        "The invitation email was not sent."
                    )

                messages.success(
                    request,
                    f"Tutor {name} was registered successfully. "
                    "A password-setting invitation has been emailed to them."
                )

            except Exception as e:
                print(
                    f"TUTOR REGISTRATION ERROR at stage '{stage}': "
                    f"{type(e).__name__}: {e}",
                    flush=True,
                )

                # Clean up Firestore record if saved
                if firestore_saved:
                    try:
                        tutor_ref.delete()

                    except Exception as cleanup_error:
                        print(
                            "FIRESTORE CLEANUP ERROR:",
                            repr(cleanup_error),
                            flush=True,
                        )

                # Clean up Firebase account created by this attempt
                if new_user is not None:
                    try:
                        auth.delete_user(
                            new_user.uid,
                            app=get_app(),
                        )

                    except Exception as cleanup_error:
                        print(
                            "FIREBASE CLEANUP ERROR:",
                            repr(cleanup_error),
                            flush=True,
                        )

                messages.error(
                    request,
                    "Tutor registration failed. Please check the Cloud Run "
                    "logs for the exact error."
                )

            return redirect("tutor_panel:manage_tutors")

        else:
            messages.error(
                request,
                "Invalid action. Please try again."
            )
            return redirect("tutor_panel:manage_tutors")

    # --------------------------------------------------
    # C. DISPLAY EXISTING TUTORS
    # --------------------------------------------------
    tutors = []

    try:
        for document in db.collection("tutors").stream():
            tutor = document.to_dict() or {}

            # Include the document ID as the email fallback
            tutor.setdefault("email", document.id)

            tutors.append(tutor)

        tutors.sort(
            key=lambda tutor: (
                tutor.get("name") or ""
            ).lower()
        )

    except Exception as e:
        print(
            "TUTOR LIST ERROR:",
            repr(e),
            flush=True,
        )

        messages.error(
            request,
            "Could not load the tutor list. Please try again."
        )

    # Render tutor management page
    return render(
        request,
        "tutor_panel/manage_tutors.html",
        {"tutors": tutors},
    )

        

def set_password_page(request):
    return render(request, "tutor_panel/set_password.html")

@require_POST
@csrf_protect
def password_setup_complete(request):
    try:
        # Read the Firebase ID token sent by the password setup page.
        data = json.loads(request.body)
        id_token = data.get("idToken")

        if not id_token:
            return JsonResponse(
                {"success": False, "error": "Authentication token is missing."},
                status=400
            )

        # Verify the token with Firebase Admin SDK.
        decoded_token = auth.verify_id_token(
            id_token,
            app=get_app()
        )

        email = decoded_token.get("email", "").strip().lower()

        if not email or not decoded_token.get("email_verified", False):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Please verify your email before continuing."
                },
                status=403
            )

        # Find the tutor's existing Firestore document.
        db = firestore.client(app=get_app())

        tutor_ref = db.collection("tutors").document(email)
        tutor_doc = tutor_ref.get()

        if not tutor_doc.exists:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Tutor account was not found."
                },
                status=404
            )

        # Record successful password setup.
        tutor_ref.update({
            "password_setup_completed": True,
            "password_setup_completed_at": datetime.now(timezone.utc)
        })

        return JsonResponse({
            "success": True,
            "message": "Password setup completed successfully."
        })

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid request data."},
            status=400
        )

    except Exception:
        return JsonResponse(
            {
                "success": False,
                "error": "Could not verify password setup. Please try again."
            },
            status=500
        )


@require_POST
@csrf_protect
def notify_admin(request):
    try:
        # The tutor must already have signed in successfully with Firebase.
        data = json.loads(request.body or "{}")
        id_token = data.get("idToken")

        if not id_token:
            return JsonResponse({
                "success": False,
                "error": "Please sign in again before sending a notification."
            }, status=401)

        # Verify the Firebase token; never trust an email supplied by the browser.
        decoded_token = auth.verify_id_token(id_token, app=get_app())

        email = (decoded_token.get("email") or "").strip().lower()

        if not email:
            return JsonResponse({
                "success": False,
                "error": "Could not identify your account."
            }, status=400)

        db = firestore.client(app=get_app())
        tutor_ref = db.collection("tutors").document(email)
        tutor_doc = tutor_ref.get()

        if not tutor_doc.exists:
            return JsonResponse({
                "success": False,
                "error": "Tutor account not found."
            }, status=404)

        tutor_data = tutor_doc.to_dict() or {}

        if (tutor_data.get("status") or "").strip().lower() != "pending":
            return JsonResponse({
                "success": False,
                "error": "This notification is only available for pending accounts."
            }, status=400)

        admin_emails = getattr(settings, "ADMIN_EMAILS", [])

        if isinstance(admin_emails, str):
            admin_emails = [admin_emails]

        admin_emails = [address for address in admin_emails if address]

        if not admin_emails:
            return JsonResponse({
                "success": False,
                "error": "Administrator email is not configured."
            }, status=500)

        tutor_name = tutor_data.get("name", "Tutor")

        send_mail(
            subject=f"Tutorain: {tutor_name} is waiting for approval",
            message=(
                "A tutor is waiting for account approval.\n\n"
                f"Name: {tutor_name}\n"
                f"Email: {email}\n"
                f"Status: {tutor_data.get('status', 'Pending')}\n\n"
                "Please sign in to the Tutorain administrator portal "
                "to review the account."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            fail_silently=False,
        )

        return JsonResponse({
            "success": True,
            "message": "Administrator notified successfully."
        })

    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    except Exception:
        return JsonResponse({
            "success": False,
            "error": "Unable to send notification. Please try again later."
        }, status=500)

# ------------------------------------------------------------
# STUDENT MANAGEMENT
# ------------------------------------------------------------
def _is_tutorain_admin(request):
    if not request.session.get("firebase_uid") or request.session.get("user_role") != "admin":
        return False
    email = (request.session.get("firebase_email") or "").strip().lower()
    admin_emails = getattr(settings, "ADMIN_EMAILS", [])
    if isinstance(admin_emails, str):
        admin_emails = [admin_emails]
    admin_emails = [item.strip().lower() for item in admin_emails if item and item.strip()]
    return email in admin_emails



def manage_students(request):
    """Admin-only student registration, Firebase login creation and editing."""
    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")
    if not _is_tutorain_admin(request):
        return redirect("tutor_panel:admin_dashboard")

    db = firestore.client(app=get_app())
    students_ref = db.collection("students")
    firebase_app = get_app()

    if request.method == "POST":
        action = (request.POST.get("action") or "create").strip().lower()
        student_id = (request.POST.get("student_id") or "").strip()

        if action in {"create", "update"}:
            name = (request.POST.get("name") or "").strip()
            student_class = (request.POST.get("student_class") or "").strip()
            subjects = (request.POST.get("subjects") or "").strip()
            guardian_name = (request.POST.get("guardian_name") or "").strip()
            guardian_phone = (request.POST.get("guardian_phone") or "").strip()
            guardian_email = (request.POST.get("guardian_email") or "").strip().lower()
            tutor_email = (request.POST.get("tutor_email") or "").strip().lower()
            status = (request.POST.get("status") or "Active").strip().title()
            student_email = (request.POST.get("student_email") or "").strip().lower()
            student_password = request.POST.get("student_password") or ""

            if not all([name, student_class, guardian_name, guardian_phone, guardian_email, tutor_email]):
                messages.error(request, "Please complete all required student fields.")
                return redirect("tutor_panel:manage_students")

            if status not in {"Active", "Inactive"}:
                status = "Active"

            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError
            try:
                validate_email(guardian_email)
                validate_email(student_email)
            except ValidationError:
                messages.error(request, "Please enter valid parent and student login email addresses.")
                return redirect("tutor_panel:manage_students")

            tutor_doc = db.collection("tutors").document(tutor_email).get()
            tutor_data = tutor_doc.to_dict() or {} if tutor_doc.exists else {}
            if not tutor_doc.exists or (tutor_data.get("status") or "").strip().lower() != "approved":
                messages.error(request, "Please select an approved tutor.")
                return redirect("tutor_panel:manage_students")

            record = {
                "name": name,
                "student_class": student_class,
                "subjects": subjects,
                "guardian_name": guardian_name,
                "guardian_phone": guardian_phone,
                "guardian_email": guardian_email,
                "tutor_email": tutor_email,
                "status": status,
                "updated_at": datetime.now(timezone.utc),
            }

            if action == "create":
                if not student_email or not student_password:
                    messages.error(request, "Student login email and password are required.")
                    return redirect("tutor_panel:manage_students")
                if len(student_password) < 8:
                    messages.error(request, "The student password must contain at least 8 characters.")
                    return redirect("tutor_panel:manage_students")

                try:
                    firebase_user = auth.create_user(
                        email=student_email,
                        password=student_password,
                        display_name=name,
                        app=firebase_app,
                    )
                except auth.EmailAlreadyExistsError:
                    messages.error(request, "This email already has a Firebase account. Please use a different student login email.")
                    return redirect("tutor_panel:manage_students")
                except Exception as exc:
                    print("STUDENT FIREBASE CREATE ERROR:", repr(exc), flush=True)
                    messages.error(request, "Firebase could not create the student account. Please check the configuration and try again.")
                    return redirect("tutor_panel:manage_students")

                new_ref = students_ref.document()
                record.update({
                    "student_id": new_ref.id,
                    "student_email": student_email,
                    "firebase_email": student_email,
                    "firebase_uid": firebase_user.uid,
                    "created_at": datetime.now(timezone.utc),
                })
                try:
                    new_ref.set(record)
                except Exception as exc:
                    print("STUDENT FIRESTORE CREATE ERROR:", repr(exc), flush=True)
                    try:
                        auth.delete_user(firebase_user.uid, app=firebase_app)
                    except Exception as cleanup_error:
                        print("STUDENT FIREBASE CLEANUP ERROR:", repr(cleanup_error), flush=True)
                    messages.error(request, "The student record could not be saved. Please check Firestore and try again.")
                    return redirect("tutor_panel:manage_students")

                messages.success(request, f"Student {name} added successfully. Student ID: {new_ref.id}. Login email: {student_email}. Give the password to the student securely.")

            else:
                if not student_id:
                    messages.error(request, "Student ID is missing.")
                    return redirect("tutor_panel:manage_students")

                student_ref = students_ref.document(student_id)
                existing_doc = student_ref.get()
                if not existing_doc.exists:
                    messages.error(request, "Student record was not found.")
                    return redirect("tutor_panel:manage_students")

                existing = existing_doc.to_dict() or {}
                uid = (existing.get("firebase_uid") or "").strip()
                old_email = (existing.get("student_email") or existing.get("firebase_email") or "").strip().lower()

                # Keep legacy records editable, but only change login credentials when the
                # Firebase UID is available to safely identify the existing account.
                auth_user = None
                if uid:
                    try:
                        auth_user = auth.get_user(uid, app=firebase_app)
                        old_email = (auth_user.email or old_email).strip().lower()
                    except Exception as exc:
                        print("STUDENT FIREBASE LOOKUP ERROR:", repr(exc), flush=True)
                        messages.error(request, "Could not find this student's Firebase account. Other details were not changed.")
                        return redirect("tutor_panel:manage_students")

                    if not student_email:
                        messages.error(request, "Student login email is required.")
                        return redirect("tutor_panel:manage_students")
                    if student_password and len(student_password) < 8:
                        messages.error(request, "A new student password must contain at least 8 characters.")
                        return redirect("tutor_panel:manage_students")

                    auth_updates = {}
                    if student_email != old_email:
                        auth_updates["email"] = student_email
                    if student_password:
                        auth_updates["password"] = student_password
                    if name != (auth_user.display_name or ""):
                        auth_updates["display_name"] = name

                    if auth_updates:
                        try:
                            auth.update_user(uid, app=firebase_app, **auth_updates)
                        except auth.EmailAlreadyExistsError:
                            messages.error(request, "That login email is already used by another Firebase account.")
                            return redirect("tutor_panel:manage_students")
                        except Exception as exc:
                            print("STUDENT FIREBASE UPDATE ERROR:", repr(exc), flush=True)
                            messages.error(request, "Firebase could not update this student's login details. No student profile changes were saved.")
                            return redirect("tutor_panel:manage_students")

                    record.update({
                        "student_id": student_id,
                        "student_email": student_email,
                        "firebase_email": student_email,
                        "firebase_uid": uid,
                    })
                else:
                    # Do not create a second Firebase user for an old student record.
                    if student_email and student_email != old_email:
                        messages.error(request, "This student record is not linked to a Firebase UID, so its login email cannot safely be changed. Please contact support to link the existing account first.")
                        return redirect("tutor_panel:manage_students")
                    if student_password:
                        messages.error(request, "This student record is not linked to a Firebase UID, so its password cannot safely be reset here.")
                        return redirect("tutor_panel:manage_students")
                    if old_email:
                        record.update({"student_email": old_email, "firebase_email": old_email})

                try:
                    student_ref.update(record)
                except Exception as exc:
                    print("STUDENT FIRESTORE UPDATE ERROR:", repr(exc), flush=True)
                    # If Firebase credentials were changed but Firestore failed, attempt
                    # to restore the previous credentials to avoid mismatched login data.
                    if uid and auth_user is not None:
                        rollback = {}
                        if student_email != old_email:
                            rollback["email"] = old_email
                        if student_password:
                            messages.warning(request, "The profile save failed after the password was updated. The new password may already be active; please test it before trying again.")
                        if rollback:
                            try:
                                auth.update_user(uid, app=firebase_app, **rollback)
                            except Exception as rollback_error:
                                print("STUDENT FIREBASE ROLLBACK ERROR:", repr(rollback_error), flush=True)
                    messages.error(request, "The student profile could not be saved. Please try again.")
                    return redirect("tutor_panel:manage_students")

                if student_password:
                    messages.success(request, f"Student {name} updated. Login email saved and password reset requested successfully.")
                elif student_email != old_email:
                    messages.success(request, f"Student {name} updated and login email changed to {student_email}.")
                else:
                    messages.success(request, f"Student {name} updated successfully.")

            return redirect("tutor_panel:manage_students")

        elif action == "toggle_status":
            if not student_id:
                messages.error(request, "Student ID is missing.")
                return redirect("tutor_panel:manage_students")
            student_ref = students_ref.document(student_id)
            student_doc = student_ref.get()
            if not student_doc.exists:
                messages.error(request, "Student record was not found.")
            else:
                current = (student_doc.to_dict() or {}).get("status", "Active")
                new_status = "Inactive" if str(current).strip().lower() == "active" else "Active"
                student_ref.update({"status": new_status, "updated_at": datetime.now(timezone.utc)})
                messages.success(request, f"Student status changed to {new_status}.")
            return redirect("tutor_panel:manage_students")

        messages.error(request, "Invalid student action.")
        return redirect("tutor_panel:manage_students")

    students = []
    for document in students_ref.stream():
        student = document.to_dict() or {}
        student.setdefault("student_id", document.id)
        students.append(student)
    students.sort(key=lambda item: (item.get("name") or "").lower())

    tutors = []
    for document in db.collection("tutors").stream():
        tutor = document.to_dict() or {}
        if (tutor.get("status") or "").strip().lower() == "approved":
            tutors.append({"email": document.id, "name": tutor.get("name") or document.id})
    tutors.sort(key=lambda item: item["name"].lower())

    edit_id = (request.GET.get("edit") or "").strip()
    edit_student = None
    if edit_id:
        edit_doc = students_ref.document(edit_id).get()
        if edit_doc.exists:
            edit_student = edit_doc.to_dict() or {}
            edit_student["student_id"] = edit_doc.id
            edit_student["student_email"] = (
                edit_student.get("student_email") or edit_student.get("firebase_email") or ""
            )
            # Older records may have the UID but not the email fields.
            if not edit_student["student_email"] and edit_student.get("firebase_uid"):
                try:
                    edit_student["student_email"] = auth.get_user(
                        edit_student["firebase_uid"], app=firebase_app
                    ).email or ""
                except Exception as exc:
                    print("STUDENT EMAIL DISPLAY ERROR:", repr(exc), flush=True)

    return render(request, "tutor_panel/manage_students.html", {
        "students": students,
        "tutors": tutors,
        "edit_student": edit_student,
    })

def tutor_students(request):
    """Tutors can see only records assigned to their signed-in email."""
    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")
    if request.session.get("user_role") != "tutor":
        return redirect("tutor_panel:admin_dashboard")

    email = (request.session.get("firebase_email") or "").strip().lower()
    db = firestore.client(app=get_app())
    tutor_doc = db.collection("tutors").document(email).get()
    if not tutor_doc.exists or (tutor_doc.to_dict() or {}).get("status", "").strip().lower() != "approved":
        request.session.flush()
        return redirect("tutor_panel:login")

    students = []
    # Filter on the server using the authenticated session email.
    for document in db.collection("students").where("tutor_email", "==", email).stream():
        student = document.to_dict() or {}
        student.setdefault("student_id", document.id)
        students.append(student)
    students.sort(key=lambda item: (item.get("name") or "").lower())
    return render(request, "tutor_panel/tutor_students.html", {"students": students, "tutor_email": email})


# ------------------------------------------------------------
# CLASS ATTENDANCE AND STUDENT EVALUATION
# ------------------------------------------------------------
def tutor_attendance(request):
    """Allow an approved tutor to submit evaluations only for assigned students."""
    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")
    if request.session.get("user_role") != "tutor":
        return redirect("tutor_panel:admin_dashboard")

    email = (request.session.get("firebase_email") or "").strip().lower()
    db = firestore.client(app=get_app())

    tutor_doc = db.collection("tutors").document(email).get()
    tutor_data = tutor_doc.to_dict() or {} if tutor_doc.exists else {}
    if not tutor_doc.exists or (tutor_data.get("status") or "").strip().lower() != "approved":
        request.session.flush()
        return redirect("tutor_panel:login")

    students_ref = db.collection("students")
    assigned_students = []
    for doc in students_ref.where("tutor_email", "==", email).stream():
        student = doc.to_dict() or {}
        student.setdefault("student_id", doc.id)
        if (student.get("status") or "Active").strip().lower() == "active":
            assigned_students.append(student)
    assigned_students.sort(key=lambda item: (item.get("name") or "").lower())

    if request.method == "POST":
        student_id = (request.POST.get("student_id") or "").strip()
        student_doc = students_ref.document(student_id).get() if student_id else None
        student = student_doc.to_dict() or {} if student_doc and student_doc.exists else {}

        # Always verify assignment on the server; never trust the selected student alone.
        if not student_doc or not student_doc.exists or (student.get("tutor_email") or "").strip().lower() != email:
            messages.error(request, "Please select a student assigned to your account.")
            return redirect("tutor_panel:tutor_attendance")
        if (student.get("status") or "Active").strip().lower() != "active":
            messages.error(request, "Attendance cannot be recorded for an inactive student.")
            return redirect("tutor_panel:tutor_attendance")

        class_date = (request.POST.get("class_date") or "").strip()
        subject = (request.POST.get("subject") or "").strip()
        scheduled_time = (request.POST.get("scheduled_time") or "").strip()
        actual_start_time = (request.POST.get("actual_start_time") or "").strip()
        duration = (request.POST.get("duration") or "").strip()
        attendance_status = (request.POST.get("attendance_status") or "").strip()
        joined_on_time = (request.POST.get("joined_on_time") or "").strip()
        late_minutes = (request.POST.get("late_minutes") or "").strip()
        full_class = (request.POST.get("full_class") or "").strip()
        homework_assigned = (request.POST.get("homework_assigned") or "").strip()
        homework_status = (request.POST.get("homework_status") or "").strip()
        homework_quality = (request.POST.get("homework_quality") or "").strip()
        participation = (request.POST.get("participation") or "").strip()
        attention = (request.POST.get("attention") or "").strip()
        question_answering = (request.POST.get("question_answering") or "").strip()
        topic_understanding = (request.POST.get("topic_understanding") or "").strip()
        activities_completed = (request.POST.get("activities_completed") or "").strip()
        topic_taught = (request.POST.get("topic_taught") or "").strip()
        performance = (request.POST.get("performance") or "").strip()
        revision_required = (request.POST.get("revision_required") or "").strip()
        suggested_homework = (request.POST.get("suggested_homework") or "").strip()
        recording_url = (request.POST.get("recording_url") or "").strip()
        tutor_remarks = (request.POST.get("tutor_remarks") or "").strip()

        required = {
            "Class date": class_date,
            "Subject": subject,
            "Attendance status": attendance_status,
        }
        missing = [label for label, value in required.items() if not value]
        if missing:
            messages.error(request, "Please complete required fields: " + ", ".join(missing))
            return redirect("tutor_panel:tutor_attendance")

        allowed = {
            "attendance_status": {"Present", "Absent"},
            "joined_on_time": {"On time", "Late", "Not applicable"},
            "full_class": {"Yes", "No", "Not applicable"},
            "homework_assigned": {"Yes", "No"},
            "homework_status": {"Fully completed", "Partially completed", "Not completed", "Not applicable"},
            "homework_quality": {"Excellent", "Good", "Needs improvement", "Not checked", "Not applicable"},
            "participation": {"Very active", "Active", "Average", "Inactive", "Not applicable"},
            "attention": {"Always", "Mostly", "Sometimes", "Rarely", "Not applicable"},
            "question_answering": {"Excellent", "Good", "Average", "Needs improvement", "Not applicable"},
            "topic_understanding": {"Fully understood", "Partially understood", "Needs revision", "Not applicable"},
            "activities_completed": {"Fully", "Partially", "Not completed", "Not applicable"},
            "revision_required": {"Yes", "No"},
        }
        submitted_values = {
            "attendance_status": attendance_status,
            "joined_on_time": joined_on_time,
            "full_class": full_class,
            "homework_assigned": homework_assigned,
            "homework_status": homework_status,
            "homework_quality": homework_quality,
            "participation": participation,
            "attention": attention,
            "question_answering": question_answering,
            "topic_understanding": topic_understanding,
            "activities_completed": activities_completed,
            "revision_required": revision_required,
        }
        for field, value in submitted_values.items():
            if value and value not in allowed[field]:
                messages.error(request, "An invalid option was submitted. Please try again.")
                return redirect("tutor_panel:tutor_attendance")

        # Allow standard YouTube watch, short, and embed URLs only.
        if recording_url:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(recording_url)
            host = (parsed.hostname or "").lower()
            valid_youtube_host = host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}
            if parsed.scheme != "https" or not valid_youtube_host:
                messages.error(request, "Please enter a valid HTTPS YouTube recording link.")
                return redirect("tutor_panel:tutor_attendance")

        report = {
            "student_id": student_id,
            "student_name": student.get("name", ""),
            "student_class": student.get("student_class", ""),
            "tutor_email": email,
            "subject": subject,
            "class_date": class_date,
            "scheduled_time": scheduled_time,
            "actual_start_time": actual_start_time,
            "duration_minutes": duration,
            "attendance_status": attendance_status,
            "joined_on_time": joined_on_time,
            "late_minutes": late_minutes if joined_on_time == "Late" else "",
            "full_class": full_class,
            "homework_assigned": homework_assigned,
            "homework_status": homework_status,
            "homework_quality": homework_quality,
            "participation": participation,
            "attention": attention,
            "question_answering": question_answering,
            "topic_understanding": topic_understanding,
            "activities_completed": activities_completed,
            "topic_taught": topic_taught,
            "performance": performance,
            "revision_required": revision_required,
            "suggested_homework": suggested_homework,
            "recording_url": recording_url,
            "tutor_remarks": tutor_remarks,
            "created_at": datetime.now(timezone.utc),
        }
        db.collection("class_reports").add(report)
        messages.success(request, f"Class report saved for {student.get('name', 'student')}.")
        return redirect("tutor_panel:tutor_attendance")

    reports = []
    for doc in db.collection("class_reports").where("tutor_email", "==", email).stream():
        item = doc.to_dict() or {}
        item["report_id"] = doc.id
        reports.append(item)
    reports.sort(key=lambda item: item.get("class_date", ""), reverse=True)

    return render(request, "tutor_panel/tutor_attendance.html", {
        "students": assigned_students,
        "reports": reports[:50],
        "today": datetime.now().date().isoformat(),
        "tutor_email": email,
    })


# ------------------------------------------------------------
# ADMIN WEEKLY STUDENT PROGRESS REPORTS
# ------------------------------------------------------------
def weekly_student_reports(request):
    """Administrator-only weekly summary generated from saved class_reports."""
    from datetime import date, timedelta

    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")
    if not _is_tutorain_admin(request):
        return redirect("tutor_panel:admin_dashboard")

    today = date.today()
    default_start = today - timedelta(days=today.weekday())
    raw_start = (request.GET.get("week_start") or default_start.isoformat()).strip()
    try:
        week_start = date.fromisoformat(raw_start)
    except ValueError:
        week_start = default_start
    week_end = week_start + timedelta(days=6)
    start_text = week_start.isoformat()
    end_text = week_end.isoformat()

    db = firestore.client(app=get_app())
    student_map = {}
    for doc in db.collection("students").stream():
        student = doc.to_dict() or {}
        student_id = student.get("student_id") or doc.id
        student["student_id"] = student_id
        student_map[student_id] = student

    grouped = {}
    # class_date is saved as YYYY-MM-DD by the attendance form.
    for doc in db.collection("class_reports").stream():
        report = doc.to_dict() or {}
        class_date = str(report.get("class_date") or "")[:10]
        if not (start_text <= class_date <= end_text):
            continue
        sid = str(report.get("student_id") or "")
        student = student_map.get(sid, {})
        key = sid or (str(report.get("student_name") or ""),)
        if key not in grouped:
            grouped[key] = {
                "student_id": sid,
                "student_name": report.get("student_name") or student.get("name") or "Unknown student",
                "student_class": report.get("student_class") or student.get("student_class") or "",
                "tutor_email": report.get("tutor_email") or student.get("tutor_email") or "",
                "guardian_name": student.get("guardian_name") or "",
                "guardian_phone": student.get("guardian_phone") or "",
                "total_classes": 0, "present": 0, "absent": 0,
                "late": 0, "homework_values": [], "participation_values": [],
                "attention_values": [], "understanding_values": [],
                "revision_topics": [], "topics": [], "remarks": [],
                "recordings": [],
            }
        row = grouped[key]
        row["total_classes"] += 1
        status = str(report.get("attendance_status") or "").lower()
        if status == "present":
            row["present"] += 1
        elif status == "absent":
            row["absent"] += 1
        if str(report.get("joined_on_time") or "").lower() == "late":
            row["late"] += 1
        for field, target in [
            ("homework_status", "homework_values"),
            ("participation", "participation_values"),
            ("attention", "attention_values"),
            ("topic_understanding", "understanding_values"),
        ]:
            value = str(report.get(field) or "").strip()
            if value and value.lower() != "not applicable":
                row[target].append(value)
        if str(report.get("revision_required") or "").lower() == "yes":
            topic = str(report.get("topic_taught") or "").strip()
            row["revision_topics"].append(topic or "Revision recommended")
        topic = str(report.get("topic_taught") or "").strip()
        if topic:
            row["topics"].append(topic)
        remark = str(report.get("tutor_remarks") or "").strip()
        if remark:
            row["remarks"].append(f"{class_date}: {remark}")
        recording = str(report.get("recording_url") or "").strip()
        if recording:
            row["recordings"].append({"date": class_date, "url": recording, "subject": report.get("subject", "")})

    reports = list(grouped.values())
    reports.sort(key=lambda item: item["student_name"].lower())
    for row in reports:
        row["attendance_rate"] = round(row["present"] / row["total_classes"] * 100) if row["total_classes"] else 0
        row["topics"] = list(dict.fromkeys(row["topics"]))
        row["revision_topics"] = list(dict.fromkeys(row["revision_topics"]))
        row["homework_summary"] = ", ".join(row["homework_values"]) or "No data"
        row["participation_summary"] = ", ".join(row["participation_values"]) or "No data"
        row["attention_summary"] = ", ".join(row["attention_values"]) or "No data"
        row["understanding_summary"] = ", ".join(row["understanding_values"]) or "No data"

    return render(request, "tutor_panel/weekly_student_reports.html", {
        "reports": reports,
        "week_start": start_text,
        "week_end": end_text,
    })


# ------------------------------------------------------------
# PARENT PORTAL
# ------------------------------------------------------------
def parent_portal(request):
    """Show active students linked to the signed-in parent, with progress summaries."""
    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")
    if request.session.get("user_role") != "parent":
        return redirect("tutor_panel:dashboard")

    email = (request.session.get("firebase_email") or "").strip().lower()
    db = firestore.client(app=get_app())
    students = []

    for doc in db.collection("students").where("guardian_email", "==", email).stream():
        student = doc.to_dict() or {}
        if (student.get("status") or "Active").strip().lower() != "active":
            continue

        student_id = student.get("student_id") or doc.id
        reports = []
        for report_doc in db.collection("class_reports").where("student_id", "==", student_id).stream():
            report = report_doc.to_dict() or {}
            report["report_id"] = report_doc.id
            reports.append(report)
        reports.sort(key=lambda item: str(item.get("class_date") or ""), reverse=True)

        # Resolve tutor name from the existing tutors collection.
        tutor_email = (student.get("tutor_email") or "").strip().lower()
        tutor_name = tutor_email or "Not assigned"
        if tutor_email:
            tutor_doc = db.collection("tutors").document(tutor_email).get()
            if tutor_doc.exists:
                tutor_data = tutor_doc.to_dict() or {}
                tutor_name = (tutor_data.get("name") or tutor_data.get("full_name")
                              or tutor_data.get("display_name") or tutor_email)

        total_classes = len(reports)
        present = sum(1 for r in reports if str(r.get("attendance_status") or "").strip().lower() == "present")
        absent = sum(1 for r in reports if str(r.get("attendance_status") or "").strip().lower() == "absent")
        attendance_recorded = present + absent
        attendance_rate = round(present * 100 / attendance_recorded) if attendance_recorded else 0

        homework_values = [str(r.get("homework_status") or "").strip() for r in reports]
        homework_values = [x for x in homework_values if x and x.lower() != "not applicable"]
        homework_completed = sum(1 for x in homework_values if x.lower() == "fully completed")
        homework_partial = sum(1 for x in homework_values if x.lower() == "partially completed")
        homework_incomplete = sum(1 for x in homework_values if x.lower() == "not completed")

        understanding_values = [str(r.get("topic_understanding") or "").strip() for r in reports]
        understanding_values = [x for x in understanding_values if x and x.lower() != "not applicable"]
        understanding_summary = []
        for label in ("Fully understood", "Partially understood", "Needs revision"):
            count = sum(1 for x in understanding_values if x.lower() == label.lower())
            understanding_summary.append({"label": label, "count": count,
                                          "percent": round(count * 100 / len(understanding_values)) if understanding_values else 0})

        student["student_id"] = student_id
        student["tutor_name"] = tutor_name
        student["reports"] = reports[:30]
        student["progress"] = {
            "total_classes": total_classes,
            "present": present,
            "absent": absent,
            "attendance_rate": attendance_rate,
            "attendance_recorded": attendance_recorded,
            "homework_recorded": len(homework_values),
            "homework_completed": homework_completed,
            "homework_partial": homework_partial,
            "homework_incomplete": homework_incomplete,
            "understanding_summary": understanding_summary,
        }
        students.append(student)

    students.sort(key=lambda item: (item.get("name") or "").lower())
    return render(request, "tutor_panel/parent_portal.html", {
        "students": students,
        "parent_email": email,
    })


# ------------------------------------------------------------
# ADMIN TUTOR PAYMENT MANAGEMENT
# ------------------------------------------------------------
def tutor_payments(request):
    """Admin payment ledger: earnings are based only on Present class reports."""
    from datetime import date
    from decimal import Decimal, InvalidOperation

    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")
    if not _is_tutorain_admin(request):
        return redirect("tutor_panel:admin_dashboard")

    today = date.today()
    month = (request.GET.get("month") or today.strftime("%Y-%m")).strip()
    try:
        month_date = date.fromisoformat(month + "-01")
        month = month_date.strftime("%Y-%m")
    except ValueError:
        month = today.strftime("%Y-%m")

    db = firestore.client(app=get_app())
    tutors_ref = db.collection("tutors")
    payments_ref = db.collection("tutor_payments")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        tutor_email = (request.POST.get("tutor_email") or "").strip().lower()
        posted_month = (request.POST.get("month") or month).strip()
        try:
            date.fromisoformat(posted_month + "-01")
        except ValueError:
            messages.error(request, "Please select a valid payment month.")
            return redirect("tutor_panel:tutor_payments")

        tutor_ref = tutors_ref.document(tutor_email) if tutor_email else None
        tutor_doc = tutor_ref.get() if tutor_ref else None
        if not tutor_email or not tutor_doc or not tutor_doc.exists:
            messages.error(request, "Please select a valid tutor.")
            return redirect(f"/tutor_panel/tutor-payments/?month={posted_month}")

        tutor_data = tutor_doc.to_dict() or {}
        if action == "set_rate":
            try:
                rate = Decimal((request.POST.get("rate_per_class") or "").strip())
                if not rate.is_finite() or rate < 0 or rate > Decimal("1000000"):
                    raise InvalidOperation
                rate = rate.quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                messages.error(request, "Enter a valid non-negative class rate.")
                return redirect(f"/tutor_panel/tutor-payments/?month={posted_month}")
            tutor_ref.update({"rate_per_class": float(rate)})
            messages.success(request, f"Class rate updated for {tutor_data.get('name') or tutor_email}.")
            return redirect(f"/tutor_panel/tutor-payments/?month={posted_month}")

        if action == "record_payment":
            try:
                amount = Decimal((request.POST.get("amount") or "").strip())
                if not amount.is_finite() or amount <= 0 or amount > Decimal("100000000"):
                    raise InvalidOperation
                amount = amount.quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                messages.error(request, "Enter a valid payment amount greater than zero.")
                return redirect(f"/tutor_panel/tutor-payments/?month={posted_month}")

            payment_date = (request.POST.get("payment_date") or today.isoformat()).strip()
            try:
                date.fromisoformat(payment_date)
            except ValueError:
                messages.error(request, "Enter a valid payment date.")
                return redirect(f"/tutor_panel/tutor-payments/?month={posted_month}")
            note = (request.POST.get("note") or "").strip()[:500]
            payment_record = {
                "tutor_email": tutor_email,
                "tutor_name": tutor_data.get("name") or tutor_email,
                "month": posted_month,
                "amount": float(amount),
                "payment_date": payment_date,
                "note": note,
                "created_at": datetime.now(timezone.utc),
                "recorded_by": (request.session.get("firebase_email") or "").strip().lower(),
            }
            payments_ref.add(payment_record)
            messages.success(request, f"Payment of ₹{amount:,.2f} recorded for {tutor_data.get('name') or tutor_email}.")
            return redirect(f"/tutor_panel/tutor-payments/?month={posted_month}")

        messages.error(request, "Invalid payment action.")
        return redirect(f"/tutor_panel/tutor-payments/?month={posted_month}")

    tutors = []
    for doc in tutors_ref.stream():
        data = doc.to_dict() or {}
        if (data.get("status") or "").strip().lower() != "approved":
            continue
        try:
            rate = float(data.get("rate_per_class") or 0)
        except (TypeError, ValueError):
            rate = 0.0
        tutors.append({"email": doc.id, "name": data.get("name") or doc.id, "rate_per_class": rate})
    tutors.sort(key=lambda x: x["name"].lower())

    earnings = {t["email"]: {"present_classes": 0, "earned": 0.0, "paid": 0.0, "balance": 0.0} for t in tutors}
    # Class reports use YYYY-MM-DD and tutor_email. Only Present counts as payable.
    for doc in db.collection("class_reports").stream():
        report = doc.to_dict() or {}
        report_month = str(report.get("class_date") or "")[:7]
        email = (report.get("tutor_email") or "").strip().lower()
        if report_month == month and email in earnings and str(report.get("attendance_status") or "").strip().lower() == "present":
            earnings[email]["present_classes"] += 1

    payments = []
    for doc in payments_ref.where("month", "==", month).stream():
        item = doc.to_dict() or {}
        item["payment_id"] = doc.id
        email = (item.get("tutor_email") or "").strip().lower()
        if email in earnings:
            try:
                earnings[email]["paid"] += float(item.get("amount") or 0)
            except (TypeError, ValueError):
                pass
            payments.append(item)
    payments.sort(key=lambda x: str(x.get("payment_date") or ""), reverse=True)

    for tutor in tutors:
        row = earnings[tutor["email"]]
        row["earned"] = round(row["present_classes"] * tutor["rate_per_class"], 2)
        row["paid"] = round(row["paid"], 2)
        row["balance"] = round(row["earned"] - row["paid"], 2)
        tutor.update(row)

    # Sort payments newest first; the template displays only records for selected month.
    total_earned = round(sum(t["earned"] for t in tutors), 2)
    total_paid = round(sum(t["paid"] for t in tutors), 2)
    return render(request, "tutor_panel/tutor_payments.html", {
        "tutors": tutors,
        "payments": payments,
        "month": month,
        "today": today.isoformat(),
        "total_earned": total_earned,
        "total_paid": total_paid,
        "total_balance": round(total_earned - total_paid, 2),
    })


# ------------------------------------------------------------
# ADMIN TUTOR PAYMENT MANAGEMENT — PER-STUDENT RATE
# ------------------------------------------------------------
def tutor_payments(request):
    """Month-end tutor payments using each student's individual rate and Present attendance only."""
    from datetime import date
    from decimal import Decimal, InvalidOperation

    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")
    if not _is_tutorain_admin(request):
        return redirect("tutor_panel:admin_dashboard")

    today = date.today()
    month = (request.GET.get("month") or today.strftime("%Y-%m")).strip()
    try:
        month = date.fromisoformat(month + "-01").strftime("%Y-%m")
    except ValueError:
        month = today.strftime("%Y-%m")

    db = firestore.client(app=get_app())
    tutors_ref = db.collection("tutors")
    students_ref = db.collection("students")
    payments_ref = db.collection("tutor_payments")

    def month_redirect(value):
        return redirect(f"/tutor_panel/tutor-payments/?month={value}")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        posted_month = (request.POST.get("month") or month).strip()
        try:
            posted_month = date.fromisoformat(posted_month + "-01").strftime("%Y-%m")
        except ValueError:
            messages.error(request, "Please select a valid payment month.")
            return month_redirect(month)

        if action == "set_student_rate":
            student_id = (request.POST.get("student_id") or "").strip()
            try:
                rate = Decimal((request.POST.get("rate_per_class") or "").strip())
                if not rate.is_finite() or rate < 0 or rate > Decimal("1000000"):
                    raise InvalidOperation
                rate = rate.quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                messages.error(request, "Enter a valid non-negative payment rate.")
                return month_redirect(posted_month)
            student_ref = students_ref.document(student_id) if student_id else None
            student_doc = student_ref.get() if student_ref else None
            if not student_doc or not student_doc.exists:
                messages.error(request, "Student record was not found.")
                return month_redirect(posted_month)
            student_ref.update({"tutor_rate_per_class": float(rate)})
            student_data = student_doc.to_dict() or {}
            messages.success(request, f"Tutor rate saved for {student_data.get('name') or student_id}.")
            return month_redirect(posted_month)

        if action == "record_payment":
            tutor_email = (request.POST.get("tutor_email") or "").strip().lower()
            tutor_doc = tutors_ref.document(tutor_email).get() if tutor_email else None
            if not tutor_doc or not tutor_doc.exists:
                messages.error(request, "Please select a valid tutor.")
                return month_redirect(posted_month)
            tutor_data = tutor_doc.to_dict() or {}
            try:
                amount = Decimal((request.POST.get("amount") or "").strip())
                if not amount.is_finite() or amount <= 0 or amount > Decimal("100000000"):
                    raise InvalidOperation
                amount = amount.quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                messages.error(request, "Enter a valid payment amount greater than zero.")
                return month_redirect(posted_month)
            payment_date = (request.POST.get("payment_date") or today.isoformat()).strip()
            try:
                date.fromisoformat(payment_date)
            except ValueError:
                messages.error(request, "Enter a valid payment date.")
                return month_redirect(posted_month)
            payments_ref.add({
                "tutor_email": tutor_email,
                "tutor_name": tutor_data.get("name") or tutor_email,
                "month": posted_month,
                "amount": float(amount),
                "payment_date": payment_date,
                "note": (request.POST.get("note") or "").strip()[:500],
                "created_at": datetime.now(timezone.utc),
                "recorded_by": (request.session.get("firebase_email") or "").strip().lower(),
            })
            messages.success(request, f"Payment of ₹{amount:,.2f} recorded for {tutor_data.get('name') or tutor_email}.")
            return month_redirect(posted_month)

        messages.error(request, "Invalid payment action.")
        return month_redirect(posted_month)

    tutors = {}
    for doc in tutors_ref.stream():
        data = doc.to_dict() or {}
        if (data.get("status") or "").strip().lower() == "approved":
            tutors[doc.id.strip().lower()] = {"email": doc.id, "name": data.get("name") or doc.id,
                                              "present_classes": 0, "earned": 0.0, "paid": 0.0, "balance": 0.0}

    students = []
    student_by_id = {}
    for doc in students_ref.stream():
        data = doc.to_dict() or {}
        tutor_email = (data.get("tutor_email") or "").strip().lower()
        if tutor_email not in tutors or str(data.get("status") or "active").strip().lower() not in ("active", "approved", ""):
            continue
        try:
            rate = float(data.get("tutor_rate_per_class") or 0)
        except (TypeError, ValueError):
            rate = 0.0
        row = {"id": doc.id, "name": data.get("name") or doc.id,
               "student_class": data.get("student_class") or "", "tutor_email": tutor_email,
               "tutor_name": tutors[tutor_email]["name"], "rate_per_class": rate,
               "present_classes": 0, "earned": 0.0}
        students.append(row)
        student_by_id[doc.id] = row
    students.sort(key=lambda x: (x["tutor_name"].lower(), x["name"].lower()))

    # Reports are matched to the student document ID. Only Present attendance is payable.
    for doc in db.collection("class_reports").stream():
        report = doc.to_dict() or {}
        if str(report.get("class_date") or "")[:7] != month:
            continue
        if str(report.get("attendance_status") or "").strip().lower() != "present":
            continue
        student_id = str(report.get("student_id") or "").strip()
        row = student_by_id.get(student_id)
        # Fallback for older reports where the student ID may be absent: match name + tutor.
        if row is None and report.get("student_name"):
            report_tutor = (report.get("tutor_email") or "").strip().lower()
            matches = [s for s in students if s["name"] == report.get("student_name") and s["tutor_email"] == report_tutor]
            if len(matches) == 1:
                row = matches[0]
        if row:
            row["present_classes"] += 1
            row["earned"] = round(row["present_classes"] * row["rate_per_class"], 2)
            tutors[row["tutor_email"]]["present_classes"] += 1
            tutors[row["tutor_email"]]["earned"] += row["rate_per_class"]

    payments = []
    for doc in payments_ref.where("month", "==", month).stream():
        item = doc.to_dict() or {}
        email = (item.get("tutor_email") or "").strip().lower()
        if email in tutors:
            try:
                tutors[email]["paid"] += float(item.get("amount") or 0)
            except (TypeError, ValueError):
                pass
            item["payment_id"] = doc.id
            payments.append(item)
    payments.sort(key=lambda x: str(x.get("payment_date") or ""), reverse=True)

    tutor_rows = sorted(tutors.values(), key=lambda x: x["name"].lower())
    for tutor in tutor_rows:
        tutor["earned"] = round(tutor["earned"], 2)
        tutor["paid"] = round(tutor["paid"], 2)
        tutor["balance"] = round(tutor["earned"] - tutor["paid"], 2)
    total_earned = round(sum(t["earned"] for t in tutor_rows), 2)
    total_paid = round(sum(t["paid"] for t in tutor_rows), 2)
    return render(request, "tutor_panel/tutor_payments.html", {
        "tutors": tutor_rows, "students": students, "payments": payments, "month": month,
        "today": today.isoformat(), "total_earned": total_earned, "total_paid": total_paid,
        "total_balance": round(total_earned - total_paid, 2),
    })

# ------------------------------------------------------------
# AUTOMATIC WEEKLY EMAIL REPORTS TO PARENTS
# ------------------------------------------------------------
# AUTOMATIC WEEKLY EMAIL REPORTS TO PARENTS
# ------------------------------------------------------------

@csrf_exempt
def send_weekly_parent_reports(request):
    """Secured endpoint that emails parents the previous Monday-Sunday report."""

    import hmac
    from datetime import timedelta
    from django.http import HttpResponse
    from django.utils import timezone as django_timezone

    # 1. Verify the secret token
    expected = (
        getattr(settings, "TUTORAIN_WEEKLY_EMAIL_TOKEN", "") or ""
    ).strip()

    supplied = (
        request.headers.get("X-Tutorain-Weekly-Token") or ""
    ).strip()

    if not expected:
        return HttpResponse(
            "Weekly email token is not configured.",
            status=503,
        )

    if not supplied or not hmac.compare_digest(expected, supplied):
        return HttpResponse("Forbidden", status=403)

    # 2. Calculate the previous Monday-Sunday reporting period
    today = django_timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())

    week_start = this_monday - timedelta(days=7)
    week_end = week_start + timedelta(days=6)

    start_text = week_start.isoformat()
    end_text = week_end.isoformat()

    # 3. Connect to Firestore
    db = firestore.client(app=get_app())

    student_map = {}

    for doc in db.collection("students").stream():
        student = doc.to_dict() or {}

        student["student_id"] = str(
            student.get("student_id") or doc.id
        )

        student_map[student["student_id"]] = (doc.id, student)

    # 4. Collect class reports for the reporting period
    grouped = {}

    for doc in db.collection("class_reports").stream():
        report = doc.to_dict() or {}

        class_date = str(report.get("class_date") or "")[:10]

        if not start_text <= class_date <= end_text:
            continue

        student_id = str(
            report.get("student_id") or ""
        ).strip()

        match = student_map.get(student_id)

        # Fallback for older reports without a matching student ID
        if not match and report.get("student_name"):

            report_tutor = str(
                report.get("tutor_email") or ""
            ).strip().lower()

            candidates = [
                (doc_id, student)
                for doc_id, student in student_map.values()
                if str(student.get("name") or "").strip()
                == str(report.get("student_name") or "").strip()
                and str(student.get("tutor_email") or "").strip().lower()
                == report_tutor
            ]

            if len(candidates) == 1:
                match = candidates[0]

        if not match:
            continue

        student_doc_id, student = match

        parent_email = str(
            student.get("guardian_email") or ""
        ).strip().lower()

        if not parent_email:
            continue

        if str(student.get("status") or "Active").strip().lower() != "active":
            continue

        grouped.setdefault(
            student_doc_id,
            {
                "student": student,
                "parent_email": parent_email,
                "reports": [],
            },
        )["reports"].append((class_date, report))

    # 5. Send weekly emails
    logs = db.collection("weekly_parent_email_logs")

    sent = 0
    skipped = 0
    errors = []

    for student_doc_id, item in grouped.items():

        student = item["student"]
        parent_email = item["parent_email"]

        # Prevent duplicate successful emails for the same week
        log_ref = logs.document(
            f"{start_text}_{student_doc_id}"
        )

        old_log = log_ref.get()

        if (
            old_log.exists
            and (old_log.to_dict() or {}).get("status") == "sent"
        ):
            skipped += 1
            continue

        entries = sorted(
            item["reports"],
            key=lambda entry: entry[0],
        )

        # Attendance calculations
        present = sum(
            str(report.get("attendance_status") or "").strip().lower()
            == "present"
            for _, report in entries
        )

        absent = sum(
            str(report.get("attendance_status") or "").strip().lower()
            == "absent"
            for _, report in entries
        )

        late = sum(
            str(report.get("joined_on_time") or "").strip().lower()
            == "late"
            for _, report in entries
        )

        recorded = present + absent

        attendance_rate = (
            round(present * 100 / recorded)
            if recorded else 0
        )

        # Topics, subjects, homework and remarks
        topics = list(dict.fromkeys(
            str(report.get("topic_taught") or "").strip()
            for _, report in entries
            if str(report.get("topic_taught") or "").strip()
        ))

        subjects = list(dict.fromkeys(
            str(report.get("subject") or "").strip()
            for _, report in entries
            if str(report.get("subject") or "").strip()
        ))

        homework = [
            str(report.get("homework_status") or "").strip()
            for _, report in entries
            if str(report.get("homework_status") or "").strip()
            and str(report.get("homework_status") or "").strip().lower()
            != "not applicable"
        ]

        remarks = [
            f"{class_date}: {str(report.get('tutor_remarks') or '').strip()}"
            for class_date, report in entries
            if str(report.get("tutor_remarks") or "").strip()
        ]

        # Tutor details
        tutor_email = str(
            student.get("tutor_email") or ""
        ).strip().lower()

        tutor_name = tutor_email or "Not assigned"

        if tutor_email:
            tutor_doc = db.collection("tutors").document(
                tutor_email
            ).get()

            if tutor_doc.exists:
                tutor_name = (
                    (tutor_doc.to_dict() or {}).get("name")
                    or tutor_email
                )

        student_name = str(
            student.get("name") or "your child"
        )

        parent_name = str(
            student.get("guardian_name") or "Parent"
        )

        subjects_text = (
            ", ".join(subjects)
            if subjects
            else "No subject details recorded"
        )

        topics_text = (
            "\n".join(topics)
            if topics
            else "No topic details recorded."
        )

        homework_text = (
            "\n".join(homework)
            if homework
            else "No homework details recorded."
        )

        remarks_text = (
            "\n".join(remarks)
            if remarks
            else "No tutor remarks recorded."
        )

        # Email subject
        subject_line = (
            f"Tutorain Weekly Progress Report - "
            f"{student_name} ({start_text} to {end_text})"
        )

        # Plain-text version for email clients that don't support HTML
        plain_body = f"""
Dear {parent_name},

Here is the weekly learning progress report for {student_name}.

Reporting period: {start_text} to {end_text}

WEEKLY SUMMARY
Classes recorded: {len(entries)}
Present: {present}
Absent: {absent}
Late arrivals: {late}
Attendance rate: {attendance_rate}%
Subjects covered: {subjects_text}
Tutor: {tutor_name}

TOPICS COVERED
{topics_text}

HOMEWORK STATUS
{homework_text}

TUTOR REMARKS
{remarks_text}

Thank you for choosing Tutorain.

Regards,
Tutorain Team
https://www.tutorain.com/
""".strip()

        # Professional HTML version using your existing helper
        html_body = build_tutorain_weekly_email(
            parent_name=parent_name,
            student_name=student_name,
            week_start=start_text,
            week_end=end_text,
            total_classes=len(entries),
            present=present,
            absent=absent,
            late_arrivals=late,
            attendance_rate=attendance_rate,
            subjects=subjects_text,
            tutor_name=tutor_name,
            topics=topics_text,
            homework=homework_text,
            remarks=remarks_text,
        )

        # Record that sending has started
        now = datetime.now(timezone.utc)

        log_ref.set(
            {
                "student_id": student_doc_id,
                "student_name": student_name,
                "guardian_email": parent_email,
                "week_start": start_text,
                "week_end": end_text,
                "status": "sending",
                "updated_at": now,
            },
            merge=True,
        )

        # Send the HTML email with a plain-text fallback
        try:
            email = EmailMultiAlternatives(
                subject=subject_line,
                body=plain_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[parent_email],
            )

            email.attach_alternative(
                html_body,
                "text/html",
            )

            result = email.send(fail_silently=False)

            if result == 1:

                log_ref.set(
                    {
                        "status": "sent",
                        "sent_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    },
                    merge=True,
                )

                sent += 1

            else:

                log_ref.set(
                    {
                        "status": "failed",
                        "error": "Email backend did not confirm send.",
                        "updated_at": datetime.now(timezone.utc),
                    },
                    merge=True,
                )

                errors.append(student_name)

        except Exception as exc:

            log_ref.set(
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                    "updated_at": datetime.now(timezone.utc),
                },
                merge=True,
            )

            errors.append(
                f"{student_name} ({type(exc).__name__})"
            )

    # 6. Return a summary for Cloud Scheduler and logs
    summary = (
        f"Weekly parent emails for {start_text} to {end_text}. "
        f"Sent: {sent}; duplicate skips: {skipped}; "
        f"errors: {len(errors)}."
    )

    print(summary, flush=True)

    if errors:
        print(
            "WEEKLY PARENT EMAIL ERRORS: " + "; ".join(errors),
            flush=True,
        )

    return HttpResponse(summary, status=200)


def build_tutorain_weekly_email(
    parent_name,
    student_name,
    week_start,
    week_end,
    total_classes,
    present,
    absent,
    late_arrivals,
    attendance_rate,
    subjects,
    tutor_name,
    topics,
    homework,
    remarks,
):
    parent_name = escape(str(parent_name or "Parent"))
    student_name = escape(str(student_name or "Student"))
    tutor_name = escape(str(tutor_name or "Tutor"))
    subjects = escape(str(subjects or "Not recorded"))
    week_start = escape(str(week_start))
    week_end = escape(str(week_end))
    topics = "<br>".join(
        escape(line)
        for line in str(topics or "No topic details recorded.").splitlines()
    )

    homework = "<br>".join(
        escape(line)
        for line in str(homework or "No homework details recorded.").splitlines()
    )

    remarks = "<br>".join(
        escape(line)
        for line in str(remarks or "No tutor remarks recorded.").splitlines()
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f3f6fb;
                 font-family:Arial,Helvetica,sans-serif;color:#263247;">

      <div style="display:none;max-height:0;overflow:hidden;">
        Weekly learning progress report for {student_name}.
      </div>

      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:#f3f6fb;padding:28px 10px;">
        <tr>
          <td align="center">

            <table role="presentation" width="600" cellspacing="0"
                   cellpadding="0"
                   style="width:100%;max-width:600px;background:#ffffff;
                          border-radius:16px;overflow:hidden;">

              <tr>
                <td style="background:#173b70;padding:30px 32px;color:#ffffff;">
                  <div style="font-size:27px;font-weight:bold;letter-spacing:.3px;">
                    Tutorain
                  </div>
                  <div style="font-size:13px;color:#d8e7ff;margin-top:7px;">
                    LEARNING PROGRESS REPORT
                  </div>
                </td>
              </tr>

              <tr>
                <td style="padding:30px 32px 18px;">
                  <p style="font-size:15px;margin:0 0 12px;">
                    Dear {parent_name},
                  </p>

                  <h1 style="font-size:25px;color:#173b70;margin:0 0 12px;">
                    Weekly learning update
                  </h1>

                  <p style="font-size:14px;line-height:1.7;color:#627086;">
                    Here is the learning progress report for
                    <strong style="color:#263247;">{student_name}</strong>.
                    Review the attendance and learning activities from this week.
                  </p>

                  <div style="background:#edf4ff;border-radius:10px;
                              padding:15px 18px;margin-top:20px;">
                    <div style="font-size:12px;color:#627086;">
                      REPORTING PERIOD
                    </div>
                    <div style="font-size:15px;font-weight:bold;
                                color:#173b70;margin-top:5px;">
                      {week_start} &ndash; {week_end}
                    </div>
                  </div>
                </td>
              </tr>

              <tr>
                <td style="padding:8px 32px 24px;">
                  <h2 style="font-size:17px;color:#173b70;margin:0 0 14px;">
                    Attendance overview
                  </h2>

                  <table role="presentation" width="100%" cellspacing="0"
                         cellpadding="0">
                    <tr>
                      <td width="50%" style="padding:5px;">
                        <div style="background:#f0f5ff;padding:17px;
                                    border-radius:10px;">
                          <div style="font-size:12px;color:#627086;">
                            CLASSES RECORDED
                          </div>
                          <div style="font-size:27px;font-weight:bold;
                                      color:#173b70;margin-top:7px;">
                            {total_classes}
                          </div>
                        </div>
                      </td>

                      <td width="50%" style="padding:5px;">
                        <div style="background:#eaf8f0;padding:17px;
                                    border-radius:10px;">
                          <div style="font-size:12px;color:#347451;">
                            PRESENT
                          </div>
                          <div style="font-size:27px;font-weight:bold;
                                      color:#18794e;margin-top:7px;">
                            {present}
                          </div>
                        </div>
                      </td>
                    </tr>

                    <tr>
                      <td width="50%" style="padding:5px;">
                        <div style="background:#fff2ed;padding:17px;
                                    border-radius:10px;">
                          <div style="font-size:12px;color:#a64c36;">
                            ABSENT
                          </div>
                          <div style="font-size:27px;font-weight:bold;
                                      color:#b54732;margin-top:7px;">
                            {absent}
                          </div>
                        </div>
                      </td>

                      <td width="50%" style="padding:5px;">
                        <div style="background:#f4efff;padding:17px;
                                    border-radius:10px;">
                          <div style="font-size:12px;color:#6950a1;">
                            ATTENDANCE RATE
                          </div>
                          <div style="font-size:27px;font-weight:bold;
                                      color:#6941c6;margin-top:7px;">
                            {attendance_rate}%
                          </div>
                        </div>
                      </td>
                    </tr>
                  </table>

                  <p style="font-size:13px;color:#627086;margin:12px 5px 0;">
                    Late arrivals: <strong>{late_arrivals}</strong>
                  </p>
                </td>
              </tr>

              <tr>
                <td style="padding:0 32px 22px;">
                  <div style="border-top:1px solid #e7ecf3;padding-top:22px;">
                    <h2 style="font-size:17px;color:#173b70;margin:0 0 12px;">
                      Learning details
                    </h2>

                    <p style="font-size:13px;color:#627086;margin-bottom:5px;">
                      SUBJECTS COVERED
                    </p>
                    <p style="font-size:14px;line-height:1.7;margin-top:0;">
                      {subjects}
                    </p>

                    <p style="font-size:13px;color:#627086;margin-bottom:5px;">
                      TOPICS COVERED
                    </p>
                    <div style="font-size:14px;line-height:1.8;
                                background:#f8fafc;border-radius:8px;
                                padding:13px 15px;">
                      {topics}
                    </div>
                  </div>
                </td>
              </tr>

              <tr>
                <td style="padding:0 32px 22px;">
                  <h2 style="font-size:17px;color:#173b70;margin:0 0 12px;">
                    Homework status
                  </h2>
                  <div style="font-size:14px;line-height:1.8;
                              background:#f8fafc;border-radius:8px;
                              padding:13px 15px;">
                    {homework}
                  </div>
                </td>
              </tr>

              <tr>
                <td style="padding:0 32px 28px;">
                  <h2 style="font-size:17px;color:#173b70;margin:0 0 12px;">
                    Tutor's feedback
                  </h2>
                  <div style="font-size:14px;line-height:1.8;
                              background:#fff8e8;border-left:4px solid #e6ad38;
                              padding:15px;border-radius:4px;">
                    {remarks}
                  </div>

                  <p style="font-size:14px;color:#627086;margin-top:18px;">
                    <strong>Class tutor:</strong> {tutor_name}
                  </p>
                </td>
              </tr>

              <tr>
                <td style="background:#173b70;padding:25px 32px;
                           text-align:center;color:#ffffff;">
                  <div style="font-size:17px;font-weight:bold;">
                    Tutorain
                  </div>
                  <p style="font-size:12px;line-height:1.7;color:#d8e7ff;">
                    Thank you for choosing Tutorain.<br>
                    Supporting every student's learning journey.
                  </p>
                  <a href="https://www.tutorain.com/"
                     style="color:#ffffff;font-size:13px;">
                    www.tutorain.com
                  </a>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """



# ------------------------------------------------------------
# ADMIN ATTENDANCE SUMMARY DASHBOARD
# ------------------------------------------------------------

from datetime import date
from collections import defaultdict


def attendance_summary(request):
    """Display attendance statistics for authorized administrators."""

    # 1. Check that the user is logged in
    if not request.session.get("firebase_uid"):
        return redirect("tutor_panel:login")

    # 2. Verify admin permissions
    email = (
        request.session.get("firebase_email") or ""
    ).strip().lower()

    admin_emails = getattr(settings, "ADMIN_EMAILS", [])

    if isinstance(admin_emails, str):
        admin_emails = [admin_emails]

    admin_emails = [
        address.strip().lower()
        for address in admin_emails
        if address and address.strip()
    ]

    if (
        request.session.get("user_role") != "admin"
        or email not in admin_emails
    ):
        return redirect("tutor_panel:login")

    # 3. Read filters
    start_date = (request.GET.get("start_date") or "").strip()
    end_date = (request.GET.get("end_date") or "").strip()
    selected_student = (
        request.GET.get("student") or ""
    ).strip()
    selected_tutor = (
        request.GET.get("tutor") or ""
    ).strip()
    selected_subject = (
        request.GET.get("subject") or ""
    ).strip()

    # Validate optional dates
    try:
        start_value = date.fromisoformat(start_date) if start_date else None
        end_value = date.fromisoformat(end_date) if end_date else None

        if start_value and end_value and start_value > end_value:
            start_value, end_value = end_value, start_value
            start_date, end_date = end_date, start_date

    except ValueError:
        return HttpResponse(
            "Invalid date. Please select valid dates.",
            status=400,
        )

    # 4. Connect to Firestore
    db = firestore.client(app=get_app())

    reports = []
    student_options = set()
    tutor_options = set()
    subject_options = set()

    # 5. Read existing attendance records
    for doc in db.collection("class_reports").stream():
        report = doc.to_dict() or {}

        student_id = str(report.get("student_id") or "").strip()
        student_name = str(report.get("student_name") or "Unknown student").strip()
        student_class = str(report.get("student_class") or "").strip()
        tutor_email = str(report.get("tutor_email") or "").strip().lower()
        subject = str(report.get("subject") or "").strip()
        class_date = str(report.get("class_date") or "").strip()
        status = str(report.get("attendance_status") or "").strip().lower()

        # Ignore records with unrecognized attendance statuses
        if status not in {"present", "absent"}:
            continue

        student_options.add((student_id or student_name, student_name))
        if tutor_email:
            tutor_options.add(tutor_email)
        if subject:
            subject_options.add(subject)

        # Apply date filters
        if start_value or end_value:
            try:
                report_date = date.fromisoformat(class_date[:10])
            except ValueError:
                continue

            if start_value and report_date < start_value:
                continue

            if end_value and report_date > end_value:
                continue

        # Apply student, tutor, and subject filters
        if selected_student and (
            (student_id or student_name) != selected_student
        ):
            continue

        if selected_tutor and tutor_email != selected_tutor:
            continue

        if selected_subject and subject != selected_subject:
            continue

        reports.append({
            "student_id": student_id,
            "student_name": student_name,
            "student_class": student_class,
            "tutor_email": tutor_email,
            "subject": subject,
            "class_date": class_date,
            "attendance_status": status,
        })

    # 6. Calculate overall statistics
    total_classes = len(reports)
    total_present = sum(
        1 for report in reports
        if report["attendance_status"] == "present"
    )
    total_absent = sum(
        1 for report in reports
        if report["attendance_status"] == "absent"
    )

    attendance_rate = (
        round(total_present / total_classes * 100, 1)
        if total_classes else 0
    )

    # 7. Calculate student-wise statistics
    student_summary = defaultdict(lambda: {
        "student_id": "",
        "student_name": "",
        "student_class": "",
        "total": 0,
        "present": 0,
        "absent": 0,
    })

    for report in reports:
        key = report["student_id"] or report["student_name"]
        item = student_summary[key]

        item["student_id"] = key
        item["student_name"] = report["student_name"]
        item["student_class"] = report["student_class"]
        item["total"] += 1

        if report["attendance_status"] == "present":
            item["present"] += 1
        else:
            item["absent"] += 1

    student_rows = []

    for item in student_summary.values():
        item["attendance_rate"] = round(
            item["present"] / item["total"] * 100, 1
        ) if item["total"] else 0

        student_rows.append(item)

    student_rows.sort(
        key=lambda item: item["student_name"].lower()
    )

    # 8. Render dashboard
    return render(
        request,
        "tutor_panel/attendance_summary.html",
        {
            "total_classes": total_classes,
            "total_present": total_present,
            "total_absent": total_absent,
            "attendance_rate": attendance_rate,
            "student_rows": student_rows,
            "student_options": sorted(
                student_options, key=lambda item: item[1].lower()
            ),
            "tutor_options": sorted(tutor_options),
            "subject_options": sorted(subject_options),
            "start_date": start_date,
            "end_date": end_date,
            "selected_student": selected_student,
            "selected_tutor": selected_tutor,
            "selected_subject": selected_subject,
        },
    )


@ensure_csrf_cookie
def student_register_page(request):
    return render(request, "tutor_panel/student_register.html")


@require_POST
@csrf_protect
def student_send_registration_code(request):
    student_id = (request.POST.get("student_id") or "").strip()
    guardian_email = (
        request.POST.get("guardian_email") or ""
    ).strip().lower()

    if not student_id or not guardian_email:
        return JsonResponse({
            "success": False,
            "error": "Enter your Student ID and guardian email."
        }, status=400)

    try:
        db = firestore.client(app=get_app())
        student_ref = db.collection("students").document(student_id)
        student_doc = student_ref.get()

        # Use the existing Firestore record as the source of truth.
        if not student_doc.exists:
            return JsonResponse({
                "success": False,
                "error": "Student record not found. Check your Student ID."
            }, status=404)

        student = student_doc.to_dict() or {}

        if (student.get("status") or "Active").strip().lower() != "active":
            return JsonResponse({
                "success": False,
                "error": "This student account is inactive. Contact Tutorain."
            }, status=403)

        registered_guardian = (
            student.get("guardian_email") or ""
        ).strip().lower()

        if not registered_guardian or not constant_time_compare(
            guardian_email, registered_guardian
        ):
            return JsonResponse({
                "success": False,
                "error": "The Student ID or guardian email is incorrect."
            }, status=400)

        if student.get("firebase_uid"):
            return JsonResponse({
                "success": False,
                "error": "This student already has a login. Please sign in."
            }, status=409)

        # Simple session-based resend cooldown.
        last_sent = request.session.get("student_reg_last_sent", 0)

        if time.time() - last_sent < 60:
            return JsonResponse({
                "success": False,
                "error": "Please wait one minute before requesting another code."
            }, status=429)

        code = f"{secrets.randbelow(1_000_000):06d}"

        # Store a hash, not the verification code itself.
        request.session["student_reg_student_id"] = student_id
        request.session["student_reg_guardian_email"] = guardian_email
        request.session["student_reg_code_hash"] = hashlib.sha256(
            code.encode()
        ).hexdigest()
        request.session["student_reg_expires"] = int(time.time()) + 600
        request.session["student_reg_last_sent"] = time.time()
        request.session["student_reg_attempts"] = 0

        send_mail(
            subject="Tutorain Student Registration Verification",
            message=(
                f"Your Tutorain verification code is: {code}\n\n"
                "This code expires in 10 minutes. "
                "If you did not request it, you can ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[registered_guardian],
            fail_silently=False,
        )

        return JsonResponse({
            "success": True,
            "message": "Verification code sent to the registered guardian email."
        })

    except Exception as exc:
        print("STUDENT VERIFICATION EMAIL ERROR:", repr(exc), flush=True)

        return JsonResponse({
            "success": False,
            "error": "Could not send the verification email. Please try again."
        }, status=500)


@require_POST
@csrf_protect
def student_complete_registration(request):
    student_id = (request.POST.get("student_id") or "").strip()
    guardian_email = (
        request.POST.get("guardian_email") or ""
    ).strip().lower()
    email = (request.POST.get("student_email") or "").strip().lower()
    password = request.POST.get("password") or ""
    confirm_password = request.POST.get("confirm_password") or ""
    code = (request.POST.get("verification_code") or "").strip()

    # Ensure the user completes the same registration session.
    if (
        student_id != request.session.get("student_reg_student_id")
        or guardian_email != request.session.get("student_reg_guardian_email")
    ):
        return JsonResponse({
            "success": False,
            "error": "Please request a new verification code."
        }, status=400)

    expected_hash = request.session.get("student_reg_code_hash")
    expires = request.session.get("student_reg_expires", 0)

    if not expected_hash or time.time() > expires:
        return JsonResponse({
            "success": False,
            "error": "Your verification code has expired. Request a new one."
        }, status=400)

    attempts = request.session.get("student_reg_attempts", 0)

    if attempts >= 5:
        return JsonResponse({
            "success": False,
            "error": "Too many incorrect attempts. Request a new code."
        }, status=429)

    submitted_hash = hashlib.sha256(code.encode()).hexdigest()

    if not constant_time_compare(submitted_hash, expected_hash):
        request.session["student_reg_attempts"] = attempts + 1

        return JsonResponse({
            "success": False,
            "error": "Incorrect verification code."
        }, status=400)

    if not email or len(password) < 8 or password != confirm_password:
        return JsonResponse({
            "success": False,
            "error": "Enter a valid email, a password of at least 8 characters, and matching passwords."
        }, status=400)

    new_user = None
    linked = False

    try:
        db = firestore.client(app=get_app())
        student_ref = db.collection("students").document(student_id)
        student_doc = student_ref.get()

        if not student_doc.exists:
            return JsonResponse({
                "success": False,
                "error": "Student record not found."
            }, status=404)

        student = student_doc.to_dict() or {}

        # Recheck the record immediately before creating the account.
        if (
            (student.get("status") or "Active").strip().lower() != "active"
            or (student.get("guardian_email") or "").strip().lower()
            != guardian_email
            or student.get("firebase_uid")
        ):
            return JsonResponse({
                "success": False,
                "error": "Student record changed or already has a login. Contact Tutorain."
            }, status=409)

        if student.get("student_email"):
            return JsonResponse({
                "success": False,
                "error": "A student email is already linked to this record."
            }, status=409)

        # Never store the password in Firestore.
        new_user = auth.create_user(
            email=email,
            password=password,
            app=get_app(),
        )

        student_ref.update({
            "firebase_uid": new_user.uid,
            "student_email": email,
            "updated_at": datetime.now(timezone.utc),
        })
        linked = True

        request.session.pop("student_reg_student_id", None)
        request.session.pop("student_reg_guardian_email", None)
        request.session.pop("student_reg_code_hash", None)
        request.session.pop("student_reg_expires", None)
        request.session.pop("student_reg_last_sent", None)
        request.session.pop("student_reg_attempts", None)

        return JsonResponse({
            "success": True,
            "message": "Registration successful. You can now sign in."
        })

    except Exception as exc:
        print("STUDENT REGISTRATION ERROR:", repr(exc), flush=True)

        # Roll back the Firebase account if linking the record failed.
        if new_user is not None and not linked:
            try:
                auth.delete_user(new_user.uid, app=get_app())
            except Exception as cleanup_error:
                print(
                    "STUDENT REGISTRATION CLEANUP ERROR:",
                    repr(cleanup_error),
                    flush=True,
                )

        return JsonResponse({
            "success": False,
            "error": (
                "Registration could not be completed. "
                "If this continues, contact Tutorain support."
            )
        }, status=500)