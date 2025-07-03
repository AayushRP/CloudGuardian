import pyotp
import os
import csv
from datetime import datetime
from django.db.models import Q
from .models import UploadedFiles, FileChunks, FileActivityLog
from .forms import RegisterForm, UploadedFilesForm, LoginForm
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models.functions import TruncDay
from django.db.models import Count
import calendar

from .utils import (
    send_otp,
    generate_aes_key,
    encrypt_chunk,
    compute_sha256,
    split_file_to_chunks,
    decrypt_and_combine_chunks,
    log_file_action,
    validate_file_upload,
)

from .tokens import account_activation_token

# Create your views here.

def sign_up(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            activate_email(request, user, form.cleaned_data.get('email'))
            return redirect('/home')
    else:
        form = RegisterForm()
        
    return render(request, 'registration/sign_up.html', {"form": form})


def activate(request, uidb64, token):
    User = get_user_model()
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except:
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()

        messages.success(request, "Thank you for your email confirmation. Now you can login your account.")
        return redirect('login')
    else:
        messages.error(request, "Activation link is invalid!")

    return redirect('home')


def activate_email(request, user, to_email):
    mail_subject = 'Activate your user account'
    message = render_to_string('template_activate_account.html', {
        'user': user,
        'domain': get_current_site(request).domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': account_activation_token.make_token(user),
        'protocol': 'https' if request.is_secure() else 'http'
    })
    email = EmailMessage(mail_subject, message, to=[to_email])
    if email.send():
        messages.success(request, f'Dear <b>{user}</b>, please go to your email <b>{to_email}</b> inbox and click on the activation link to complete the registration. <b>Note:</b> Please remember to check your spam folder.')
    else:
        messages.error(request, f'Problem sending email to {to_email}, check if you typed it correctly.')


def index(request):
    return render(request, 'storage/index.html')


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            try:
                # Check if user exists
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                try:
                    # Optional: Try with email too
                    user = User.objects.get(email=username)
                except User.DoesNotExist:
                    user = None

            if user is not None:
                if not user.is_active:
                    form.add_error(None, 'Your email is registered but not verified.')
                else:
                    # Auth only if verified
                    user = authenticate(request, username=user.username, password=password)
                    if user:
                        send_otp(request, user)
                        request.session['username'] = username
                        return redirect('otp')
                    else:
                        form.add_error(None, 'Invalid credentials.')
            else:
                form.add_error(None, 'Invalid credentials.')  # Generic message if user not found
    else:
        form = LoginForm()

    return render(request, 'registration/login.html', {'form': form})


def otp_view(request):
    if request.method == 'POST':
        otp = request.POST['otp']
        username = request.session['username']
        otp_secret_key = request.session['otp_secret_key']
        otp_valid_date = request.session['otp_valid_date']
        if otp_secret_key and otp_valid_date is not None:
            valid_date = datetime.fromisoformat(otp_valid_date)
        
            if valid_date > datetime.now():
                totp = pyotp.TOTP(otp_secret_key, interval=60)
                if totp.verify(otp):
                    user = get_object_or_404(User, username=username)
                    login(request, user)
                    del request.session['otp_secret_key']
                    del request.session['otp_valid_date']
                    return redirect('home')
                else:
                    messages.error(request, f'The OTP you entered is invalid!')
            else:
                messages.error(request, f'The OTP you entered has expired!')  
        else:
            messages.error(request, f'Opps.. something went wrong.')
        
    return render(request, 'registration/otp.html', {})    


#Home page after login
@login_required
def home(request):
    if 'username' in request.session:
        del request.session['username']
    user = request.user

    # 📤 Uploaded Files Daily
    uploaded_stats = (
        UploadedFiles.objects.filter(owner=user)
        .annotate(day=TruncDay('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )

    uploaded_labels = [item['day'].strftime("%Y-%m-%d") for item in uploaded_stats if item['day']]
    uploaded_counts = [item['count'] for item in uploaded_stats if item['day']]

    # 🤝 Shared With Me Daily
    shared_stats = (
        UploadedFiles.objects.filter(shared_users=user)
        .annotate(day=TruncDay('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )

    shared_labels = [item['day'].strftime("%Y-%m-%d") for item in shared_stats if item['day']]
    shared_counts = [item['count'] for item in shared_stats if item['day']]

    recent_uploaded = UploadedFiles.objects.filter(owner=user).order_by('-created_at')[:5]
    shared_with_me = UploadedFiles.objects.filter(shared_users=user).order_by('-created_at')[:5]
    recent_logs = FileActivityLog.objects.filter(performed_by=user).order_by('-timestamp')[:5]

    context = {
        'recent_uploaded': recent_uploaded,
        'shared_with_me': shared_with_me,
        'recent_logs': recent_logs,
        'uploaded_labels': uploaded_labels,
        'uploaded_counts': uploaded_counts,
        'shared_labels': shared_labels,
        'shared_counts': shared_counts,
    }

    if user.is_staff:
        context.update({
            'total_files': UploadedFiles.objects.count(),
            'total_users': User.objects.count(),
            'all_logs': FileActivityLog.objects.order_by('-timestamp')[:5],
        })

    return render(request, 'storage/home.html', context)


@login_required
def logout_view(request):
    logout(request)
    return redirect('/login')


@login_required
def my_profile(request):
    user = request.user
    password_form = PasswordChangeForm(user)

    if request.method == 'POST':
        password_form = PasswordChangeForm(user, request.POST)
        if password_form.is_valid():
            password_form.save()
            update_session_auth_hash(request, password_form.user)
            messages.success(request, 'Your password was successfully updated.')
            return redirect('my_profile')
        else:
            messages.error(request, 'Please correct the errors below.')

    # ✅ File Stats
    files_uploaded = UploadedFiles.objects.filter(owner=user).count()
    files_shared_with_others = UploadedFiles.objects.filter(owner=user).exclude(shared_users=None).count()
    files_shared_with_me = UploadedFiles.objects.filter(shared_users=user).count()

    return render(request, 'storage/users/my_profile.html', {
        'user': user,
        'password_form': password_form,
        'files_uploaded': files_uploaded,
        'files_shared_with_others': files_shared_with_others,
        'files_shared_with_me': files_shared_with_me,
    })
    

@login_required
def myFilesIndex(request):
    files = UploadedFiles.objects.filter(owner=request.user).order_by('-created_at')
    paginator = Paginator(files, 3)  # Show 10 files per page

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'storage/files/my_files_index.html', {'page_obj': page_obj})


@login_required
def sharedFilesIndex(request):
    user = request.user

    # Get user's groups
    user_groups = user.groups.all()

    # Files shared directly with the user or with any of the user's groups
    shared_files = UploadedFiles.objects.filter(
        Q(shared_users=user) | Q(shared_groups__in=user_groups)
    ).distinct()
    
    # Pagination
    paginator = Paginator(shared_files, 3)  # Show 3 files per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Add can_view flag to each file in page_obj
    for file in page_obj:
        file.can_view = (
            file.owner == user or
            user in file.shared_users.all() or
            file.shared_groups.filter(id__in=user_groups.values_list('id', flat=True)).exists()
        )

    return render(request, 'storage/files/shared_files.html', {
        'page_obj': page_obj,
        'user_groups': user_groups,
    })


@login_required
def create_file(request):
    if request.method == 'POST':
        form = UploadedFilesForm(request.POST, request.FILES)
        file_obj = request.FILES.get('main_file')

        if not file_obj:
            messages.error(request, "You must select a file.")
        elif file_obj:
            try:
                validate_file_upload(file_obj)
            except ValidationError as ve:
                # Extract first message cleanly
                error_message = ve.messages[0] if hasattr(ve, 'messages') else str(ve)
                messages.error(request, error_message)
                return render(request, 'storage/files/create_file.html', {
                    'form': form
                })
                
        if form.is_valid():
            uploaded_file = form.save(commit=False)
            uploaded_file.owner = request.user
            uploaded_file.original_title = file_obj.name
            
            # Read entire file into memory
            file_bytes = file_obj.read()

            # 1. Compute and save file hash
            file_hash = compute_sha256(file_bytes)
            uploaded_file.file_hash = file_hash
            uploaded_file.save()
            form.save_m2m()

            # 2. Split file into 3 chunks
            chunks = split_file_to_chunks(file_bytes)

            # 3. Encrypt each chunk, store in DB and filesystem
            for i, chunk in enumerate(chunks, start=1):
                key = generate_aes_key()
                encrypted_data = encrypt_chunk(chunk, key)

                chunk_filename = f"{uploaded_file.id}_chunk{i}.bin"
                file_chunk = FileChunks(
                    main_file=uploaded_file,
                    order=i,
                    aes_key=key,
                )
                file_chunk.chunk_file.save(chunk_filename, ContentFile(encrypted_data))
                file_chunk.save()
                
            log_file_action(uploaded_file, request.user, 'created', 'File created and uploaded')

            messages.success(request, f'Your file has been successfully uploaded.')  
            return redirect("/files/my-files")
    else:
        form = UploadedFilesForm()

    return render(request, 'storage/files/create_file.html', {'form': form})


@login_required
def view_file(request, file_uid):
    uploaded_file = get_object_or_404(UploadedFiles, file_uid=file_uid)

    # Check if user is the owner
    is_owner = request.user == uploaded_file.owner

    # Check if user is directly shared
    is_shared_user = request.user in uploaded_file.shared_users.all()

    # Check if user belongs to any of the shared groups
    user_group_ids = request.user.groups.values_list('id', flat=True)
    is_shared_with_group = uploaded_file.shared_groups.filter(id__in=user_group_ids).exists()

    # Final permission flag
    is_allowed = is_owner or is_shared_user or is_shared_with_group

    if not is_allowed:
        return HttpResponseForbidden("You do not have permission to view this file.")

    return render(request, 'storage/files/view_file.html', {
        'file': uploaded_file,
        'is_allowed': is_allowed,
    })
    
    
@login_required
def delete_file(request, file_uid):
    file = get_object_or_404(UploadedFiles, file_uid=file_uid)

    if request.user != file.owner:
        messages.error(request, "You are not authorized to delete this file.")
        return redirect('my_files_index')

    if request.method == 'POST':
        password = request.POST.get('password')

        user = authenticate(request, username=request.user.username, password=password)
        if user is not None:
            # 1. Delete chunk files from filesystem
            chunks = FileChunks.objects.filter(main_file=file)
            for chunk in chunks:
                if chunk.chunk_file and os.path.isfile(chunk.chunk_file.path):
                    os.remove(chunk.chunk_file.path)

            # 2. Delete chunk records from DB
            chunks.delete()

            # 3. Delete UploadedFiles record
            
            file.delete()

            log_file_action(file, request.user, 'deleted', "File permanently deleted")

            messages.success(request, "File deleted successfully.")
        else:
            messages.error(request, "Incorrect password. File not deleted.")

    return redirect('my_files_index')


@login_required
def change_permissions(request, file_uid):
    file = get_object_or_404(UploadedFiles, file_uid=file_uid)

    if file.owner != request.user:
        return HttpResponseForbidden("You do not have permission to change permissions for this file.")

    if request.method == 'POST':
        form = UploadedFilesForm(request.POST, instance=file)
        if form.is_valid():
            # Store current (old) permissions before clearing
            old_users = set(file.shared_users.all())
            old_groups = set(file.shared_groups.all())
            
            # Clear old permissions
            file.shared_users.clear()
            file.shared_groups.clear()

            # Save the form but prevent auto-saving m2m fields
            file = form.save(commit=False)
            file.save()

            # Update many-to-many fields manually
            new_users = set(form.cleaned_data['shared_users'])
            new_groups = set(form.cleaned_data['shared_groups'])
            
            file.shared_users.set(new_users)
            file.shared_groups.set(new_groups)
    
            # Calculate added users/groups for logging
            added_users = new_users - old_users
            added_groups = new_groups - old_groups        
            
            # Prepare logging detail
            details = []
            if added_users:
                details.append(f"Added users: {', '.join(u.username for u in added_users)}")
            if added_groups:
                details.append(f"Added groups: {', '.join(g.name for g in added_groups)}")

            log_file_action(file, request.user, 'shared_updated', "; ".join(details) or "No new permissions added.")

            messages.success(request, 'Permissions updated successfully.')
            return redirect('my_files_index')
    else:
        form = UploadedFilesForm(instance=file)

    return render(request, 'storage/files/change_permissions.html', {
        'form': form,
        'file': file
    })


@login_required
def download_file(request, file_uid):
    uploaded_file = get_object_or_404(UploadedFiles, file_uid=file_uid)

    # Permissions
    is_owner = request.user == uploaded_file.owner
    is_shared_user = request.user in uploaded_file.shared_users.all()
    is_shared_with_group = uploaded_file.shared_groups.filter(id__in=request.user.groups.values_list('id', flat=True)).exists()

    if not (is_owner or is_shared_user or is_shared_with_group):
        return HttpResponseForbidden("You do not have permission to download this file.")

    # File integrity and decryption
    combined_file_path = decrypt_and_combine_chunks(uploaded_file)

    if not combined_file_path:
        messages.error(request, "File integrity verification failed. The file may have been tampered with.")
        return redirect('/files/my-files/')

    with open(combined_file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{uploaded_file.original_title}"'
        log_file_action(uploaded_file, request.user, 'downloaded', 'File downloaded')
        return response
    
    
@staff_member_required
def all_file_logs(request):
    logs = FileActivityLog.objects.all()
    return render(request, 'admin/all_file_logs.html', {'logs': logs})


@staff_member_required
def current_file_logs_list(request):
    files = UploadedFiles.objects.all().order_by('-created_at')
    return render(request, 'admin/current_file_logs_list.html', {'files': files})


@staff_member_required
def current_file_log_details(request, file_uid):
    if not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to view this page.")
    
    logs = FileActivityLog.objects.filter(file_uid=file_uid)

    if not logs.exists():
        return HttpResponseNotFound("No logs found for this file.")

    file_title = logs.first().file_title

    try:
        uploaded_file = UploadedFiles.objects.get(file_uid=file_uid)
    except UploadedFiles.DoesNotExist:
        uploaded_file = None

    return render(request, 'admin/current_file_log_details.html', {
        'file': uploaded_file,
        'file_title': file_title,
        'logs': logs,
    })
    

@staff_member_required
def export_all_file_logs(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to download the logs of the system.")
    
    logs = FileActivityLog.objects.all().order_by('-timestamp')

    if not logs.exists():
        return HttpResponse("No logs available.", status=404)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="all_file_logs.csv"'

    writer = csv.writer(response)
    writer.writerow(['S.N.', 'Timestamp', 'Performed By', 'Action', 'Details', 'File Title', 'File UID'])

    for index, log in enumerate(logs, start=1):
        writer.writerow([
            index,
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            log.performed_by.get_username() if log.performed_by else "Deleted User",
            log.action,
            log.details,
            log.file_title,
            log.file_uid
        ])

    return response


@staff_member_required
def export_individual_file_logs(request, file_uid):
    if not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to download the logs for this file.")
    
    logs = FileActivityLog.objects.filter(file_uid=file_uid)
    if not logs.exists():
        return HttpResponse("No logs found for this file.", status=404)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="file_{file_uid}_logs.csv"'

    writer = csv.writer(response)
    writer.writerow(['SN', 'Timestamp', 'Performed By', 'Action', 'Details', 'File Title', 'File UID'])

    for index, log in enumerate(logs, start=1):
        writer.writerow([
            index,
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            log.performed_by.get_username() if log.performed_by else "Deleted User",
            log.action,
            log.details,
            log.file_title,
            log.file_uid
        ])

    return response