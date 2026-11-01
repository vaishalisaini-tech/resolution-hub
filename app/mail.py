# Resolution Hub email helper. SMTP configuration is a server-environment concern.
import os,ssl,smtplib,logging
from email.message import EmailMessage

log=logging.getLogger('resolution-hub.mail')

def mail_configured():
    """Email sending is enabled only when a host and a from-address are configured."""
    return bool(os.getenv('SMTP_HOST') and os.getenv('MAIL_FROM'))

def reset_link(token):
    base=os.getenv('APP_BASE_URL','http://127.0.0.1:8001').rstrip('/')
    return base+'/?reset='+token

def send_reset_email(to_address,username,token):
    """Send a password-reset email.

    Returns True when a message was dispatched over SMTP. When SMTP is not
    configured the reset link is written to the server log so a local/dev
    operator can still complete the flow. Never raises to the caller: a mail
    transport failure must not reveal whether an account exists.
    """
    link=reset_link(token)
    if not mail_configured():
        log.warning('SMTP not configured; password reset link for %s: %s',username,link)
        return False
    msg=EmailMessage()
    msg['Subject']='Resolution Hub password reset'
    msg['From']=os.getenv('MAIL_FROM')
    msg['To']=to_address
    expiry=os.getenv('RESET_TOKEN_MINUTES','30')
    msg.set_content(
        f'Hello {username},\n\n'
        'A password reset was requested for your Resolution Hub account.\n'
        f'Open the link below to choose a new password. It expires in {expiry} minutes '
        'and can be used once:\n\n'
        f'{link}\n\n'
        'If you did not request this, ignore this email; your password is unchanged.\n'
    )
    host=os.getenv('SMTP_HOST');port=int(os.getenv('SMTP_PORT','587'))
    user=os.getenv('SMTP_USERNAME');password=os.getenv('SMTP_PASSWORD')
    use_ssl=os.getenv('SMTP_SSL','false').lower()=='true'
    use_tls=os.getenv('SMTP_STARTTLS','true').lower()=='true'
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host,port,timeout=15,context=ssl.create_default_context()) as s:
                if user:s.login(user,password or '')
                s.send_message(msg)
        else:
            with smtplib.SMTP(host,port,timeout=15) as s:
                if use_tls:s.starttls(context=ssl.create_default_context())
                if user:s.login(user,password or '')
                s.send_message(msg)
        log.info('Password reset email sent for %s',username)
        return True
    except Exception:
        log.exception('Failed to send password reset email for %s',username)
        return False
