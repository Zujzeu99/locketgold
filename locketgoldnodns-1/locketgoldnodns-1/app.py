import re
import json
import time
import uuid
import requests
from urllib.parse import unquote
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pathlib import Path

app = Flask(__name__)
CORS(app)

# ==================== CONFIG ====================
RC_KEY = "appl_JngFETzdodyLmCREOlwTUtXdQik"

HEADERS = {
    "Authorization": f"Bearer {RC_KEY}",
    "Content-Type": "application/json",
    "X-Platform": "ios",
}

# Proxy pool file - luu trang thai cac anonymous proxy
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PROXY_FILE = DATA_DIR / "proxy_pool.json"

current_master = {
    "uid": None,
    "username": None,
    "gold_info": None,
}


# ==================== PROXY POOL MANAGEMENT ====================

def load_proxy_pool():
    """Load proxy pool from file"""
    if PROXY_FILE.exists():
        with open(PROXY_FILE, "r") as f:
            return json.load(f)
    return {"proxies": [], "stats": {"total_customers": 0}}


def save_proxy_pool(pool):
    """Save proxy pool to file"""
    with open(PROXY_FILE, "w") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)


def get_available_proxy(pool, master_uid):
    """Get or create an available proxy (anonymous ID) with free slots"""
    # Find existing proxy with free slots for this master
    for proxy in pool["proxies"]:
        if proxy["master_uid"] == master_uid and proxy["customer_count"] < 50:
            return proxy

    # All proxies full or none exist — create new one
    if len([p for p in pool["proxies"] if p["master_uid"] == master_uid]) >= 50:
        return None  # Master itself is full (50 proxies × 50 = 2500 max)

    anon_id = f"$RCAnonymousID:{uuid.uuid4().hex[:32]}"

    # Alias anon into master
    alias_result = alias_to_target(master_uid, anon_id)
    if not alias_result.get("success"):
        return None

    new_proxy = {
        "anon_id": anon_id,
        "master_uid": master_uid,
        "customer_count": 0,
        "customers": [],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    pool["proxies"].append(new_proxy)
    save_proxy_pool(pool)
    return new_proxy


# ==================== CORE FUNCTIONS ====================

def resolve_username(username):
    """Convert username to Firebase UID"""
    username = username.strip().lstrip("@").strip()
    if len(username) == 28 and re.match(r"^[a-zA-Z0-9_-]+$", username):
        return {"uid": username, "method": "direct_uid"}

    url = f"https://locket.cam/{username}"
    h = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"}
    try:
        resp = requests.get(url, headers=h, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return {"error": f"Không tìm thấy profile @{username} (HTTP {resp.status_code})"}

        html = unquote(resp.text)
        m = re.search(r'invites[/%2F]([a-zA-Z0-9_-]{28})', html)
        if not m:
            m = re.search(r'users[/%2F]([a-zA-Z0-9_-]{20,40})[/%2F]public', html)
        if m:
            return {"uid": m.group(1), "method": "scraped"}
        return {"error": f"Không trích xuất được UID từ profile @{username}"}
    except requests.exceptions.Timeout:
        return {"error": "Hết thời gian kết nối đến locket.cam"}
    except Exception as e:
        return {"error": f"Lỗi kết nối: {str(e)}"}


def check_gold_status(uid):
    """Check if a UID has Gold entitlement"""
    try:
        resp = requests.get(
            f"https://api.revenuecat.com/v1/subscribers/{uid}",
            headers=HEADERS, timeout=10
        )
        if resp.status_code != 200:
            return {"has_gold": False, "error": f"RevenueCat HTTP {resp.status_code}"}

        data = resp.json()
        subscriber = data.get("subscriber", {})
        gold = subscriber.get("entitlements", {}).get("Gold")

        if gold:
            expires = gold.get("expires_date")
            from datetime import datetime
            if expires:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                now = datetime.now(exp_dt.tzinfo)
                days_left = max(0, (exp_dt - now).days)
                is_active = exp_dt > now
            else:
                days_left = 0
                is_active = False

            return {
                "has_gold": True,
                "is_active": is_active,
                "expires_date": expires,
                "days_left": days_left,
                "product": gold.get("product_identifier", "N/A"),
                "purchase_date": gold.get("purchase_date"),
                "store": gold.get("store", "app_store"),
            }
        else:
            return {"has_gold": False, "is_active": False}

    except Exception as e:
        return {"has_gold": False, "error": str(e)}


def alias_to_target(target_uid, new_uid):
    """Create alias: new_uid -> target_uid"""
    payload = {"new_app_user_id": new_uid}
    try:
        resp = requests.post(
            f"https://api.revenuecat.com/v1/subscribers/{target_uid}/alias",
            headers=HEADERS, json=payload, timeout=10
        )
        body = {}
        if resp.headers.get("content-type", "").startswith("application/json"):
            body = resp.json()

        if resp.status_code >= 200 and resp.status_code < 300:
            return {"success": True, "status_code": resp.status_code}
        else:
            msg = body.get("message", "Unknown error")
            is_limit = "limit" in msg.lower() or "7255" in str(body)
            return {
                "success": False,
                "status_code": resp.status_code,
                "message": msg,
                "is_alias_limit": is_limit
            }
    except Exception as e:
        return {"success": False, "message": str(e)}


def unlock_via_proxy_chain(master_uid, customer_uid):
    """
    Proxy Chain Method: Master -> Anonymous Proxy -> Customer
    Bypasses 50 alias limit: 50 proxies x 50 customers = 2500 max
    """
    pool = load_proxy_pool()

    # Get available proxy
    proxy = get_available_proxy(pool, master_uid)
    if not proxy:
        return {
            "success": False,
            "error": "Tất cả proxy đã đầy (2500 slots). Cần Master mới!",
            "method": "proxy_chain"
        }

    # Alias customer into the proxy (NOT directly into master)
    alias_result = alias_to_target(proxy["anon_id"], customer_uid)

    if not alias_result.get("success"):
        if alias_result.get("is_alias_limit"):
            # This proxy is full, mark it and try next
            proxy["customer_count"] = 50
            save_proxy_pool(pool)
            # Retry with a new proxy
            proxy2 = get_available_proxy(pool, master_uid)
            if not proxy2:
                return {"success": False, "error": "Hết proxy slot!", "method": "proxy_chain"}
            alias_result2 = alias_to_target(proxy2["anon_id"], customer_uid)
            if not alias_result2.get("success"):
                return {"success": False, "error": alias_result2.get("message", "Lỗi"), "method": "proxy_chain"}
            proxy2["customer_count"] += 1
            proxy2["customers"].append(customer_uid)
        else:
            return {"success": False, "error": alias_result.get("message", "Lỗi"), "method": "proxy_chain"}
    else:
        proxy["customer_count"] += 1
        proxy["customers"].append(customer_uid)

    pool["stats"]["total_customers"] += 1
    save_proxy_pool(pool)

    return {
        "success": True,
        "method": "proxy_chain",
        "proxy_id": proxy["anon_id"][:20] + "...",
        "proxy_slot": f"{proxy['customer_count']}/50",
        "total_proxies": len([p for p in pool["proxies"] if p["master_uid"] == master_uid]),
        "total_customers": pool["stats"]["total_customers"],
    }


def unlock_via_direct_alias(master_uid, customer_uid):
    """Direct alias: Customer -> Master (original method, max 50)"""
    return alias_to_target(master_uid, customer_uid)


# ==================== API ROUTES ====================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/check-master", methods=["POST"])
def api_check_master():
    """Check master account Gold status"""
    data = request.get_json()
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"success": False, "error": "Vui lòng nhập username Master"}), 400

    result = resolve_username(username)
    if "error" in result:
        return jsonify({"success": False, "error": result["error"]}), 400

    uid = result["uid"]
    gold_status = check_gold_status(uid)
    if not gold_status.get("has_gold") or not gold_status.get("is_active"):
        return jsonify({
            "success": False,
            "error": f"Master @{username} KHÔNG có Gold hoặc Gold đã hết hạn!",
            "uid": uid,
            "gold_status": gold_status
        }), 400

    # Load proxy pool stats
    pool = load_proxy_pool()
    master_proxies = [p for p in pool["proxies"] if p.get("master_uid") == uid]
    total_proxy_customers = sum(p["customer_count"] for p in master_proxies)

    current_master["uid"] = uid
    current_master["username"] = username
    current_master["gold_info"] = gold_status

    return jsonify({
        "success": True,
        "username": username,
        "uid": uid,
        "gold": gold_status,
        "proxy_stats": {
            "total_proxies": len(master_proxies),
            "total_customers": total_proxy_customers,
            "max_capacity": 2500,
            "available": 2500 - total_proxy_customers,
        }
    })


@app.route("/api/check-user", methods=["POST"])
def api_check_user():
    """Check customer account status"""
    data = request.get_json()
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"success": False, "error": "Vui lòng nhập username"}), 400

    result = resolve_username(username)
    if "error" in result:
        return jsonify({"success": False, "error": result["error"]}), 400

    uid = result["uid"]
    gold_status = check_gold_status(uid)

    return jsonify({
        "success": True,
        "username": username,
        "uid": uid,
        "gold": gold_status,
        "already_has_gold": gold_status.get("has_gold", False) and gold_status.get("is_active", False)
    })


@app.route("/api/unlock", methods=["POST"])
def api_unlock():
    """Unlock Gold for customer via proxy chain alias"""
    data = request.get_json()
    customer_username = data.get("customer_username", "").strip()
    master_uid = data.get("master_uid", "").strip() or current_master.get("uid")
    method = data.get("method", "proxy_chain")  # proxy_chain or direct

    if not master_uid:
        return jsonify({"success": False, "error": "Chưa thiết lập Master!"}), 400
    if not customer_username:
        return jsonify({"success": False, "error": "Vui lòng nhập username cần nâng Gold"}), 400

    # Resolve customer
    result = resolve_username(customer_username)
    if "error" in result:
        return jsonify({"success": False, "error": result["error"]}), 400
    customer_uid = result["uid"]

    # Pre-check
    pre_check = check_gold_status(customer_uid)
    if pre_check.get("has_gold") and pre_check.get("is_active"):
        return jsonify({
            "success": True,
            "already_had_gold": True,
            "message": f"@{customer_username} đã có Gold rồi!",
            "gold": pre_check
        })

    # Unlock via chosen method
    if method == "direct":
        unlock_result = unlock_via_direct_alias(master_uid, customer_uid)
        if not unlock_result.get("success"):
            error_msg = unlock_result.get("message", "Lỗi không xác định")
            if unlock_result.get("is_alias_limit"):
                error_msg = "Master đã hết 50 alias trực tiếp! Chuyển sang Proxy Chain."
            return jsonify({"success": False, "error": error_msg}), 400
    else:
        # Proxy Chain (default)
        unlock_result = unlock_via_proxy_chain(master_uid, customer_uid)
        if not unlock_result.get("success"):
            return jsonify({"success": False, "error": unlock_result.get("error", "Lỗi")}), 400

    # Wait & verify
    time.sleep(2)
    verify1 = check_gold_status(customer_uid)

    if verify1.get("has_gold") and verify1.get("is_active"):
        return jsonify({
            "success": True,
            "message": f"Nâng Gold thành công cho @{customer_username}!",
            "gold": verify1,
            "method": method,
            "unlock_info": unlock_result if method == "proxy_chain" else None,
            "attempt": 1
        })

    # Retry
    time.sleep(3)
    verify2 = check_gold_status(customer_uid)

    if verify2.get("has_gold") and verify2.get("is_active"):
        return jsonify({
            "success": True,
            "message": f"Nâng Gold thành công cho @{customer_username}! (lần 2)",
            "gold": verify2,
            "method": method,
            "unlock_info": unlock_result if method == "proxy_chain" else None,
            "attempt": 2
        })

    return jsonify({
        "success": False,
        "error": "Alias OK nhưng Gold chưa xuất hiện. Yêu cầu khách nhấn 'Khôi phục gói đăng ký'.",
        "gold": verify2
    }), 500


@app.route("/api/proxy-stats", methods=["GET"])
def api_proxy_stats():
    """Get proxy chain statistics"""
    pool = load_proxy_pool()
    master_uid = current_master.get("uid")

    if not master_uid:
        return jsonify({"success": False, "error": "Chưa thiết lập Master"})

    master_proxies = [p for p in pool["proxies"] if p.get("master_uid") == master_uid]
    total_customers = sum(p["customer_count"] for p in master_proxies)

    return jsonify({
        "success": True,
        "master_uid": master_uid,
        "total_proxies": len(master_proxies),
        "total_customers": total_customers,
        "max_capacity": 2500,
        "available": 2500 - total_customers,
        "proxies": [{
            "id": p["anon_id"][:20] + "...",
            "customers": p["customer_count"],
            "created": p.get("created_at", "N/A")
        } for p in master_proxies]
    })


@app.route("/api/master-info", methods=["GET"])
def api_master_info():
    """Get current master info"""
    if not current_master.get("uid"):
        return jsonify({"success": False, "error": "Chưa thiết lập Master"})
    return jsonify({"success": True, "master": current_master})


# ==================== MAIN ====================
if __name__ == "__main__":
    print("=" * 50)
    print("  LOCKET GOLD UNLOCKER — Web App v2")
    print("  Proxy Chain Method: 2500 slots/master")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5000)
