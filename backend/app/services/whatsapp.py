import os
import time
import base64
import asyncio
import logging
import platform
import psutil
import tempfile
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException
from urllib.parse import quote
from typing import Optional, Dict, List, Any, Union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import set_qr_code, delete_qr_code, get_qr_code, reset_auth_status
from app.models.whatsapp import WhatsAppAccount, WhatsAppAccountStatus, WhatsAppMessage, WhatsAppMessageStatus
from app.utils.session_cache import SessionCacheManager
from app.schemas.whatsapp import WhatsAppMessageRecipient, WhatsAppMessageHistory

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self, db: AsyncSession):
        self.db = db
        
        # Hardcoded Chrome profiles directory path
        self.base_profile_dir = "/root/chrome-profiles"
        logger.info(f"Using Chrome profiles directory: {self.base_profile_dir}")
        
        # Create directory if it doesn't exist
        if not os.path.exists(self.base_profile_dir):
            os.makedirs(self.base_profile_dir, exist_ok=True)
            logger.info(f"Created Chrome profiles directory: {self.base_profile_dir}")
            
        # Timing settings
        self.qr_check_interval = 1
        self.qr_max_wait = 60
        
        # Browser pool lock and storage
        self._browser_pool_lock = asyncio.Lock()
        self._browser_pool = {}
    
    def _get_profile_path(self, profile_name: str) -> str:
        """Returns the path to a Chrome profile"""
        # Remove invalid characters from the profile name
        safe_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in profile_name)
        profile_path = os.path.join(self.base_profile_dir, f"profile-{safe_name}")
        logger.info(f"Profile path for {profile_name}: {profile_path}")
        return profile_path
    
    async def _cleanup_chrome_processes(self):
        """Cleans up hanging Chrome processes"""
        try:
            logger.info("Starting Chrome processes cleanup")
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    proc_name = proc.info['name'].lower()
                    # Check process name depending on OS
                    is_chrome = False
                    if platform.system() == "Windows":
                        is_chrome = proc_name == 'chrome.exe'
                    else:
                        is_chrome = proc_name in ['chrome', 'chromium', 'chromium-browser']
                    
                    if is_chrome and proc.info['cmdline']:
                        cmdline = ' '.join(proc.info['cmdline'])
                        if self.base_profile_dir in cmdline:
                            logger.info(f"Terminating Chrome process: {proc.pid}")
                            proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            logger.info("Chrome processes cleanup completed")
        except Exception as e:
            logger.error(f"Error cleaning up Chrome processes: {str(e)}")
    
    async def _init_chrome(self, profile_path: str) -> webdriver.Chrome:
        """Initializes Chrome with optimal settings using standard Selenium"""
        loop = asyncio.get_event_loop()
        max_attempts = 3
        
        # Ensure the profile directory exists
        os.makedirs(profile_path, exist_ok=True)
        logger.info(f"Ensuring profile directory exists: {profile_path}")
        
        for attempt in range(max_attempts):
            try:
                # Create driver in a separate function to execute it in another thread
                def create_driver():
                    options = Options()
                    
                    # Basic launch parameters
                    options.add_argument('--no-sandbox')
                    options.add_argument(f'--user-data-dir={profile_path}')
                    options.add_argument('--start-maximized')
                    options.add_argument('--window-position=0,0')
                    
                    # Disable unnecessary features
                    options.add_argument('--disable-dev-shm-usage')
                    options.add_argument('--disable-extensions')
                    options.add_argument('--disable-background-mode')
                    options.add_argument('--disable-popup-blocking')
                    options.add_argument('--disable-notifications')
                    options.add_argument('--disable-infobars')
                    options.add_argument('--disable-gpu')  # Important for Linux VPS
                    
                    # Important parameters for WhatsApp Web
                    options.add_argument('--enable-features=NetworkServiceInProcess')
                    options.add_argument('--disable-site-isolation-trials')
                    options.add_experimental_option('excludeSwitches', ['enable-automation'])
                    options.add_experimental_option('useAutomationExtension', False)
                    
                    # Custom user agent for better compatibility
                    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36')
                    
                    # Performance optimizations
                    options.add_argument('--autoplay-policy=no-user-gesture-required')
                    options.add_argument('--disable-background-networking')
                    options.add_argument('--disable-background-timer-throttling')
                    options.add_argument('--disable-client-side-phishing-detection')
                    options.add_argument('--disable-component-update')
                    options.add_argument('--no-first-run')
                    options.add_argument('--no-default-browser-check')
                    
                    # Choose a random debug port
                    import random
                    debug_port = random.randint(9222, 9999)
                    options.add_argument(f'--remote-debugging-port={debug_port}')
                    
                    # Headless mode
                    options.add_argument('--headless=new')  # Use new headless mode
                    
                    try:
                        logger.info(f"Creating Chrome driver with user data dir: {profile_path}")
                        service = Service()
                        driver = webdriver.Chrome(service=service, options=options)
                        logger.info("Chrome driver created successfully")
                        return driver
                    except Exception as e:
                        logger.error(f"Chrome initialization error: {str(e)}")
                        raise

                # Launch driver creation in a separate thread
                logger.info(f"Attempt {attempt+1}/{max_attempts} to initialize Chrome")
                driver = await loop.run_in_executor(None, create_driver)
                
                # Set reasonable timeouts
                driver.implicitly_wait(10)
                driver.set_page_load_timeout(30)
                
                # Test the browser by loading a simple page
                try:
                    logger.info("Testing browser with a simple navigation")
                    driver.get("about:blank")
                    logger.info("Browser test successful")
                except Exception as e:
                    logger.error(f"Browser test failed: {str(e)}")
                    raise
                
                return driver
                
            except Exception as e:
                logger.error(f"Failed to initialize Chrome (attempt {attempt+1}/{max_attempts}): {str(e)}")
                
                # If this is the last attempt, raise exception
                if attempt == max_attempts - 1:
                    raise
                
                # Otherwise clean up processes and try again
                await self._cleanup_chrome_processes()
                await asyncio.sleep(5)
    
    async def get_account(self, account_id: str) -> Optional[WhatsAppAccount]:
        """Get a WhatsApp account by ID"""
        result = await self.db.execute(
            select(WhatsAppAccount).where(WhatsAppAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def initialize_session(
        self, account: WhatsAppAccount, wait_time: int = 60
    ) -> Dict:
        """Initialize a WhatsApp session and return QR code for scanning"""
        result = {
            "success": False,
            "account_id": account.id,
            "status": account.status,
            "error": None,
            "qr_code": None
        }

        # Create profile path
        profile_path = self._get_profile_path(account.profile_name)
        account.profile_path = profile_path
        await self.db.commit()
        
        # Reset authentication status in Redis (delete QR code and auth marker)
        await reset_auth_status(account.id)
        
        driver = None
        try:
            # Check if we need to create a new profile
            new_profile = False
            if account.status not in [WhatsAppAccountStatus.ACTIVE, WhatsAppAccountStatus.INITIALIZED]:
                if os.path.exists(profile_path):
                    logger.info(f"Cleaning existing profile at {profile_path}")
                    import shutil
                    try:
                        shutil.rmtree(profile_path)
                        new_profile = True
                        logger.info(f"Successfully removed profile directory: {profile_path}")
                    except Exception as e:
                        logger.warning(f"Failed to clean profile directory: {str(e)}")
                else:
                    new_profile = True
                
                if new_profile:
                    os.makedirs(profile_path, exist_ok=True)
                    logger.info(f"Created profile directory: {profile_path}")
            
            # Initialize Chrome
            logger.info(f"Initializing Chrome for account {account.id}")
            driver = await self._init_chrome(profile_path)
            
            # Open WhatsApp Web
            logger.info("Opening WhatsApp Web")
            driver.get("https://web.whatsapp.com/")
            await asyncio.sleep(3)  # Give the page some time to load
            
            # Set timers
            start_time = time.time()
            qr_found = False
            qr_disappeared = False
            authenticated = False
            
            # Update account status
            account.status = WhatsAppAccountStatus.PENDING
            await self.db.commit()
            
            # Take screenshot of initial state
            try:
                screenshot_path = os.path.join(profile_path, f"init_screenshot_{int(time.time())}.png")
                driver.save_screenshot(screenshot_path)
                logger.info(f"Init screenshot saved to {screenshot_path}")
            except Exception as e:
                logger.warning(f"Failed to save init screenshot: {str(e)}")
            
            # Main checking loop
            logger.info(f"Starting authentication check loop for account {account.id}")
            while time.time() - start_time < wait_time:
                try:
                    # Check for QR code
                    qr_elements = driver.find_elements(By.TAG_NAME, "canvas")
                    
                    # If QR code is found and not saved yet
                    if qr_elements and not qr_found:
                        logger.info(f"QR code element found for account {account.id}")
                        # Extract QR code as Base64 image
                        qr_base64 = driver.execute_script("""
                            const canvas = document.querySelector('canvas');
                            if (!canvas || canvas.width === 0 || canvas.height === 0) {
                                return null;
                            }
                            try {
                                return canvas.toDataURL('image/png').substring(22);
                            } catch (e) {
                                console.error('Error getting QR:', e);
                                return null;
                            }
                        """)
                        
                        if qr_base64:
                            # Save QR code to Redis
                            await set_qr_code(account.id, qr_base64, expire=120)
                            
                            # Check that QR code was saved correctly
                            saved_qr = await get_qr_code(account.id)
                            if saved_qr:
                                result["qr_code"] = qr_base64
                                qr_found = True
                                logger.info(f"QR code generated for account {account.id}")
                    
                    # Key check: QR code was present but disappeared
                    if qr_found and not qr_elements:
                        logger.info(f"QR code disappeared for account {account.id} - checking for authenticated state")
                        qr_disappeared = True
                        
                        # Give a small pause for UI loading
                        await asyncio.sleep(2)
                    
                    # Check for WhatsApp interface elements
                    if qr_disappeared or (not qr_elements and not new_profile):
                        # Take screenshot for verification
                        try:
                            screenshot_path = os.path.join(profile_path, f"auth_screenshot_{int(time.time())}.png")
                            driver.save_screenshot(screenshot_path)
                            logger.info(f"Auth screenshot saved to {screenshot_path}")
                        except Exception as e:
                            logger.warning(f"Failed to save auth screenshot: {str(e)}")
                        
                        # Check for UI elements - any of these selectors should exist
                        ui_selectors = [
                            "#app", "#main", ".app", ".two", "[data-testid='conversation-panel']",
                            "[data-testid='chat-list']", "[data-testid='default-user']", "[data-icon='default-user']",
                            "pane-side"
                        ]
                        
                        for selector in ui_selectors:
                            try:
                                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                if elements:
                                    logger.info(f"Found UI element: {selector}")
                                    authenticated = True
                                    break
                            except:
                                pass
                    
                    # If user is authenticated
                    if authenticated or qr_disappeared:
                        logger.info(f"WhatsApp account {account.id} authenticated")
                        
                        # Delete QR code from Redis
                        await delete_qr_code(account.id)
                        
                        # Update account status
                        account.status = WhatsAppAccountStatus.ACTIVE
                        if not account.account_metadata:
                            account.account_metadata = {}
                        account.account_metadata["last_active"] = datetime.now().isoformat()
                        await self.db.commit()
                        
                        # Set flag for frontend to close modal window
                        result["success"] = True
                        result["status"] = WhatsAppAccountStatus.ACTIVE
                        result["authenticated"] = True  # Explicit flag for frontend
                        
                        # To fix issues with "hanging" browsers,
                        # forcibly close the browser after successful authentication
                        try:
                            driver.quit()
                            logger.info(f"Browser closed after successful authentication for account {account.id}")
                        except Exception as e:
                            logger.warning(f"Error closing browser: {str(e)}")
                        
                        # Reset browser cache
                        async with self._browser_pool_lock:
                            if profile_path in self._browser_pool:
                                del self._browser_pool[profile_path]
                        
                        return result
                
                except Exception as e:
                    logger.debug(f"Error during initialization check: {str(e)}")
                
                # Small pause before next check
                await asyncio.sleep(1)
            
            # If wait time expired
            if not result["success"]:
                logger.warning(f"Session initialization timeout for account {account.id}")
                if qr_found:
                    result["error"] = "QR code was not scanned in time"
                else:
                    result["error"] = "Failed to generate QR code"
                
                # If QR code was found, leave status as PENDING
                # Otherwise set status to ERROR
                if not qr_found:
                    account.status = WhatsAppAccountStatus.ERROR
                    account.set_error(result["error"])
                    await self.db.commit()
            
        except Exception as e:
            logger.error(f"Session initialization error: {str(e)}")
            result["error"] = f"Session initialization failed: {str(e)}"
            account.status = WhatsAppAccountStatus.ERROR
            if not account.account_metadata:
                account.account_metadata = {}
            account.account_metadata["last_error"] = str(e)
            account.account_metadata["last_error_at"] = datetime.now().isoformat()
            await self.db.commit()
            
        finally:
            # If we're not authenticated, close the browser to save resources
            if driver and not result.get("authenticated", False):
                try:
                    driver.quit()
                except Exception as e:
                    logger.warning(f"Error closing driver: {str(e)}")
        
        return result

    async def _get_or_create_browser(self, profile_path: str) -> webdriver.Chrome:
        """Get an existing browser from the pool or create a new one"""
        async with self._browser_pool_lock:
            if profile_path in self._browser_pool:
                browser = self._browser_pool[profile_path]
                try:
                    # Check that the browser is alive
                    browser.current_url
                    logger.info(f"Reusing existing browser for profile: {profile_path}")
                    return browser
                except Exception as e:
                    logger.warning(f"Browser from pool is dead, creating new one: {str(e)}")
                    # Browser is dead, remove from pool
                    try:
                        browser.quit()
                    except:
                        pass
                    del self._browser_pool[profile_path]
            
            # Create a new browser
            logger.info(f"Creating new browser for profile: {profile_path}")
            browser = await self._init_chrome(profile_path)
            self._browser_pool[profile_path] = browser
            return browser

    async def create_message_history(
        self,
        account: WhatsAppAccount,
        recipient: WhatsAppMessageRecipient,
        status: WhatsAppMessageStatus = WhatsAppMessageStatus.PENDING
    ) -> WhatsAppMessage:
        """Create a record in message history"""
        message = WhatsAppMessage(
            account_id=account.id,
            recipient=recipient.phone,
            message_text=recipient.message,
            status=status
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_message_history(
        self,
        account_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[WhatsAppMessage]:
        """Get message history"""
        result = await self.db.execute(
            select(WhatsAppMessage)
            .where(WhatsAppMessage.account_id == account_id)
            .order_by(WhatsAppMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def send_message(
        self,
        account: WhatsAppAccount,
        recipient: WhatsAppMessageRecipient,
        message_id: Optional[str] = None,
        wait_time: int = 60,
        existing_driver: Optional[webdriver.Chrome] = None,
        close_driver: bool = True
    ) -> Dict:
        """Send a WhatsApp message using direct URL approach with improved handling"""
        # Get message record if message_id is specified
        message = None
        if message_id:
            result = await self.db.execute(
                select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
            )
            message = result.scalar_one_or_none()
            if not message:
                logger.error(f"Message {message_id} not found")
                raise ValueError(f"Message {message_id} not found")
        
        # If message_id is not specified, create a new record
        if not message:
            message = await self.create_message_history(account, recipient)
        
        # Prepare result
        result = {
            "success": False,
            "account_id": account.id,
            "recipient": recipient.phone,
            "message_id": message.id,
            "error": None,
            "timestamp": datetime.now()
        }
        
        # Check if account is ready
        if not account.is_ready:
            logger.warning(f"Account {account.id} is not ready for sending messages")
            result["error"] = "Account is not active or not initialized"
            message.status = WhatsAppMessageStatus.ERROR
            message.error_message = result["error"]
            await self.db.commit()
            return result
        
        driver = existing_driver
        profile_path = account.profile_path or self._get_profile_path(account.profile_name)
        browser_created = False
        
        try:
            # Use existing driver or create a new one
            if driver is None:
                # First visit main WhatsApp page to ensure we're authenticated
                logger.info(f"Getting browser for profile {profile_path}")
                driver = await self._get_or_create_browser(profile_path)
                browser_created = True
                
                # First check that the session is authenticated
                logger.info("First visiting main WhatsApp page to ensure we're authenticated")
                driver.get("https://web.whatsapp.com/")
                await asyncio.sleep(5)  # Give time to load
                
                # Check for QR code (if session is not authenticated)
                qr_elements = driver.find_elements(By.TAG_NAME, "canvas")
                if qr_elements:
                    logger.warning(f"QR code detected when trying to send message for account {account.id}")
                    # Take a screenshot of the QR code
                    try:
                        screenshot_path = os.path.join(profile_path, f"qr_detected_{int(time.time())}.png")
                        driver.save_screenshot(screenshot_path)
                        logger.info(f"QR code screenshot saved to {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"Failed to save QR code screenshot: {str(e)}")
                        
                    result["error"] = "WhatsApp account not authenticated"
                    message.status = WhatsAppMessageStatus.ERROR
                    message.error_message = result["error"]
                    await self.db.commit()
                    
                    # Update account status
                    account.status = WhatsAppAccountStatus.PENDING
                    await self.db.commit()
                    
                    # Close the browser
                    if browser_created:
                        try:
                            driver.quit()
                        except:
                            pass
                        async with self._browser_pool_lock:
                            if profile_path in self._browser_pool:
                                del self._browser_pool[profile_path]
                    
                    return result
                
                # Wait for UI to fully load
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='chat-list'], #pane-side"))
                    )
                    logger.info("WhatsApp UI loaded successfully")
                except Exception as e:
                    logger.warning(f"WhatsApp UI loading timeout: {str(e)}")
            
            # Format direct link for sending message
            message_text = str(recipient.message)
            direct_url = (
                f"https://web.whatsapp.com/send?phone={recipient.phone.replace('+', '')}"
                f"&text={quote(message_text)}"
            )
            
            # Navigate to the direct link
            logger.info(f"Navigating to direct URL for sending message to {recipient.phone}")
            driver.get(direct_url)
            
            # Initialize variables for tracking sending state
            message_sent = False
            button_found = False
            
            try:
                # Take a screenshot after navigating
                try:
                    screenshot_path = os.path.join(profile_path, f"direct_url_{int(time.time())}.png")
                    driver.save_screenshot(screenshot_path)
                    logger.info(f"Screenshot after direct URL navigation saved to {screenshot_path}")
                except Exception as e:
                    logger.warning(f"Failed to save screenshot: {str(e)}")
                
                # Check for version error message
                try:
                    # Use a generic selector for Chrome version error
                    error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Chrome') and contains(text(), '60')]")
                    if error_elements and len(error_elements) > 0:
                        logger.error("Detected Chrome version compatibility error")
                        
                        # Try to bypass the issue by using the main interface
                        try:
                            # Navigate to main page
                            driver.get("https://web.whatsapp.com/")
                            await asyncio.sleep(3)
                            
                            # Add JavaScript to change User-Agent
                            driver.execute_script("""
                            Object.defineProperty(navigator, 'userAgent', {
                                get: function () { return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'; }
                            });
                            """)
                            
                            # Try direct link again
                            driver.get(direct_url)
                            await asyncio.sleep(5)
                            
                            # Take a screenshot after retry
                            try:
                                screenshot_path = os.path.join(profile_path, f"retry_url_{int(time.time())}.png")
                                driver.save_screenshot(screenshot_path)
                                logger.info(f"Screenshot after retry saved to {screenshot_path}")
                            except Exception as e:
                                pass
                            
                        except Exception as e:
                            logger.error(f"Error during version bypass attempt: {str(e)}")
                    
                    # Check for invalid phone number error
                    error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Phone number shared via url is invalid')]")
                    if error_elements and len(error_elements) > 0:
                        raise ValueError(f"Invalid phone number: {recipient.phone}")
                except Exception as e:
                    if "Invalid phone number" in str(e):
                        logger.error(str(e))
                        raise
                    logger.warning(f"Error during error check: {str(e)}")
                
                # Optimized approach with pause before sending
                max_poll_time = 40  # increased to 40 seconds for all attempts
                poll_start = time.time()
                poll_attempts = 0
                
                # Phase 1: Wait for chat to load and find send button
                while time.time() - poll_start < max_poll_time and not message_sent and not button_found:
                    poll_attempts += 1
                    
                    # Take screenshot every 10 attempts for debugging
                    if poll_attempts % 10 == 0:
                        try:
                            screenshot_path = os.path.join(profile_path, f"poll_attempt_{poll_attempts}_{int(time.time())}.png")
                            driver.save_screenshot(screenshot_path)
                            logger.info(f"Poll attempt {poll_attempts} screenshot saved to {screenshot_path}")
                        except Exception as e:
                            pass
                    
                    # Check for QR code (session lost)
                    qr_elements = driver.find_elements(By.TAG_NAME, "canvas")
                    if qr_elements:
                        logger.error(f"QR code detected during message sending for account {account.id}")
                        raise Exception("WhatsApp account not authenticated")
                    
                    # Check for browser version error
                    version_error = driver.find_elements(By.XPATH, "//*[contains(text(), 'Chrome') and contains(text(), '60')]")
                    if version_error:
                        logger.error("Detected Chrome version error during polling")
                        
                        # Use JavaScript to modify user agent
                        driver.execute_script("""
                        Object.defineProperty(navigator, 'userAgent', {
                            get: function () { return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'; }
                        });
                        """)
                        
                        # Refresh the page
                        driver.refresh()
                        await asyncio.sleep(5)
                        continue
                    
                    # Check if chat is loaded
                    chat_loaded = False
                    try:
                        chat_elements = driver.find_elements(By.CSS_SELECTOR, '[data-testid="conversation-panel"]')
                        if chat_elements:
                            chat_loaded = True
                            logger.info("Chat panel found")
                    except Exception as e:
                        pass
                    
                    # Check for send button
                    send_button_selectors = [
                        'span[data-icon="send"]', 
                        'div[data-icon="send"]',
                        'button.send',
                        'div[aria-label="Send"]', 
                        '[role="button"][aria-label="Send"]',
                        '[data-testid="send"]',
                        '[aria-label="Send"]',  # Universal label
                        '[title="Send"]'        # Universal title
                    ]
                    
                    for selector in send_button_selectors:
                        try:
                            buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                            if buttons and len(buttons) > 0 and buttons[0].is_displayed():
                                logger.info(f"Send button found: {selector}")
                                button_found = True
                                break
                        except Exception as e:
                            pass
                    
                    # If button found or chat loaded and we've waited long enough
                    if button_found or (chat_loaded and poll_attempts > 20):
                        break
                    
                    # Small pause between attempts
                    await asyncio.sleep(0.5)
                
                # If button not found but chat loaded, try sending via Enter
                if not button_found and chat_loaded:
                    from selenium.webdriver.common.keys import Keys
                    
                    # Look for input field
                    input_selectors = [
                        '[contenteditable="true"][role="textbox"]',
                        '[data-testid="conversation-compose-box-input"]',
                        '#main footer .selectable-text',
                        '.copyable-text.selectable-text'
                    ]
                    
                    for selector in input_selectors:
                        try:
                            inputs = driver.find_elements(By.CSS_SELECTOR, selector)
                            if inputs and len(inputs) > 0:
                                # Focus on element and clear it
                                input_element = inputs[0]
                                driver.execute_script("arguments[0].focus();", input_element)
                                input_element.clear()
                                
                                # Additional Enter press may help send the message
                                input_element.send_keys(Keys.ENTER)
                                logger.info("Pressed Enter key in input field")
                                await asyncio.sleep(1)
                                button_found = True  # Set flag that we found a way to send
                                break
                        except Exception as e:
                            logger.debug(f"Error with input selector {selector}: {str(e)}")
                
                # Phase 2: If button found or we found input field, send message
                if button_found or chat_loaded:
                    logger.info("Ready to send message, waiting before attempting")
                    await asyncio.sleep(1)  # Pause for interface stabilization
                    
                    # Method 1: Send via JavaScript
                    try:
                        click_send_js = """
                        function clickSendButton() {
                            // Try to find send button
                            const selectors = [
                                'span[data-icon="send"]', 
                                'div[data-icon="send"]',
                                'button.send',
                                'div[aria-label="Send"]', 
                                '[role="button"][aria-label="Send"]',
                                '[data-testid="send"]',
                                '[aria-label="Send"]',
                                '[title="Send"]'
                            ];
                            
                            for (const selector of selectors) {
                                const elements = document.querySelectorAll(selector);
                                for (const el of elements) {
                                    if (el && el.offsetParent !== null) {
                                        // Element is visible - click it
                                        try {
                                            el.click();
                                            return true;
                                        } catch(e) {
                                            console.error('Error clicking element:', e);
                                        }
                                    }
                                }
                            }
                            
                            // If button not found, try sending via Enter in input field
                            const inputSelectors = [
                                '[contenteditable="true"][role="textbox"]',
                                '[data-testid="conversation-compose-box-input"]',
                                '#main footer .selectable-text',
                                '.copyable-text.selectable-text'
                            ];
                            
                            for (const selector of inputSelectors) {
                                const inputs = document.querySelectorAll(selector);
                                if (inputs.length > 0) {
                                    const input = inputs[0];
                                    input.focus();
                                    
                                    // Create and dispatch Enter event
                                    const enterEvent = new KeyboardEvent('keydown', {
                                        bubbles: true,
                                        cancelable: true,
                                        keyCode: 13
                                    });
                                    input.dispatchEvent(enterEvent);
                                    return true;
                                }
                            }
                            
                            return false;
                        }
                        return clickSendButton();
                        """
                        
                        result_js = driver.execute_script(click_send_js)
                        if result_js:
                            logger.info("Message sent via JavaScript")
                            message_sent = True
                    except Exception as e:
                        logger.warning(f"Error sending via JavaScript: {str(e)}")
                    
                    # If JavaScript didn't work, try other methods
                    if not message_sent:
                        # Method 2: Send via Enter key
                        try:
                            from selenium.webdriver.common.keys import Keys
                            from selenium.webdriver.common.action_chains import ActionChains
                            
                            input_selectors = [
                                '[contenteditable="true"][role="textbox"]',
                                '[data-testid="conversation-compose-box-input"]',
                                '#main footer .selectable-text',
                                '.copyable-text.selectable-text'
                            ]
                            
                            for selector in input_selectors:
                                inputs = driver.find_elements(By.CSS_SELECTOR, selector)
                                if inputs and len(inputs) > 0:
                                    # Focus on element
                                    driver.execute_script("arguments[0].focus();", inputs[0])
                                    
                                    # Send Enter
                                    actions = ActionChains(driver)
                                    actions.send_keys(Keys.ENTER)
                                    actions.perform()
                                    logger.info("Message sent via Enter key")
                                    message_sent = True
                                    break
                        except Exception as e:
                            logger.warning(f"Error sending via Enter key: {str(e)}")
                        
                        # Method 3: Click via Selenium Actions
                        if not message_sent:
                            try:
                                from selenium.webdriver.common.action_chains import ActionChains
                                
                                send_button_selectors = [
                                    'span[data-icon="send"]', 
                                    'div[data-icon="send"]',
                                    'button.send',
                                    'div[aria-label="Send"]',
                                    '[role="button"][aria-label="Send"]',
                                    '[data-testid="send"]',
                                    '[aria-label="Send"]',
                                    '[title="Send"]'
                                ]
                                
                                for selector in send_button_selectors:
                                    buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                                    if buttons and len(buttons) > 0:
                                        # Scroll to button
                                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buttons[0])
                                        await asyncio.sleep(0.5)
                                        
                                        # Click the button
                                        actions = ActionChains(driver)
                                        actions.move_to_element(buttons[0])
                                        actions.click()
                                        actions.perform()
                                        logger.info(f"Message sent via Selenium click on {selector}")
                                        message_sent = True
                                        break
                            except Exception as e:
                                logger.warning(f"Error sending via Selenium click: {str(e)}")
                        
                        # Method 4: Direct JavaScript click
                        if not message_sent:
                            try:
                                for selector in send_button_selectors:
                                    buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                                    if buttons and len(buttons) > 0:
                                        driver.execute_script("arguments[0].click();", buttons[0])
                                        logger.info(f"Message sent via direct JavaScript click on {selector}")
                                        message_sent = True
                                        break
                            except Exception as e:
                                logger.warning(f"Error sending via direct JavaScript click: {str(e)}")
                    
                    # Wait for send confirmation
                    await asyncio.sleep(2)
                    
                    # Take screenshot after send attempt
                    try:
                        screenshot_path = os.path.join(profile_path, f"after_send_{int(time.time())}.png")
                        driver.save_screenshot(screenshot_path)
                        logger.info(f"Screenshot after send attempt saved to {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"Failed to save after-send screenshot: {str(e)}")
                
                # Additional check for actual message sending
                if message_sent or button_found:
                    # Additional pause to ensure sending
                    await asyncio.sleep(2)
                    
                    # Check that input field is cleared - sign of successful sending
                    input_empty = False
                    try:
                        input_selectors = [
                            '[contenteditable="true"][role="textbox"]',
                            '[data-testid="conversation-compose-box-input"]',
                            '#main footer .selectable-text',
                            '.copyable-text.selectable-text'
                        ]
                        
                        for selector in input_selectors:
                            inputs = driver.find_elements(By.CSS_SELECTOR, selector)
                            if inputs and len(inputs) > 0:
                                input_text = inputs[0].text.strip()
                                if not input_text:
                                    input_empty = True
                                    logger.info("Input field is empty - message likely sent")
                                    break
                                else:
                                    logger.warning(f"Input field still contains text: '{input_text}'")
                    except Exception as e:
                        logger.warning(f"Error checking input field: {str(e)}")
                    
                    # Check for delivery markers
                    delivery_markers = False
                    try:
                        markers = driver.find_elements(By.CSS_SELECTOR, 
                            '[data-icon="msg-check"], [data-icon="msg-dblcheck"], .message-out .status-check')
                        if markers and len(markers) > 0:
                            delivery_markers = True
                            logger.info("Found delivery confirmation markers")
                    except Exception as e:
                        logger.warning(f"Error checking delivery markers: {str(e)}")
                    
                    # If there is at least one sign of successful sending
                    if input_empty or delivery_markers:
                        result["success"] = True
                        message.status = WhatsAppMessageStatus.SENT
                        if not message.message_metadata:
                            message.message_metadata = {}
                        message.message_metadata["sent_at"] = datetime.now().isoformat()
                        
                        # Update account metadata
                        if not account.account_metadata:
                            account.account_metadata = {}
                        account.account_metadata["last_message_sent"] = datetime.now().isoformat()
                        account.account_metadata["last_active"] = datetime.now().isoformat()
                        
                        try:
                            # Create event data for optimization
                            event_data = {
                                "target": recipient.phone,
                                "message_id": str(message.id),
                                "operation": "message_delivered"
                            }
                            # Schedule session optimization as a background task
                            asyncio.create_task(
                                SessionCacheManager().optimize_session(
                                    profile_path, 
                                    session_id=account.id, 
                                    event_data=event_data
                                )
                            )
                        except Exception as e:
                            # Silently log any optimization failures
                            logger.debug(f"Session cache optimization skipped: {str(e)}")
                        
                        await self.db.commit()
                        logger.info(f"Message sent successfully to {recipient.phone} (empty_input={input_empty}, markers={delivery_markers})")
                    else:
                        # Check for sent message in chat history
                        try:
                            message_elements = driver.find_elements(By.CSS_SELECTOR, 
                                '.message-out, [data-testid="msg-container"]')
                            if message_elements and len(message_elements) > 0:
                                # If we found at least one message in history, consider send successful
                                result["success"] = True
                                message.status = WhatsAppMessageStatus.SENT
                                if not message.message_metadata:
                                    message.message_metadata = {}
                                message.message_metadata["sent_at"] = datetime.now().isoformat()
                                
                                await self.db.commit()
                                logger.info(f"Message found in chat history - assuming successfully sent to {recipient.phone}")
                            else:
                                # If no signs of successful sending
                                result["success"] = False
                                message.status = WhatsAppMessageStatus.ERROR
                                message.error_message = "No confirmation of successful message delivery"
                                await self.db.commit()
                                logger.warning(f"No delivery confirmation for message to {recipient.phone}")
                        except Exception as e:
                            logger.warning(f"Error checking message history: {str(e)}")
                            # If no signs of successful sending
                            result["success"] = False
                            message.status = WhatsAppMessageStatus.ERROR
                            message.error_message = "No confirmation of successful message delivery"
                            await self.db.commit()
                            logger.warning(f"No delivery confirmation for message to {recipient.phone}")
                else:
                    if button_found:
                        logger.warning(f"Button was found but message couldn't be sent")
                        result["error"] = "Failed to click send button after finding it"
                    else:
                        logger.warning(f"Failed to find send button after {time.time() - poll_start:.2f}s of trying")
                        result["error"] = "Failed to find send button"
                    
                    message.status = WhatsAppMessageStatus.ERROR
                    message.error_message = result["error"]
                    await self.db.commit()
                
            except Exception as e:
                # Handle errors and set message status
                logger.error(f"Error sending WhatsApp message: {str(e)}")
                result["error"] = str(e)
                message.status = WhatsAppMessageStatus.ERROR
                message.error_message = result["error"]
                await self.db.commit()
                
                # Just return result with error instead of raising exception
                
        except Exception as e:
            # General errors
            logger.error(f"Message sending error: {str(e)}")
            result["error"] = f"Message sending failed: {str(e)}"
            message.status = WhatsAppMessageStatus.ERROR
            message.error_message = result["error"]
            
            # Check if we lost connection
            if isinstance(e, WebDriverException) and "not reachable" in str(e).lower():
                account.status = WhatsAppAccountStatus.ERROR
                account.set_error("Browser connection lost")
            
            await self.db.commit()
            
            # In case of critical error, close browser
            if driver and browser_created:
                try:
                    driver.quit()
                except:
                    pass
                # Remove from pool
                async with self._browser_pool_lock:
                    if profile_path in self._browser_pool:
                        del self._browser_pool[profile_path]
        
        finally:
            # Close browser only if we created it and need to close
            if driver and close_driver and browser_created:
                try:
                    driver.quit()
                    logger.info(f"Browser closed after sending message to {recipient.phone}")
                except Exception as e:
                    logger.warning(f"Error closing browser: {str(e)}")
                
                # Remove from pool
                async with self._browser_pool_lock:
                    if profile_path in self._browser_pool:
                        del self._browser_pool[profile_path]
        
        return result

    async def send_bulk_messages(
        self,
        account: WhatsAppAccount,
        recipients: List[WhatsAppMessageRecipient],
        message_ids: Optional[List[str]] = None,
        wait_time: int = 60
    ) -> List[Dict]:
        """Send bulk messages with optimized delay between them"""
        results = []
        
        logger.info(f"Starting bulk send for account {account.id}, {len(recipients)} messages")
        
        # Get profile path
        profile_path = account.profile_path or self._get_profile_path(account.profile_name)
        
        # Create one browser for all messages
        driver = None
        try:
            # First check account status to ensure it's authenticated
            status_check = await self.check_account_status(account)
            if status_check["status"] != WhatsAppAccountStatus.ACTIVE:
                logger.warning(f"Account {account.id} is not active for bulk sending. Current status: {status_check['status']}")
                # Try to initialize the account again if it's not active
                if account.status != WhatsAppAccountStatus.ACTIVE:
                    logger.info(f"Re-initializing account {account.id} before bulk send")
                    init_result = await self.initialize_session(account)
                    if not init_result["success"]:
                        error_msg = f"Failed to initialize account: {init_result.get('error', 'Unknown error')}"
                        logger.error(error_msg)
                        # Return error results for all messages
                        for i, recipient in enumerate(recipients):
                            message_id = message_ids[i] if message_ids and i < len(message_ids) else None
                            if message_id:
                                result = await self.db.execute(
                                    select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
                                )
                                message = result.scalar_one_or_none()
                                if message:
                                    message.status = WhatsAppMessageStatus.ERROR
                                    message.error_message = error_msg
                            results.append({
                                "success": False,
                                "account_id": account.id,
                                "recipient": recipient.phone,
                                "message_id": message_id,
                                "error": error_msg,
                                "timestamp": datetime.now()
                            })
                        await self.db.commit()
                        return results
            
            # Initialize browser once for all messages
            logger.info(f"Initializing browser for bulk send using profile: {profile_path}")
            driver = await self._get_or_create_browser(profile_path)
            
            # First visit WhatsApp Web page to ensure we're authenticated
            driver.get("https://web.whatsapp.com/")
            await asyncio.sleep(5)
            
            # Check if we need to authenticate
            qr_elements = driver.find_elements(By.TAG_NAME, "canvas")
            if qr_elements:
                logger.error(f"QR code detected before bulk sending for account {account.id}")
                error_msg = "WhatsApp account not authenticated"
                # Return error results for all messages
                for i, recipient in enumerate(recipients):
                    message_id = message_ids[i] if message_ids and i < len(message_ids) else None
                    if message_id:
                        result = await self.db.execute(
                            select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
                        )
                        message = result.scalar_one_or_none()
                        if message:
                            message.status = WhatsAppMessageStatus.ERROR
                            message.error_message = error_msg
                    results.append({
                        "success": False,
                        "account_id": account.id,
                        "recipient": recipient.phone,
                        "message_id": message_id,
                        "error": error_msg,
                        "timestamp": datetime.now()
                    })
                await self.db.commit()
                
                # Close the browser
                try:
                    driver.quit()
                except:
                    pass
                async with self._browser_pool_lock:
                    if profile_path in self._browser_pool:
                        del self._browser_pool[profile_path]
                
                return results
            
            for i, recipient in enumerate(recipients):
                logger.info(f"Processing message {i+1}/{len(recipients)} to {recipient.phone}")
                # Get message ID if provided
                message_id = message_ids[i] if message_ids and i < len(message_ids) else None
                
                try:
                    # Use shared browser for all messages and don't close between sends
                    result = await self.send_message(
                        account=account,
                        recipient=recipient,
                        message_id=message_id,
                        wait_time=wait_time,
                        existing_driver=driver,
                        close_driver=False  # Don't close browser between messages
                    )
                    
                    # Log result inside try block
                    if result.get('success', False):
                        logger.info(f"Message {i+1} sent successfully")
                    else:
                        logger.error(f"Message {i+1} error: {result.get('error', 'Unknown error')}")
                    
                    results.append(result)
                    
                    # Minimum delay between messages
                    if i < len(recipients) - 1:  # Skip delay after last message
                        import random
                        delay = random.uniform(2, 3)  # Slightly longer pause for reliability
                        logger.info(f"Waiting {delay:.2f} seconds before next message")
                        await asyncio.sleep(delay)
                
                except Exception as e:
                    logger.error(f"Error sending message {i+1}: {str(e)}")
                    # Add error info to result
                    results.append({
                        "success": False,
                        "account_id": account.id,
                        "recipient": recipient.phone,
                        "message_id": message_id,
                        "error": f"Exception: {str(e)}",
                        "timestamp": datetime.now()
                    })
                    
                    # Increase delay after error, but not after last message
                    if i < len(recipients) - 1:
                        await asyncio.sleep(5)  # Longer pause after error
                
                # Check if QR code appeared (session may have been lost)
                if i % 5 == 0 and i > 0:  # Check every 5 messages
                    try:
                        qr_elements = driver.find_elements(By.TAG_NAME, "canvas")
                        if qr_elements:
                            logger.error(f"QR code detected during bulk sending after {i} messages")
                            # Update account status
                            account.status = WhatsAppAccountStatus.PENDING
                            await self.db.commit()
                            
                            # Stop sending remaining messages
                            error_msg = "WhatsApp session lost during bulk sending"
                            for j in range(i, len(recipients)):
                                recipient = recipients[j]
                                message_id = message_ids[j] if message_ids and j < len(message_ids) else None
                                if message_id:
                                    result = await self.db.execute(
                                        select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
                                    )
                                    message = result.scalar_one_or_none()
                                    if message:
                                        message.status = WhatsAppMessageStatus.ERROR
                                        message.error_message = error_msg
                                results.append({
                                    "success": False,
                                    "account_id": account.id,
                                    "recipient": recipient.phone,
                                    "message_id": message_id,
                                    "error": error_msg,
                                    "timestamp": datetime.now()
                                })
                            await self.db.commit()
                            break
                    except Exception as e:
                        logger.warning(f"Error checking for QR code during bulk sending: {str(e)}")
        except Exception as e:
            logger.error(f"Error during bulk send: {str(e)}")
        finally:
            # Additional pause to ensure sending of last message
            await asyncio.sleep(3)
            logger.info("Final pause before closing browser")
            
            # Close browser only after sending all messages
            if driver:
                try:
                    # Check how many messages were sent successfully
                    success_count = sum(1 for r in results if r.get('success', False))
                    logger.info(f"Success count before closing browser: {success_count}/{len(results)}")
                    
                    driver.quit()
                    logger.info("Browser closed after completing bulk send")
                except Exception as e:
                    logger.warning(f"Error closing browser after bulk send: {str(e)}")
                
                # Remove from pool
                async with self._browser_pool_lock:
                    if profile_path in self._browser_pool:
                        del self._browser_pool[profile_path]
        
        logger.info(f"Bulk send completed. Success: {sum(1 for r in results if r.get('success', False))}/{len(results)}")
        return results

    async def delete_account(self, account: WhatsAppAccount) -> bool:
        """Delete a WhatsApp account and all related data"""
        try:
            logger.info(f"Starting deletion of account {account.id}")
            
            # Delete all related messages
            result = await self.db.execute(
                select(WhatsAppMessage).where(WhatsAppMessage.account_id == account.id)
            )
            messages = result.scalars().all()
            for message in messages:
                await self.db.delete(message)
            logger.info(f"Deleted {len(messages)} messages for account {account.id}")
            
            # Close and remove browser from pool, if exists
            profile_path = account.profile_path
            if profile_path and profile_path in self._browser_pool:
                try:
                    self._browser_pool[profile_path].quit()
                    logger.info(f"Closed browser for account {account.id}")
                except Exception as e:
                    logger.warning(f"Error closing browser: {str(e)}")
                
                async with self._browser_pool_lock:
                    if profile_path in self._browser_pool:
                        del self._browser_pool[profile_path]
            
            # Delete Chrome profile
            profile_path = self._get_profile_path(account.profile_name)
            if os.path.exists(profile_path):
                import shutil
                try:
                    shutil.rmtree(profile_path)
                    logger.info(f"Deleted profile directory: {profile_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete profile directory: {str(e)}")
            
            # Delete QR code from Redis
            await delete_qr_code(account.id)
            
            # Delete account record
            await self.db.delete(account)
            await self.db.commit()
            logger.info(f"Account {account.id} deleted successfully")
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete account {account.id}: {str(e)}")
            await self.db.rollback()
            return False
    
    async def check_account_status(self, account: WhatsAppAccount) -> Dict:
        """Check WhatsApp account status"""
        driver = None
        try:
            logger.info(f"Checking status for account {account.id}")
            # Check profile path
            if not account.profile_path:
                account.profile_path = self._get_profile_path(account.profile_name)
                await self.db.commit()
                logger.info(f"Updated profile path for account {account.id}: {account.profile_path}")
            
            # Get or create browser
            driver = await self._get_or_create_browser(account.profile_path)
            
            # Check if WhatsApp Web is open
            if not driver.current_url.startswith("https://web.whatsapp.com"):
                logger.info(f"Navigating to WhatsApp Web for account {account.id}")
                driver.get("https://web.whatsapp.com/")
                await asyncio.sleep(5)  # Allow time to load
            
            # Check for QR code
            qr_elements = driver.find_elements(By.TAG_NAME, "canvas")
            
            # Check for interface elements
            chat_elements = driver.find_elements(By.CSS_SELECTOR, 
                "#app, #main, .app, .two, [data-testid='conversation-panel'], " +
                "[data-testid='chat-list'], .landing-wrapper")
                
            # Check for loading indicators or errors
            loading_elements = driver.find_elements(By.CSS_SELECTOR, 
                ".landing-main, [data-testid='intro-text'], .landing-title")
                
            # Take a screenshot for debugging
            try:
                screenshot_path = os.path.join(account.profile_path, f"status_check_{int(time.time())}.png")
                driver.save_screenshot(screenshot_path)
                logger.info(f"Status check screenshot saved to {screenshot_path}")
            except Exception as e:
                logger.warning(f"Failed to save status check screenshot: {str(e)}")
                
            # If QR code is present - waiting for authentication
            if qr_elements:
                logger.info(f"QR code detected for account {account.id} - needs authentication")
                # Account not authenticated, but QR code is present
                account.status = WhatsAppAccountStatus.PENDING
                await self.db.commit()
                
                return {
                    "status": WhatsAppAccountStatus.PENDING,
                    "is_connected": False,
                    "qr_available": True,
                    "last_check": datetime.now().isoformat()
                }
            
            # If chat elements are present and no QR code - authenticated
            elif chat_elements and not qr_elements and not loading_elements:
                logger.info(f"Account {account.id} is active")
                # Account is active
                account.status = WhatsAppAccountStatus.ACTIVE
                if not account.account_metadata:
                    account.account_metadata = {}
                account.account_metadata["last_check"] = datetime.now().isoformat()
                account.account_metadata["last_active"] = datetime.now().isoformat()
                await self.db.commit()
                
                return {
                    "status": WhatsAppAccountStatus.ACTIVE,
                    "is_connected": True,
                    "last_check": datetime.now().isoformat()
                }
            
            # Page is loading or in unknown state
            else:
                logger.info(f"Account {account.id} status check inconclusive - page loading or unknown state")
                return {
                    "status": account.status,
                    "is_connected": False,
                    "is_loading": bool(loading_elements),
                    "last_check": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error checking account status: {str(e)}")
            
            # In case of error, may need to reinitialize
            account.status = WhatsAppAccountStatus.ERROR
            account.set_error(f"Status check failed: {str(e)}")
            await self.db.commit()
            
            return {
                "status": WhatsAppAccountStatus.ERROR,
                "is_connected": False,
                "error": str(e),
                "last_check": datetime.now().isoformat(),
                "needs_reinitialization": True
            }
        finally:
            # Don't close the driver - let it be managed by the pool
            pass
        
    async def logout(self, account: WhatsAppAccount) -> bool:
        """Log out from WhatsApp account"""
        driver = None
        try:
            logger.info(f"Starting logout for account {account.id}")
            if not account.profile_path:
                account.profile_path = self._get_profile_path(account.profile_name)
            
            # Get or create browser
            driver = await self._get_or_create_browser(account.profile_path)
            
            # Navigate to WhatsApp page
            logger.info("Navigating to WhatsApp Web")
            driver.get("https://web.whatsapp.com/")
            await asyncio.sleep(5)
            
            # Find and click menu button
            try:
                # First look for new interface
                logger.info("Looking for menu button")
                menu_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='menu'] svg, span[data-icon='menu']"))
                )
                menu_button.click()
                logger.info("Clicked menu button")
                await asyncio.sleep(1)
                
                # Find and click logout button
                logger.info("Looking for logout button")
                logout_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@aria-label, 'Log out') or contains(text(), 'Log out')]"))
                )
                logout_button.click()
                logger.info("Clicked logout button")
                await asyncio.sleep(1)
                
                # Confirm logout
                logger.info("Looking for confirmation button")
                confirm_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@aria-label, 'OK') or contains(text(), 'OK')]"))
                )
                confirm_button.click()
                logger.info("Clicked confirmation button")
                await asyncio.sleep(3)
                
                # Close browser
                driver.quit()
                logger.info("Browser closed after logout")
                
                # Remove browser from pool
                async with self._browser_pool_lock:
                    if account.profile_path in self._browser_pool:
                        del self._browser_pool[account.profile_path]
                
                # Update account status
                account.status = WhatsAppAccountStatus.PENDING
                if not account.account_metadata:
                    account.account_metadata = {}
                account.account_metadata["last_logout"] = datetime.now().isoformat()
                await self.db.commit()
                
                return True
            except Exception as e:
                logger.error(f"Error during logout: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error during logout: {str(e)}")
            return False