import jwt
import time
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

# 1. Get your secret
SECRET = os.getenv("SUPABASE_JWT_SECRET")
if not SECRET:
    print("❌ Error: AUTH_SECRET_KEY is missing in .env")
    exit(1)

# 2. Define a fake user (mimicking Supabase structure)
user_id = str(uuid.uuid4()) # Or use a specific UUID if you want a consistent user
payload = {
    "aud": "authenticated",       # Supabase checks this
    "role": "authenticated",      # Supabase RLS checks this
    "sub": user_id,               # The User ID
    "email": "test@backend.dev",
    "exp": int(time.time()) + (60 * 60 * 24 * 30) # Expires in 30 days
}

# 3. Sign it using HS256 (The "Legacy" way)
token = jwt.encode(payload, SECRET, algorithm="HS256")

print("-" * 60)
print(f"🔑 TEST USER ID: {user_id}")
print("-" * 60)
print("👇 COPY THIS TOKEN FOR POSTMAN / SWAGGER 👇")
print(token)
print("-" * 60)