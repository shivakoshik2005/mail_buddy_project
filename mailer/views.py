import os
import ssl
import socket
import smtplib
from email.message import EmailMessage
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.contrib import messages
from .models import EmailDraft
from .ai_service import generate_email_content


def extract_file_content(file_obj):
    try:
        if file_obj.name.endswith(('.txt', '.md', '.csv', '.json', '.log')):
            return file_obj.read().decode('utf-8', errors='ignore')[:3000]
    except Exception:
        pass
    return None


def force_ipv4_smtp_connect(host, port, use_ssl=True, timeout=10):
    """
    Forces Python socket creation to use IPv4 (AF_INET) exclusively.
    Prevents Render [Errno 101] Network is unreachable IPv6 routing failures.
    """
    # Resolve IPv4 address explicitly
    addr_info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    if not addr_info:
        raise OSError(f"Could not resolve IPv4 address for {host}")
    
    ip_address = addr_info[0][4][0]

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    if use_ssl:
        server = smtplib.SMTP_SSL(ip_address, port, context=context, timeout=timeout)
        # Re-set server hostname for TLS SNI extension validation
        server.server_hostname = host
    else:
        server = smtplib.SMTP(ip_address, port, timeout=timeout)
        server.starttls(context=context)
    
    return server


def login_required_custom(view_func):
    def wrapper(request, *args, **kwargs):
        if 'email_user' not in request.session or 'email_pass' not in request.session:
            messages.info(request, "Please enter your Gmail credentials to access Mail Buddy.")
            return redirect('smtp_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def smtp_login(request):
    if request.method == 'POST':
        email_user = request.POST.get('email_user', '').strip()
        email_pass = request.POST.get('email_pass', '').strip().replace(' ', '')

        if not email_user or not email_pass:
            messages.error(request, "Both Email Address and App Password are required.")
            return render(request, 'mailer/login.html')

        authenticated = False

        # 1. Try Forced IPv4 over SSL Port 465
        try:
            with force_ipv4_smtp_connect('smtp.gmail.com', 465, use_ssl=True, timeout=10) as server:
                server.login(email_user, email_pass)
                authenticated = True
        except smtplib.SMTPAuthenticationError:
            messages.error(request, "Invalid Credentials: Use your 16-character Google App Password.")
            return render(request, 'mailer/login.html')
        except Exception:
            # 2. Fallback: Forced IPv4 over STARTTLS Port 587
            try:
                with force_ipv4_smtp_connect('smtp.gmail.com', 587, use_ssl=False, timeout=10) as server:
                    server.login(email_user, email_pass)
                    authenticated = True
            except smtplib.SMTPAuthenticationError:
                messages.error(request, "Invalid Credentials: Use your 16-character Google App Password.")
                return render(request, 'mailer/login.html')
            except Exception as ex:
                messages.error(request, f"SMTP Connection Error: {str(ex)}")
                return render(request, 'mailer/login.html')

        if authenticated:
            request.session['email_user'] = email_user
            request.session['email_pass'] = email_pass
            messages.success(request, f"Authenticated successfully as {email_user}")
            return redirect('dashboard')

    return render(request, 'mailer/login.html')


def smtp_logout(request):
    request.session.flush()
    messages.info(request, "Logged out successfully.")
    return redirect('smtp_login')


@never_cache
@login_required_custom
def dashboard(request):
    emails = EmailDraft.objects.all().order_by('-created_at')
    return render(request, 'mailer/dashboard.html', {'emails': emails})


@login_required_custom
def compose(request):
    if request.method == 'POST':
        receiver_name = request.POST.get('receiver_name', '').strip()
        receiver_email = request.POST.get('receiver_email', '').strip()
        subject = request.POST.get('subject', '').strip()
        description = request.POST.get('description', '').strip()
        tone = request.POST.get('tone', 'professional')
        attachment = request.FILES.get('attachment')

        doc_text = None
        if attachment:
            doc_text = extract_file_content(attachment)

        try:
            new_subject, body = generate_email_content(
                receiver_name=receiver_name,
                description=description,
                subject=subject,
                tone=tone,
                document_text=doc_text
            )

            draft = EmailDraft.objects.create(
                receiver_name=receiver_name,
                receiver_email=receiver_email,
                subject=new_subject,
                description=description,
                tone=tone,
                generated_body=body,
                attachment=attachment
            )
            return redirect('preview', draft_id=draft.id)
        except Exception as e:
            messages.error(request, f"AI Generation Error: {str(e)}")
            return render(request, 'mailer/compose.html', {
                'receiver_name': receiver_name,
                'receiver_email': receiver_email,
                'subject': subject,
                'description': description,
                'tone': tone,
            })

    return render(request, 'mailer/compose.html')


@never_cache
@login_required_custom
def preview(request, draft_id):
    draft = get_object_or_404(EmailDraft, id=draft_id)

    if draft.status == 'sent':
        if request.method == 'POST':
            messages.warning(request, "This email has already been sent.")
            return redirect('dashboard')

    if request.method == 'POST':
        edited_subject = request.POST.get('subject', '').strip()
        edited_body = request.POST.get('generated_body', '').strip()
        
        if edited_subject:
            draft.subject = edited_subject
        if edited_body:
            draft.generated_body = edited_body
        draft.save()

        if 'recompose' in request.POST:
            doc_text = None
            if draft.attachment:
                try:
                    draft.attachment.open('rb')
                    doc_text = extract_file_content(draft.attachment)
                except Exception:
                    pass

            try:
                new_subject, body = generate_email_content(
                    receiver_name=draft.receiver_name,
                    description=draft.description,
                    subject=draft.subject,
                    tone=draft.tone,
                    document_text=doc_text
                )
                draft.generated_body = body
                draft.subject = new_subject
                draft.save()
                messages.success(request, "Draft regenerated with AI successfully.")
            except Exception as e:
                messages.error(request, f"Recomposition Error: {str(e)}")
            return redirect('preview', draft_id=draft.id)

        elif 'send' in request.POST:
            sender = request.session.get('email_user')
            password = request.session.get('email_pass')

            msg = EmailMessage()
            msg.set_content(draft.generated_body)
            msg['Subject'] = draft.subject
            msg['From'] = sender
            msg['To'] = draft.receiver_email

            if draft.attachment:
                try:
                    draft.attachment.open('rb')
                    file_data = draft.attachment.read()
                    file_name = draft.filename()
                    msg.add_attachment(file_data, maintype='application', subtype='octet-stream', filename=file_name)
                except Exception as e:
                    messages.error(request, f"Attachment Error: {str(e)}")
                    return redirect('preview', draft_id=draft.id)

            sent_successfully = False

            # 1. Dispatch over Forced IPv4 SSL Port 465
            try:
                with force_ipv4_smtp_connect('smtp.gmail.com', 465, use_ssl=True, timeout=10) as server:
                    server.login(sender, password)
                    server.send_message(msg)
                    sent_successfully = True
            except Exception:
                # 2. Dispatch over Forced IPv4 STARTTLS Port 587
                try:
                    with force_ipv4_smtp_connect('smtp.gmail.com', 587, use_ssl=False, timeout=10) as server:
                        server.login(sender, password)
                        server.send_message(msg)
                        sent_successfully = True
                except Exception as ex:
                    messages.error(request, f"SMTP Connection Error: {str(ex)}")
                    return redirect('preview', draft_id=draft.id)

            if sent_successfully:
                draft.status = 'sent'
                draft.save()
                messages.success(request, f"Email sent successfully to {draft.receiver_email}!")
                return redirect('dashboard')

    response = render(request, 'mailer/preview.html', {'draft': draft})
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@require_POST
@login_required_custom
def delete_draft(request, draft_id):
    draft = get_object_or_404(EmailDraft, id=draft_id)
    recipient = draft.receiver_email
    
    if draft.attachment and os.path.isfile(draft.attachment.path):
        os.remove(draft.attachment.path)

    draft.delete()
    messages.info(request, f"Conversation draft for {recipient} deleted successfully.")
    return redirect('dashboard')