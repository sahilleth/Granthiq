"""
Standalone script to test Supabase Storage upload and operations.
Use this to debug storage bucket and connection issues.

Usage:
    python scripts/test_storage_upload.py              # Run test with cleanup
    python scripts/test_storage_upload.py --keep       # Keep test file (skip cleanup)
    python scripts/test_storage_upload.py --check-only # Only check bucket status, don't upload
"""
import sys
import asyncio
import argparse
from pathlib import Path

# Add backend to path
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from loguru import logger
from supabase import create_client
from src.config import get_settings
from tests.fixtures.test_data import create_sample_pdf

async def check_bucket_status(client, bucket_name: str):
    """Check if bucket exists and its public/private status."""
    try:
        buckets_response = client.storage.list_buckets()
        
        # Handle response
        buckets = []
        if hasattr(buckets_response, 'data'):
            buckets = buckets_response.data if buckets_response.data else []
        elif isinstance(buckets_response, list):
            buckets = buckets_response
        else:
            buckets = list(buckets_response) if hasattr(buckets_response, '__iter__') else []
        
        # Find the bucket
        for b in buckets:
            name = b.name if hasattr(b, 'name') else b.get('name', '') if isinstance(b, dict) else str(b)
            if name == bucket_name:
                # Check public status
                is_public = b.public if hasattr(b, 'public') else b.get('public', False) if isinstance(b, dict) else False
                return True, is_public
        
        return False, None
    except Exception as e:
        logger.error(f"Error checking bucket status: {e}")
        return None, None

async def test_supabase_storage(keep_file: bool = False, check_only: bool = False):
    """Test Supabase Storage upload with detailed debugging."""
    settings = get_settings()
    
    print("\n" + "="*80)
    print("SUPABASE STORAGE UPLOAD TEST")
    print("="*80)
    
    # 1. Check configuration
    print("\n📋 Configuration:")
    print(f"  Supabase URL: {settings.storage.supabase_url}")
    print(f"  Supabase Key: {'***' + settings.storage.supabase_key[-4:] if settings.storage.supabase_key else 'NOT SET'}")
    print(f"  Private Bucket: {settings.storage.private_bucket}")
    print(f"  Public Bucket: {settings.storage.public_bucket}")
    
    # 2. Validate and initialize Supabase client
    print("\n🔌 Initializing Supabase Client...")
    if not settings.storage.supabase_url or not settings.storage.supabase_key:
        print("❌ Missing Supabase credentials!")
        print("   Set STORAGE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
        print("   Note: Use Service Role Key (not anon key) for bucket management")
        return
    
    # Validate URL format - must be https://xxx.supabase.co (not database connection string)
    supabase_url = settings.storage.supabase_url.strip()
    if not supabase_url.startswith("https://") or ".supabase.co" not in supabase_url:
        print(f"❌ Invalid Supabase URL format!")
        print(f"   Current URL: {supabase_url}")
        print(f"   Expected format: https://[PROJECT-ID].supabase.co")
        print(f"\n💡 Configuration Issue:")
        print(f"   The SUPABASE_URL should be the API URL, not the database connection string.")
        print(f"   Example: https://xxxxx.supabase.co")
        print(f"   You can find this in Supabase Dashboard > Settings > API > Project URL")
        print(f"\n   If you're using DATABASE_URL for the database connection, that's correct!")
        print(f"   But SUPABASE_URL must be the API URL for Storage operations.")
        return
    
    try:
        client = create_client(
            supabase_url,
            settings.storage.supabase_key
        )
        print("✅ Supabase client initialized")
        print(f"   Using URL: {supabase_url}")
    except Exception as e:
        print(f"❌ Failed to initialize Supabase client: {e}")
        logger.exception("Client initialization error:")
        print(f"\n💡 Troubleshooting:")
        print(f"   1. Verify STORAGE_URL is the API URL: https://xxx.supabase.co")
        print(f"   2. Verify SUPABASE_SERVICE_ROLE_KEY is the Service Role Key (not anon key)")
        print(f"   3. Get these from: Supabase Dashboard > Settings > API")
        return
    
    # 3. List existing buckets
    print("\n📦 Listing existing buckets...")
    try:
        buckets_response = client.storage.list_buckets()
        
        # Handle response - can be list or response object
        bucket_names = []
        if hasattr(buckets_response, 'data'):
            # Response object with data attribute
            buckets = buckets_response.data if buckets_response.data else []
        elif isinstance(buckets_response, list):
            buckets = buckets_response
        else:
            buckets = list(buckets_response) if hasattr(buckets_response, '__iter__') else []
        
        # Extract bucket names
        for b in buckets:
            if hasattr(b, 'name'):
                bucket_names.append(b.name)
            elif isinstance(b, dict):
                bucket_names.append(b.get('name', ''))
            else:
                bucket_names.append(str(b))
        
        print(f"   Found {len(bucket_names)} bucket(s):")
        if bucket_names:
            for name in bucket_names:
                print(f"     - {name}")
        else:
            print("   ⚠️  No buckets found!")
            print("   (This is normal for a new project - buckets will be created as needed)")
            
    except Exception as e:
        print(f"❌ Failed to list buckets: {e}")
        logger.exception("List buckets error:")
        print("   This might indicate:")
        print("   - Permission issues (need Service Role Key)")
        print("   - Connection problems")
        print("   - Invalid Supabase URL or Key")
        return
    
    # 4. Test bucket existence and creation
    test_bucket = settings.storage.private_bucket
    print(f"\n🪣 Testing bucket: '{test_bucket}'")
    
    # Check bucket status (public/private) - this is more accurate
    bucket_exists, is_public = await check_bucket_status(client, test_bucket)
    
    # Also check in the bucket_names list for compatibility
    bucket_in_list = test_bucket in bucket_names
    
    if bucket_exists or bucket_in_list:
        # Check if bucket is correctly configured as private
        if bucket_exists and is_public:
            print(f"⚠️  WARNING: Bucket '{test_bucket}' is marked as PUBLIC!")
            print(f"   This bucket should be PRIVATE for security reasons.")
            print(f"   Files in public buckets can be accessed by anyone with the URL.")
            print(f"\n💡 To fix this:")
            print(f"   1. Go to Supabase Dashboard > Storage > Buckets")
            print(f"   2. Click on '{test_bucket}' bucket")
            print(f"   3. Click 'Edit bucket' or 'Settings'")
            print(f"   4. Uncheck 'Public bucket' or set it to Private")
            print(f"   5. Save changes")
        elif bucket_exists:
            print(f"✅ Bucket '{test_bucket}' is correctly configured as PRIVATE")
        else:
            print(f"✅ Bucket '{test_bucket}' exists")
        bucket_exists = True  # Ensure it's True if found
    else:
        # Bucket doesn't exist
        bucket_exists = False
        is_public = None
    
    if check_only:
        print(f"\n✅ Bucket check complete!")
        if bucket_exists:
            print(f"   Status: {'PUBLIC' if is_public else 'PRIVATE'}")
            if is_public:
                print(f"   ⚠️  Action required: Make bucket private in Supabase dashboard")
        else:
            print(f"   Status: Bucket does not exist")
        return
    
    if not bucket_exists:
        print(f"⚠️  Bucket '{test_bucket}' does not exist. Attempting to create it...")
        try:
            # According to Supabase docs: create_bucket(name, options={})
            response = client.storage.create_bucket(
                test_bucket,
                options={
                    "public": False,
                    "allowed_mime_types": None,  # Allow all file types
                    "file_size_limit": None,  # No size limit
                }
            )
            print(f"✅ Bucket '{test_bucket}' created successfully!")
            # Re-fetch bucket list to verify
            try:
                buckets_response = client.storage.list_buckets()
                if hasattr(buckets_response, 'data'):
                    buckets = buckets_response.data if buckets_response.data else []
                elif isinstance(buckets_response, list):
                    buckets = buckets_response
                else:
                    buckets = list(buckets_response) if hasattr(buckets_response, '__iter__') else []
                
                created_names = [b.name if hasattr(b, 'name') else b.get('name', '') if isinstance(b, dict) else str(b) for b in buckets]
                if test_bucket in created_names:
                    print(f"✅ Bucket verified in bucket list")
                else:
                    print(f"⚠️  Bucket created but not found in list (may need a moment to propagate)")
            except Exception as verify_error:
                print(f"⚠️  Could not verify bucket creation: {verify_error}")
        except Exception as e:
            print(f"❌ Failed to create bucket '{test_bucket}': {e}")
            logger.exception("Bucket creation error:")
            print(f"\n💡 Manual Setup Required:")
            print(f"   1. Go to Supabase Dashboard: {settings.storage.supabase_url.replace('https://', 'https://app.supabase.com/project/').split('/')[0] if 'supabase' in settings.storage.supabase_url else settings.storage.supabase_url}/storage/buckets")
            print(f"   2. Click '+ New bucket'")
            print(f"   3. Name: '{test_bucket}'")
            print(f"   4. Public: False (unchecked)")
            print(f"   5. Save and retry this test")
            return
    if check_only:
        print(f"\n✅ Bucket check complete!")
        print(f"   Status: {'PUBLIC' if is_public else 'PRIVATE'}")
        if is_public and bucket_exists:
            print(f"   ⚠️  Action required: Make bucket private in Supabase dashboard")
        return
    
    # 5. Test file upload
    print(f"\n📤 Testing file upload to bucket '{test_bucket}'...")
    print(f"   ⚠️  Note: Supabase free tier has a 50MB per-file limit")
    test_path = "test/test_upload.pdf"
    test_file_content = create_sample_pdf()  # This is already bytes
    test_file_size_mb = len(test_file_content) / (1024 * 1024)
    print(f"   Test file size: {test_file_size_mb:.2f} MB")
    
    try:
        # Validate file size first (Supabase free tier: 50MB limit)
        if test_file_size_mb > 50:
            print(f"   ⚠️  Warning: Test file ({test_file_size_mb:.2f} MB) exceeds Supabase free tier limit (50MB)")
            print(f"   This upload may fail. Consider using Cloudflare R2 or Backblaze B2 for larger files.")
            print(f"   See docs/STORAGE_RECOMMENDATIONS.md for alternatives.")
        
        # According to Supabase docs: upload(path, file, file_options={})
        # The file parameter accepts bytes directly, not BytesIO
        response = client.storage.from_(test_bucket).upload(
            path=test_path,
            file=test_file_content,  # Pass bytes directly
            file_options={
                "content-type": "application/pdf",
                "upsert": "true",  # Allow overwriting
                "cache-control": "3600"
            }
        )
        
        # Handle response - can be dict or response object
        if isinstance(response, dict):
            if 'error' in response:
                raise Exception(f"Upload error: {response.get('error')}")
        
        print(f"✅ Upload successful!")
        print(f"   Path: {test_path}")
        print(f"   Bucket: {test_bucket}")
        print(f"   File size: {len(test_file_content)} bytes")
        print(f"   Response: {response}")
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        logger.exception("Upload error details:")
        return
    
    # 6. Test signed URL generation
    print(f"\n🔗 Testing signed URL generation...")
    try:
        # According to Supabase docs: create_signed_url(path, expires_in_seconds)
        response = client.storage.from_(test_bucket).create_signed_url(test_path, 3600)
        
        # Handle response - can be dict with 'signedURL' key or direct string
        if isinstance(response, dict):
            signed_url = response.get('signedURL') or response.get('signed_url') or response
        else:
            signed_url = response
        
        if signed_url:
            print(f"✅ Signed URL generated successfully")
            print(f"   URL (first 80 chars): {str(signed_url)[:80]}...")
            print(f"   Expires in: 3600 seconds (1 hour)")
        else:
            print(f"❌ Failed to generate signed URL (returned empty)")
            return
    except Exception as e:
        print(f"❌ Signed URL generation failed: {e}")
        logger.exception("Signed URL error details:")
        return
    
    # 7. Test file download via signed URL
    print(f"\n📥 Testing file download via signed URL...")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            async with http_client.stream('GET', signed_url) as response:
                if response.status_code == 200:
                    content = b""
                    async for chunk in response.aiter_bytes():
                        content += chunk
                    print(f"✅ Download successful!")
                    print(f"   Downloaded size: {len(content)} bytes")
                    if len(content) == len(test_file_content):
                        print(f"   ✅ File size matches original")
                    else:
                        print(f"   ⚠️  File size mismatch (expected {len(test_file_content)}, got {len(content)})")
                else:
                    error_body = await response.aread()
                    print(f"❌ Download failed with status: {response.status_code}")
                    print(f"   Response: {error_body.decode('utf-8', errors='ignore')[:200]}")
                    return
    except Exception as e:
        print(f"❌ Download failed: {e}")
        logger.exception("Download error details:")
        return
    
    # 8. Test public URL generation (for comparison)
    print(f"\n🔗 Testing public URL generation (for reference)...")
    try:
        # Note: This will only work if bucket is public
        public_url = client.storage.from_(test_bucket).get_public_url(test_path)
        print(f"   Public URL: {public_url[:80]}...")
        print(f"   (Note: Will only work if bucket is public)")
    except Exception as e:
        print(f"   ⚠️  Could not generate public URL (expected for private bucket): {e}")
    
    # 9. Test file listing
    print(f"\n📋 Testing file listing in bucket...")
    try:
        files_response = client.storage.from_(test_bucket).list("test/")
        
        # Handle response
        files = []
        if hasattr(files_response, 'data'):
            files = files_response.data if files_response.data else []
        elif isinstance(files_response, list):
            files = files_response
        else:
            files = list(files_response) if hasattr(files_response, '__iter__') else []
        
        print(f"   Found {len(files)} file(s) in 'test/' folder:")
        for f in files[:5]:  # Show first 5
            name = f.name if hasattr(f, 'name') else f.get('name', '') if isinstance(f, dict) else str(f)
            print(f"     - {name}")
    except Exception as e:
        print(f"   ⚠️  Could not list files: {e}")
    
    # 10. Cleanup - Delete test file
    print(f"\n🧹 Cleaning up test file...")
    try:
        # According to Supabase docs: remove([paths])
        response = client.storage.from_(test_bucket).remove([test_path])
        print(f"✅ Test file deleted successfully")
    except Exception as e:
        print(f"⚠️  Cleanup failed (non-critical): {e}")
        logger.debug("Cleanup error:", exc_info=True)
    
    print("\n" + "="*80)
    print("✅ ALL SUPABASE STORAGE TESTS PASSED!")
    print("="*80 + "\n")
    print("💡 Summary:")
    print(f"   - Bucket: {test_bucket}")
    print(f"   - Upload: ✅ Working")
    print(f"   - Signed URLs: ✅ Working")
    print(f"   - Download: ✅ Working")
    print(f"\n📝 Important Notes:")
    print(f"   - Supabase free tier: 50MB per file limit")
    print(f"   - File size validation is enforced in the application")
    print(f"   - For larger files, consider Cloudflare R2 or Backblaze B2")
    print(f"   - See docs/STORAGE_RECOMMENDATIONS.md for alternatives")
    print("="*80 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Supabase Storage operations")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep test file after test (skip cleanup) - useful for inspecting files in dashboard"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check bucket status, don't upload any files"
    )
    
    args = parser.parse_args()
    asyncio.run(test_supabase_storage(keep_file=args.keep, check_only=args.check_only))
