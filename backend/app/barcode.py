import httpx

OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product"


async def lookup_barcode(code: str) -> dict | None:
    async with httpx.AsyncClient(timeout=6.0) as client:
        try:
            resp = await client.get(f"{OFF_PRODUCT_URL}/{code}.json")
        except httpx.HTTPError:
            return None

    if resp.status_code != 200:
        return None

    body = resp.json()
    if body.get("status") != 1:
        return None

    product = body.get("product", {})
    name = product.get("product_name") or "Unknown product"
    quantity = product.get("quantity") or ""

    return {
        "product_name": name,
        "summary_for_speech": f"{name}. {quantity}.",
    }
