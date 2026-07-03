# Supabase Email Templates for Granthiq

Copy and paste the **Subject** and **Body** for each email type into your Supabase Authentication -> Email Templates settings.

---

## 1. Confirm Sign Up

**Subject:**
`Confirm your account on Granthiq`

**Body:**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="font-family: 'Inter', Helvetica, Arial, sans-serif; background-color: #09090b; margin: 0; padding: 0;">
  <div style="width: 100%; padding: 60px 0;">
    <div style="max-width: 500px; margin: 0 auto; background-color: #18181b; border: 1px solid #27272a; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.4);">
      
      <!-- Header -->
      <div style="padding: 32px 32px 0 32px; text-align: center;">
         <!-- Placeholder for Logo if you have a public URL, otherwise Text -->
         <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0;">Granthiq</h1>
      </div>

      <!-- Content -->
      <div style="padding: 32px;">
        <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; text-align: center;">Confirm your email</h2>
        <p style="color: #a1a1aa; font-size: 15px; line-height: 24px; margin: 0 0 24px 0; text-align: center;">
          Welcome to Granthiq! Please confirm your email address to activate your account and start your research journey.
        </p>

        <div style="text-align: center; margin-bottom: 32px;">
          <a href="{{ .ConfirmationURL }}" style="background-color: #FFFFFF; color: #000000; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 15px; text-decoration: none; display: inline-block;">
            Confirm Email
          </a>
        </div>

        <p style="color: #52525b; font-size: 13px; margin: 0; text-align: center;">
          If you didn't create an account, you can safely ignore this email.
        </p>
      </div>

      <!-- Footer -->
      <div style="background-color: #18181b; padding: 20px 32px; border-top: 1px solid #27272a; text-align: center;">
        <p style="color: #52525b; font-size: 12px; margin: 0;">
          &copy; 2026 Granthiq. All rights reserved.
        </p>
      </div>
    </div>
  </div>
</body>
</html>
```

---

## 2. Invite User

**Subject:**
`You've been invited to join Granthiq`

**Body:**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="font-family: 'Inter', Helvetica, Arial, sans-serif; background-color: #09090b; margin: 0; padding: 0;">
  <div style="width: 100%; padding: 60px 0;">
    <div style="max-width: 500px; margin: 0 auto; background-color: #18181b; border: 1px solid #27272a; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.4);">
      
      <!-- Header -->
      <div style="padding: 32px 32px 0 32px; text-align: center;">
         <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0;">Granthiq</h1>
      </div>

      <!-- Content -->
      <div style="padding: 32px;">
        <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; text-align: center;">You're invited!</h2>
        <p style="color: #a1a1aa; font-size: 15px; line-height: 24px; margin: 0 0 24px 0; text-align: center;">
          You have been invited to collaborate on Granthiq. Click the button below to accept your invitation.
        </p>

        <div style="text-align: center; margin-bottom: 32px;">
          <a href="{{ .InviteURL }}" style="background-color: #FFFFFF; color: #000000; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 15px; text-decoration: none; display: inline-block;">
            Accept Invitation
          </a>
        </div>

        <p style="color: #52525b; font-size: 13px; margin: 0; text-align: center;">
          If you weren't expecting this invitation, you can delete this email.
        </p>
      </div>

      <!-- Footer -->
      <div style="background-color: #18181b; padding: 20px 32px; border-top: 1px solid #27272a; text-align: center;">
        <p style="color: #52525b; font-size: 12px; margin: 0;">
          &copy; 2026 Granthiq. All rights reserved.
        </p>
      </div>
    </div>
  </div>
</body>
</html>
```

---

## 3. Magic Link

**Subject:**
`Your login link for Granthiq`

**Body:**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="font-family: 'Inter', Helvetica, Arial, sans-serif; background-color: #09090b; margin: 0; padding: 0;">
  <div style="width: 100%; padding: 60px 0;">
    <div style="max-width: 500px; margin: 0 auto; background-color: #18181b; border: 1px solid #27272a; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.4);">
      
      <!-- Header -->
      <div style="padding: 32px 32px 0 32px; text-align: center;">
         <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0;">Granthiq</h1>
      </div>

      <!-- Content -->
      <div style="padding: 32px;">
        <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; text-align: center;">Sign in to your account</h2>
        <p style="color: #a1a1aa; font-size: 15px; line-height: 24px; margin: 0 0 24px 0; text-align: center;">
          Click the button below to sign in instantly. This link will expire in 24 hours.
        </p>

        <div style="text-align: center; margin-bottom: 32px;">
          <a href="{{ .ConfirmationURL }}" style="background-color: #FFFFFF; color: #000000; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 15px; text-decoration: none; display: inline-block;">
            Sign In
          </a>
        </div>

        <p style="color: #52525b; font-size: 13px; margin: 0; text-align: center;">
          If you didn't request this login link, you can safely ignore this email.
        </p>
      </div>

      <!-- Footer -->
      <div style="background-color: #18181b; padding: 20px 32px; border-top: 1px solid #27272a; text-align: center;">
        <p style="color: #52525b; font-size: 12px; margin: 0;">
          &copy; 2026 Granthiq. All rights reserved.
        </p>
      </div>
    </div>
  </div>
</body>
</html>
```

---

## 4. Change Email Address

**Subject:**
`Confirm email change for Granthiq`

**Body:**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="font-family: 'Inter', Helvetica, Arial, sans-serif; background-color: #09090b; margin: 0; padding: 0;">
  <div style="width: 100%; padding: 60px 0;">
    <div style="max-width: 500px; margin: 0 auto; background-color: #18181b; border: 1px solid #27272a; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.4);">
      
      <!-- Header -->
      <div style="padding: 32px 32px 0 32px; text-align: center;">
         <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0;">Granthiq</h1>
      </div>

      <!-- Content -->
      <div style="padding: 32px;">
        <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; text-align: center;">Confirm new email address</h2>
        <p style="color: #a1a1aa; font-size: 15px; line-height: 24px; margin: 0 0 24px 0; text-align: center;">
          You requested to change your email address to <strong style="color: #fff;">{{ .NewEmail }}</strong>. Click below to confirm.
        </p>

        <div style="text-align: center; margin-bottom: 32px;">
          <a href="{{ .ConfirmationURL }}" style="background-color: #FFFFFF; color: #000000; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 15px; text-decoration: none; display: inline-block;">
            Confirm Change
          </a>
        </div>
      </div>

      <!-- Footer -->
      <div style="background-color: #18181b; padding: 20px 32px; border-top: 1px solid #27272a; text-align: center;">
        <p style="color: #52525b; font-size: 12px; margin: 0;">
          &copy; 2026 Granthiq. All rights reserved.
        </p>
      </div>
    </div>
  </div>
</body>
</html>
```

---

## 5. Reset Password

**Subject:**
`Reset your Granthiq password`

**Body:**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="font-family: 'Inter', Helvetica, Arial, sans-serif; background-color: #09090b; margin: 0; padding: 0;">
  <div style="width: 100%; padding: 60px 0;">
    <div style="max-width: 500px; margin: 0 auto; background-color: #18181b; border: 1px solid #27272a; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.4);">
      
      <!-- Header -->
      <div style="padding: 32px 32px 0 32px; text-align: center;">
         <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0;">Granthiq</h1>
      </div>

      <!-- Content -->
      <div style="padding: 32px;">
        <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; text-align: center;">Reset your password</h2>
        <p style="color: #a1a1aa; font-size: 15px; line-height: 24px; margin: 0 0 24px 0; text-align: center;">
          We received a request to reset your password. Click the button below to choose a new one.
        </p>

        <div style="text-align: center; margin-bottom: 32px;">
          <a href="{{ .ConfirmationURL }}" style="background-color: #FFFFFF; color: #000000; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 15px; text-decoration: none; display: inline-block;">
            Reset Password
          </a>
        </div>

        <p style="color: #52525b; font-size: 13px; margin: 0; text-align: center;">
          If you didn't ask for this, you can safely ignore this email.
        </p>
      </div>

      <!-- Footer -->
      <div style="background-color: #18181b; padding: 20px 32px; border-top: 1px solid #27272a; text-align: center;">
        <p style="color: #52525b; font-size: 12px; margin: 0;">
          &copy; 2026 Granthiq. All rights reserved.
        </p>
      </div>
    </div>
  </div>
</body>
</html>
```

---

## 6. Reauthentication

**Subject:**
`Your verification code for Granthiq`

**Body:**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="font-family: 'Inter', Helvetica, Arial, sans-serif; background-color: #09090b; margin: 0; padding: 0;">
  <div style="width: 100%; padding: 60px 0;">
    <div style="max-width: 500px; margin: 0 auto; background-color: #18181b; border: 1px solid #27272a; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.4);">
      
      <!-- Header -->
      <div style="padding: 32px 32px 0 32px; text-align: center;">
         <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0;">Granthiq</h1>
      </div>

      <!-- Content -->
      <div style="padding: 32px;">
        <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; text-align: center;">Verify it's you</h2>
        <p style="color: #a1a1aa; font-size: 15px; line-height: 24px; margin: 0 0 24px 0; text-align: center;">
         Enter the following code to confirm your identity.
        </p>

        <div style="text-align: center; margin-bottom: 32px;">
           <span style="display: inline-block; background-color: #27272a; color: #ffffff; font-size: 32px; font-weight: 700; padding: 16px 32px; border-radius: 12px; letter-spacing: 4px;">
             {{ .Token }}
           </span>
        </div>

        <p style="color: #52525b; font-size: 13px; margin: 0; text-align: center;">
          This code will expire in 5 minutes.
        </p>
      </div>

      <!-- Footer -->
      <div style="background-color: #18181b; padding: 20px 32px; border-top: 1px solid #27272a; text-align: center;">
        <p style="color: #52525b; font-size: 12px; margin: 0;">
          &copy; 2026 Granthiq. All rights reserved.
        </p>
      </div>
    </div>
  </div>
</body>
</html>
```

