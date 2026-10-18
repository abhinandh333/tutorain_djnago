import json
from datetime import datetime, timezone

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from firebase_admin import auth, get_app, firestore
from tutorain import firebase_config




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
        stage = "connecting to Firestore"
        db = firestore.client(app=get_app())

        stage = "reading tutor document"
        tutor_ref = db.collection("tutors").document(email)
        tutor_doc = tutor_ref.get()

        if not tutor_doc.exists:
            return JsonResponse({
                "success": False,
                "error": (
                    "Your tutor account was not found. "
                    "Please contact the administrator."
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
                        )
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