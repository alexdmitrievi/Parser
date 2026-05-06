import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test 1: Module imports
from api.tenders import handler as HandlerClass, MODULES_OK
print("1. Handler class:", HandlerClass)
print("   MODULES_OK:", MODULES_OK)
print("   Has do_GET:", hasattr(HandlerClass, "do_GET"))

# Test 2: Shared imports
from shared.db import get_db, search_tenders, count_tenders, get_stats_via_rpc
print("2. DB imports OK")

# Test 3: Config
from shared.config import supabase_url, supabase_key
print("3. Config OK. URL:", supabase_url()[:30] if supabase_url() else "NOT SET")

# Test 4: Supabase connection
try:
    db = get_db()
    result = db.table("tenders").select("id", count="estimated").limit(1).execute()
    print("4. DB connection OK, count:", result.count)
except Exception as e:
    print("4. DB connection FAILED:", e)

# Test 5: Stats RPC
try:
    stats = get_stats_via_rpc()
    print("5. Stats RPC OK, total:", stats.get("total", "?"))
except Exception as e:
    print("5. Stats RPC FAILED:", e)

print("\nAll checks done.")
