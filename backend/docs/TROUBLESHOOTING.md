# Troubleshooting Guide

Common issues and solutions for Granthiq Backend.

## Deployment Issues

### DATABASE_URL not set

**Error:**
```
DATABASE_URL environment variable is not set!
```

**Solutions:**

1. **Railway**: Add variable in service settings
   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   ```
   Or manually set the full connection string.

2. **Check format**: Ensure URL uses correct format
   ```
   postgresql://user:pass@host:5432/dbname
   ```
   The app auto-converts to `postgresql+asyncpg://`

---

### Module not found errors

**Error:**
```
ModuleNotFoundError: No module named 'xxx'
```

**Solutions:**

1. Check `requirements-docker.txt` includes the package
2. Rebuild Docker image: `docker build --no-cache`
3. Verify package name matches import

---

### Pydantic validation errors

**Error:**
```
Field "model_name" has conflict with protected namespace "model_"
```

**Solution:** Already fixed in codebase. If you see this, ensure you have the latest code.

---

### HuggingFace cache errors

**Error:**
```
Cannot write to cache folder /home/appuser/.cache/huggingface
```

**Solution:** Already fixed in Dockerfile. Ensure `HF_HOME` is set to writable directory.

---

## Runtime Issues

### Health check failing

**Symptoms:** `/health` returns unhealthy status

**Debug steps:**

1. Check which service is failing:
   ```bash
   curl https://your-app.com/health | jq
   ```

2. **Database unhealthy:**
   - Verify `DATABASE_URL` is correct
   - Check database is accessible from Railway/Render
   - Ensure SSL settings match (`?ssl=require`)

3. **Qdrant unhealthy:**
   - Verify `QDRANT_HOST` and `QDRANT_API_KEY`
   - Check Qdrant cluster is running

4. **Storage unhealthy:**
   - Verify `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
   - Check buckets exist: `notebook-public`, `notebook-private`

---

### Document processing stuck

**Symptoms:** Documents stay in `PENDING` or `PROCESSING` status

**Solutions:**

1. **Check worker is running:**
   ```bash
   # In logs, look for:
   # "Starting embedded Procrastinate worker..."
   # "Embedded worker started"
   ```

2. **Check database connectivity** from worker

3. **Manual recovery:** Documents stuck > 1 hour are auto-marked `FAILED` on restart

4. **Check logs** for processing errors

---

### Chat returns empty or low-quality responses

**Possible causes:**

1. **No documents indexed:**
   - Verify documents are `COMPLETED` status
   - Check Qdrant has vectors: `/health` shows `vectors_count`

2. **Score threshold too high:**
   ```env
   POLICY__MIN_SCORE_THRESHOLD=0.10  # Lower = more permissive
   ```

3. **Retrieval issues:**
   - Ensure `COHERE_API_KEY` is set for reranking
   - Check `QDRANT_COLLECTION_NAME` matches indexed documents

---

### Rate limiting errors

**Error:**
```
429 Too Many Requests
```

**Solutions:**

1. Reduce request frequency
2. For development, disable rate limiting:
   ```env
   ENABLE_RATE_LIMITING=false
   ```

---

### CORS errors

**Error:**
```
Access-Control-Allow-Origin header missing
```

**Solution:** Add your frontend URL to CORS origins:
```env
CORS_ORIGINS=https://your-frontend.com,http://localhost:3000
```

---

## Database Issues

### Connection timeout

**Error:**
```
asyncpg.exceptions.ConnectionDoesNotExistError
```

**Solutions:**

1. Check database is running
2. Verify connection string format
3. Check firewall/network access
4. For Supabase, use port `5432` (not `6543`)

---

### SSL connection errors

**Error:**
```
SSL connection required
```

**Solution:** Add `?ssl=require` to DATABASE_URL:
```
postgresql://user:pass@host:5432/db?ssl=require
```

---

## LLM Issues

### API key errors

**Error:**
```
Invalid API key
```

**Solutions:**

1. Verify key is correct (no extra spaces)
2. Check key has required permissions
3. Verify billing is enabled for the provider

---

### Rate limits from LLM provider

**Error:**
```
Rate limit exceeded
```

**Solutions:**

1. Use a provider with higher limits (Gemini recommended)
2. Implement request caching
3. Reduce concurrent requests

---

## Performance Issues

### Slow document processing

**Possible causes:**

1. Large documents taking time to parse
2. Embedding generation is CPU-intensive
3. Network latency to Qdrant

**Solutions:**

1. Check document size limits
2. Consider using smaller embedding model
3. Use Qdrant Cloud in same region as deployment

---

### High memory usage

**Solutions:**

1. Reduce worker concurrency:
   ```python
   # In queue config
   workers_critical: int = 1
   workers_high: int = 1
   workers_standard: int = 1
   ```

2. Process smaller batches
3. Increase container memory limit

---

## Debugging Tips

### Enable debug logging

```env
DEBUG=true
```

### Check application logs

**Railway:**
```
Dashboard → Deployments → View Logs
```

**Docker:**
```bash
docker logs -f container_name
```

### Test endpoints manually

```bash
# Health check
curl https://your-app.com/health

# With auth
curl -H "Authorization: Bearer $TOKEN" \
  https://your-app.com/api/v1/notebooks
```

### Verify configuration

```bash
python -c "from src.config import get_settings; s = get_settings(); print(f'DB: {s.database.url[:30]}...')"
```

---

## Getting Help

1. Check this troubleshooting guide
2. Review logs for error messages
3. Search existing issues
4. Open new issue with:
   - Error message
   - Steps to reproduce
   - Environment (Railway, Docker, etc.)
   - Relevant configuration (without secrets)
