import os
import hashlib
import tempfile
import pyotp
from .models import FileChunks, FileActivityLog
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
from datetime import datetime, timedelta
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.contrib import messages


def send_otp(request, user):
    to_email = user.email
    topt = pyotp.TOTP(pyotp.random_base32(), interval=60)
    otp = topt.now()
    request.session['otp_secret_key'] = topt.secret
    valid_date = datetime.now() + timedelta(minutes=1)
    request.session['otp_valid_date'] = str(valid_date)    
    mail_subject = 'OTP for Login'
    message = render_to_string('template_enter_otp.html', {
        'user': user,
        'domain': get_current_site(request).domain,
        'otp': otp,
        'protocol': 'https' if request.is_secure() else 'http'
    })
    email = EmailMessage(mail_subject, message, to=[to_email])
    if email.send():
        messages.success(request, f'Dear <b>{user}</b>, please go to your email <b>{to_email}</b> inbox and enter the OTP received to login. <b>Note:</b> Please remember to check your spam folder.')
    else:
        messages.error(request, f'Problem sending email to {to_email}, check if you typed it correctly.')
        

def generate_aes_key():
    """Generate a 256-bit AES key."""
    return get_random_bytes(32)  # 32 bytes = 256 bits


def encrypt_chunk(data, key):
    """Encrypt a data chunk with AES-256-CBC."""
    iv = get_random_bytes(16)  # AES block size for CBC
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(data, AES.block_size))
    return iv + encrypted  # Prepend IV for use during decryption


def decrypt_chunk(encrypted_data, key):
    """Decrypt a data chunk encrypted with AES-256-CBC."""
    iv = encrypted_data[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(encrypted_data[16:]), AES.block_size)


def split_file_to_chunks(file_bytes):
    """Split bytes into 3 equal (or nearly equal) parts."""
    total_len = len(file_bytes)
    chunk_size = total_len // 3
    return [
        file_bytes[0:chunk_size],
        file_bytes[chunk_size:chunk_size*2],
        file_bytes[chunk_size*2:]
    ]


def compute_sha256(data_bytes):
    """Compute SHA-256 hash of bytes."""
    return hashlib.sha256(data_bytes).hexdigest()


def combine_chunks_and_verify(chunks, original_hash):
    """Combine decrypted chunks and verify integrity."""
    combined_data = b''.join(chunks)
    combined_hash = compute_sha256(combined_data)
    if combined_hash == original_hash:
        return combined_data, True
    return None, False


def decrypt_and_combine_chunks(uploaded_file):
    """Decrypt chunks of the given file and verify integrity."""
    chunks_qs = FileChunks.objects.filter(main_file=uploaded_file).order_by('order')

    decrypted_chunks = []
    for chunk in chunks_qs:
        encrypted_data = chunk.chunk_file.read()
        decrypted = decrypt_chunk(encrypted_data, chunk.aes_key)
        decrypted_chunks.append(decrypted)

    combined_data, is_valid = combine_chunks_and_verify(decrypted_chunks, uploaded_file.file_hash)

    if not is_valid:
        return None  # Integrity check failed

    # Write combined file to temp location
    temp_dir = tempfile.gettempdir()
    combined_file_path = os.path.join(temp_dir, f"{uploaded_file.id}_restored_{uploaded_file.original_title}")

    with open(combined_file_path, 'wb') as f:
        f.write(combined_data)

    return combined_file_path


def log_file_action(file, user, action, details=""):
    FileActivityLog.objects.create(
        file_uid=file.file_uid,
        file_title=file.original_title,
        action=action,
        performed_by=user,
        details=details
    )
    