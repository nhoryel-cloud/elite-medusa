#!/usr/bin/env python3
"""
One-off migration: Payload Commerce products (prod, READ-ONLY) -> local Medusa.

Source schema (Payload, custom):
- product: title, slug, _status, priceInUSD (minor units), originalPrice,
  inventory, gallery[].image.url (Bunny CDN), categories[], description (lexical richText),
  variantTypes[] ({id,label} + options.docs[{id,label,value,variantType}]),
  variants.docs[] ({title, options[{variantType,label,value}], priceInUSD, inventory})
Target (Medusa 2.21 Admin API):
- product categories, products with options/variants/prices(usd)/images(url)
"""
import json
import re
import sys
import urllib.request
import urllib.error

PAYLOAD = "https://6bwtywykbkuqa9pgor5wfwr5.198.211.99.38.sslip.io/api"
MEDUSA = "http://localhost:9000"
EMAIL = "john@widsix.com"
PASSWORD = "daab8475025284ed44babfd7"
SALES_CHANNEL = "sc_01M3Z7ZW9Z9095DXJGQ84GW71N"
OUT_MAP = "scripts/payload-to-medusa-map.json"


def http(url, method="GET", token=None, body=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:400]}")


def plaintext(node):
    if isinstance(node, dict):
        parts = [node.get("text") or ""]
        kids = node.get("children") or []
        parts.append("".join(plaintext(c) for c in kids))
        if node.get("type") in ("paragraph", "heading", "listitem", "blockquote"):
            parts.append("\n")
        return "".join(parts)
    if isinstance(node, list):
        return "".join(plaintext(c) for c in node)
    return str(node) if node is not None else ""


def clean_text(s):
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def main():
    # 1. login to medusa admin
    login = http(f"{MEDUSA}/auth/user/emailpass", "POST",
                 body={"email": EMAIL, "password": PASSWORD})
    token = login["token"]

    # 2. clear demo products locally
    existing = http(f"{MEDUSA}/admin/products?limit=100", "GET", token)
    for p in existing.get("products", []):
        http(f"{MEDUSA}/admin/products/{p['id']}", "DELETE", token)
        print(f"deleted demo product {p['id']}")
    # clear demo categories (local clean slate; only seeded ones)
    cats = http(f"{MEDUSA}/admin/product-categories?limit=100", "GET", token)
    for c in cats.get("product_categories", []):
        try:
            http(f"{MEDUSA}/admin/product-categories/{c['id']}", "DELETE", token)
            print(f"deleted existing category {c['name']}")
        except RuntimeError as e:
            print(f"keep category {c['name']}: {e}")

    # 3. payload categories -> medusa product categories
    pcats = http(f"{PAYLOAD}/categories?limit=100&depth=0", "GET")["docs"]
    cat_map = {}  # payload cat id -> medusa cat id
    for c in pcats:
        created = http(f"{MEDUSA}/admin/product-categories", "POST", token,
                       body={"name": c["title"],
                             "handle": c.get("slug") or re.sub(r"[^a-z0-9]+", "-", c["title"].lower()).strip("-"),
                             "is_active": True})
        cat_map[c["id"]] = created["product_category"]["id"]
        print(f"category: {c['title']} -> {created['product_category']['id']}")

    # 4. payload products -> medusa products
    prods = http(f"{PAYLOAD}/products?limit=200&depth=2", "GET")["docs"]
    print(f"importing {len(prods)} products")
    mapping = {}
    ok = fail = 0
    for p in prods:
        desc = clean_text(plaintext(p.get("description")))
        if not desc:
            desc = p["title"]
        images = []
        for g in p.get("gallery") or []:
            img = g.get("image") or {}
            url = img.get("url")
            if url:
                images.append({"url": url, "alt": img.get("alt")})
        # options from variantTypes
        option_groups = []
        for vt in p.get("variantTypes") or []:
            vals = [o["label"] for o in (vt.get("options") or {}).get("docs", [])]
            option_groups.append({"title": vt["label"], "values": vals})
        variants_docs = (p.get("variants") or {}).get("docs") or []
        # ensure every option value referenced by a variant exists in its group
        for vd in variants_docs:
            for o in vd.get("options") or []:
                label = o.get("label")
                for vt in p.get("variantTypes") or []:
                    if vt["id"] == o.get("variantType"):
                        for g in option_groups:
                            if g["title"] == vt["label"] and label not in g["values"]:
                                g["values"].append(label)
        variants = []
        if variants_docs:
            for vd in variants_docs:
                vopts = {}
                for vt in p.get("variantTypes") or []:
                    for o in vd.get("options") or []:
                        if o.get("variantType") == vt["id"]:
                            vopts[vt["label"]] = o.get("label")
                amount = vd.get("priceInUSD")
                if amount is None:
                    amount = p.get("priceInUSD") or p.get("originalPrice") or 0
                variants.append({
                    "title": vd.get("title") or p["title"],
                    "prices": [{"amount": int(amount), "currency_code": "usd"}],
                    "manage_inventory": False,
                    "metadata": {"payload_inventory": int(vd.get("inventory") or 0)},
                    "options": vopts,
                })
        else:
            amount = p.get("priceInUSD")
            if amount is None:
                amount = p.get("originalPrice") or 0
            option_groups = [{"title": "Size", "values": ["Default"]}]
            variants.append({
                "title": "Default",
                "prices": [{"amount": int(amount), "currency_code": "usd"}],
                "manage_inventory": False,
                "metadata": {"payload_inventory": int(p.get("inventory") or 0)},
                "options": {"Size": "Default"},
            })
        # ensure every option group has a matching variant option value or drop group
        used_groups = []
        for g in option_groups:
            if any(g["title"] in v["options"] for v in variants):
                used_groups.append(g)
        body = {
            "title": p["title"],
            "handle": p.get("slug") or re.sub(r"[^a-z0-9]+", "-", p["title"].lower()).strip("-"),
            "description": desc[:100000],
            "status": "published" if p.get("_status") == "published" else "draft",
            "options": used_groups,
            "variants": variants,
            "images": images,
            "thumbnail": images[0]["url"] if images else None,
            "sales_channels": [{"id": SALES_CHANNEL}],
        }
        if p.get("categories"):
            body["categories"] = [{"id": cat_map[c["id"]]}
                                  for c in p["categories"] if c["id"] in cat_map]
        try:
            created = http(f"{MEDUSA}/admin/products", "POST", token, body=body)
            mid = created["product"]["id"]
            mapping[str(p["id"])] = {
                "payload_id": p["id"],
                "payload_slug": p.get("slug"),
                "medusa_id": mid,
                "medusa_handle": created["product"].get("handle"),
            }
            ok += 1
            print(f"ok  {p['title']!r} -> {mid}")
        except RuntimeError as e:
            fail += 1
            print(f"FAIL {p['title']!r}: {e}")
            with open(OUT_MAP + ".errors", "a") as f:
                f.write(json.dumps({"title": p["title"], "payload_id": p["id"], "error": str(e)[:500]}) + "\n")

    with open(OUT_MAP, "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"\nDONE: ok={ok} fail={fail} total={len(prods)}. Map written to {OUT_MAP}")


if __name__ == "__main__":
    main()
