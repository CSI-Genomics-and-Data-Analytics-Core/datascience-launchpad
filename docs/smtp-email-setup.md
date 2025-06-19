# SMTP Email Configuration

The GeDaC Launchpad uses SMTP credentials for sending OTP emails. This supports any SMTP email provider including Gmail, Outlook, AWS SES, SendGrid, Mailgun, and others.

## Configuration

Set the following environment variables:

```bash
# SMTP Configuration
SMTP_USER=your_smtp_username
SMTP_PASSWORD=your_smtp_password
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_FROM_NAME="GeDaC Launchpad"

# SMTP Server Configuration (optional - defaults to AWS SES)
EMAIL_HOST=smtp.your-provider.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

## Popular SMTP Providers

### AWS SES
```bash
SMTP_USER=your_aws_ses_smtp_username
SMTP_PASSWORD=your_aws_ses_smtp_password
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

### Gmail
```bash
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

### Outlook/Hotmail
```bash
SMTP_USER=your_email@outlook.com
SMTP_PASSWORD=your_password
EMAIL_HOST=smtp-mail.outlook.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

### SendGrid
```bash
SMTP_USER=apikey
SMTP_PASSWORD=your_sendgrid_api_key
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

### Mailgun
```bash
SMTP_USER=your_mailgun_smtp_username
SMTP_PASSWORD=your_mailgun_smtp_password
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SMTP_USER` | SMTP username | - | Yes |
| `SMTP_PASSWORD` | SMTP password | - | Yes |
| `SMTP_FROM_EMAIL` | From email address | `noreply@yourdomain.com` | Yes |
| `SMTP_FROM_NAME` | From name | `GeDaC Launchpad` | No |
| `EMAIL_HOST` | SMTP server hostname | `email-smtp.ap-southeast-1.amazonaws.com` | No |
| `EMAIL_PORT` | SMTP server port | `465` | No |
| `EMAIL_USE_TLS` | Use TLS encryption | `false` | No |
| `EMAIL_USE_SSL` | Use SSL encryption | `true` | No |

## SSL vs TLS Configuration

- **SSL (Port 465)**: Set `EMAIL_USE_SSL=true` and `EMAIL_USE_TLS=false`
- **TLS (Port 587)**: Set `EMAIL_USE_SSL=false` and `EMAIL_USE_TLS=true`
- **Plain (Port 25)**: Set both to `false` (not recommended for production)

## Benefits of Generic SMTP

1. **Provider Flexibility**: Works with any SMTP email service
2. **Easy Migration**: Switch providers without code changes
3. **Cost Optimization**: Choose the most cost-effective email provider
4. **Reliability**: Use multiple providers for redundancy
5. **Standard Protocol**: Uses industry-standard SMTP

## Troubleshooting

### Common Issues

1. **Authentication Failed**:
   - Verify SMTP username and password
   - Check if 2FA requires app-specific password (Gmail)
   - Ensure SMTP is enabled on your email provider

2. **Connection Timeout**:
   - Check firewall settings for SMTP ports
   - Verify EMAIL_HOST is correct
   - Try different ports (25, 587, 465)

3. **TLS/SSL Errors**:
   - Match encryption settings with your provider
   - Port 587 usually requires TLS
   - Port 465 usually requires SSL

4. **Email Not Delivered**:
   - Check spam/junk folders
   - Verify sender email is authorized
   - Check provider sending limits

### Testing Email Configuration

The application will log email sending status. Check the application logs for:

- `"Using SMTP for email sending"` - SMTP is properly configured
- `"SMTP credentials not configured"` - Configuration error
- `"Email sent successfully via SMTP to {email}"` - Successful email delivery
- `"SMTP error sending email"` - SMTP connection or authentication issues

## Setup Checklist

- [ ] Choose an SMTP email provider
- [ ] Create SMTP credentials with your provider
- [ ] Configure environment variables
- [ ] Test email delivery
- [ ] Verify OTP emails are received
- [ ] Check spam/junk folders if emails are missing

## Security Best Practices

1. **Use App Passwords**: For Gmail, use app-specific passwords instead of your main password
2. **Secure Storage**: Store SMTP credentials securely (environment variables, secrets manager)
3. **Limit Permissions**: Use SMTP credentials with minimal required permissions
4. **Monitor Usage**: Keep track of email sending volumes and costs
5. **Backup Provider**: Consider configuring a backup SMTP provider
