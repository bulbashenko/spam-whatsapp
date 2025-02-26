import os
import time
import base64
import asyncio
import logging
import undetected_chromedriver as uc
from app.core.redis import set_qr_code, delete_qr_code, get_qr_code
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import random
from typing import Optional, Dict, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.whatsapp import WhatsAppAccount, WhatsAppAccountStatus, WhatsAppMessage, WhatsAppMessageStatus
from app.schemas.whatsapp import WhatsAppMessageRecipient, WhatsAppMessageHistory

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_profile_dir = os.path.abspath("./chrome-profiles")
        if not os.path.exists(self.base_profile_dir):
            os.makedirs(self.base_profile_dir)
        self.qr_check_interval = 1
        self.qr_max_wait = 60
        self._browser_pool = {}
        self._browser_pool_lock = asyncio.Lock()

    def _get_profile_path(self, profile_name: str) -> str:
        """Returns Chrome profile path"""
        return os.path.join(self.base_profile_dir, f"profile-{profile_name}")

    async def _cleanup_chrome_processes(self):
        """Cleanup stray Chrome processes"""
        import psutil
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'].lower() == 'chrome.exe' and proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if 'undetected_chromedriver' in cmdline:
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    async def _get_or_create_browser(self, profile_path: str) -> uc.Chrome:
        """Get existing browser from pool or create new one"""
        async with self._browser_pool_lock:
            if profile_path in self._browser_pool:
                browser = self._browser_pool[profile_path]
                try:
                    # Check if browser is still alive
                    browser.current_url
                    return browser
                except:
                    # Browser died, remove from pool
                    del self._browser_pool[profile_path]
            
            # Create new browser
            browser = await self._init_chrome(profile_path)
            self._browser_pool[profile_path] = browser
            return browser

    async def _init_chrome(self, profile_path: str) -> uc.Chrome:
        """Initialize Chrome instance with optimized settings"""
        loop = asyncio.get_event_loop()
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                def create_driver():
                    options = uc.ChromeOptions()
                    options.add_argument('--no-sandbox')
                    options.add_argument(f'--user-data-dir={profile_path}')
                    options.add_argument('--start-maximized')  # Ensure window is maximized
                    options.add_argument('--window-position=0,0')  # Position window at top-left
                    options.add_argument('--disable-dev-shm-usage')
                    options.add_argument('--disable-extensions')
                    options.add_argument('--disable-background-mode')  # Prevent background mode
                    options.add_argument('--autoplay-policy=no-user-gesture-required')  # Allow foreground behavior
                    
                    # Performance optimizations
                    options.add_argument('--js-flags=--expose-gc')
                    options.add_argument('--enable-precise-memory-info')
                    options.add_argument('--disable-default-apps')
                    options.add_argument('--no-first-run')
                    options.add_argument('--no-default-browser-check')
                    options.add_argument('--disable-background-networking')
                    options.add_argument('--disable-background-timer-throttling')
                    options.add_argument('--disable-client-side-phishing-detection')
                    options.add_argument('--disable-component-update')
                    
                    debug_port = random.randint(9222, 9999)
                    options.add_argument(f'--remote-debugging-port={debug_port}')
                    
                    driver = uc.Chrome(
                        options=options,
                        headless=False,
                        use_subprocess=True,
                        driver_executable_path=None
                    )
                    return driver

                driver = await loop.run_in_executor(None, create_driver)
                return driver
            except Exception as e:
                if attempt < max_attempts - 1:
                    await self._cleanup_chrome_processes()
                    await asyncio.sleep(5)
                    continue
                logger.error(f"Failed to initialize Chrome after {max_attempts} attempts: {str(e)}")
                raise Exception(f"Failed to initialize Chrome after {max_attempts} attempts: {str(e)}")

    async def get_account(self, account_id: str) -> Optional[WhatsAppAccount]:
        """Gets account by ID"""
        result = await self.db.execute(
            select(WhatsAppAccount).where(WhatsAppAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def initialize_session(
        self, account: WhatsAppAccount, wait_time: int = 60
    ) -> Dict:
        """Initialize WhatsApp session with optimized QR handling"""
        result = {
            "success": False,
            "account_id": account.id,
            "status": account.status,
            "error": None,
            "qr_code": None
        }

        profile_path = self._get_profile_path(account.profile_name)
        account.profile_path = profile_path
        
        try:
            if os.path.exists(profile_path):
                import shutil
                shutil.rmtree(profile_path)
            
            os.makedirs(profile_path, exist_ok=True)
            
            driver = await self._init_chrome(profile_path)
            
            driver.get("https://web.whatsapp.com/")
            await asyncio.sleep(5)  # Reduced initial wait
            
            start_time = time.time()
            qr_found = False
            
            try:
                while time.time() - start_time < wait_time:
                    try:
                        if not qr_found:
                            qr_ready = driver.execute_script("""
                                const canvas = document.querySelector('canvas');
                                if (!canvas) return false;
                                const rect = canvas.getBoundingClientRect();
                                if (rect.width === 0 || rect.height === 0) return false;
                                const context = canvas.getContext('2d');
                                const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
                                return imageData.data.some(pixel => pixel !== 0);
                            """)
                            
                            if qr_ready:
                                qr_canvas = WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located((By.TAG_NAME, "canvas"))
                                )
                                qr_base64 = driver.execute_script("""
                                    const canvas = arguments[0];
                                    if (!canvas || canvas.width === 0 || canvas.height === 0) {
                                        throw new Error('Canvas is not ready or has zero dimensions');
                                    }
                                    try {
                                        return canvas.toDataURL('image/png').substring(22);
                                    } catch (e) {
                                        throw new Error('Error getting data from canvas: ' + e.message);
                                    }
                                """, qr_canvas)
                                
                                await set_qr_code(account.id, qr_base64, expire=120)  # Reduced TTL
                                
                                saved_qr = await get_qr_code(account.id)
                                if saved_qr:
                                    result["qr_code"] = qr_base64
                                    account.status = WhatsAppAccountStatus.PENDING
                                    await self.db.commit()
                                    qr_found = True
                        
                        chat_list = driver.find_elements(By.CSS_SELECTOR, "#side, .two")
                        if chat_list:
                            await asyncio.sleep(2)  # Reduced wait
                            await delete_qr_code(account.id)
                            
                            account.status = WhatsAppAccountStatus.ACTIVE
                            await self.db.commit()
                            result["success"] = True
                            return result
                            
                    except Exception as e:
                        logger.debug(f"Waiting for QR code or login: {str(e)}")
                        
                    await asyncio.sleep(1)  # Reduced polling interval
                    
                if not result["success"]:
                    logger.error(f"Authorization timeout for account {account.id}")
                    result["error"] = "Session initialization failed"
                    account.status = WhatsAppAccountStatus.ERROR
                    await self.db.commit()
                
            except TimeoutException:
                logger.error(f"Failed to get QR code for account {account.id}")
                result["error"] = "Session initialization failed"
                account.status = WhatsAppAccountStatus.ERROR
                await self.db.commit()
                
        except Exception as e:
            logger.error(f"Session initialization error for account {account.id}: {str(e)}")
            result["error"] = "Session initialization failed"
            account.status = WhatsAppAccountStatus.ERROR
            await self.db.commit()
            
        finally:
            if 'driver' in locals():
                try:
                    driver.quit()
                except:
                    pass
        
        return result

    async def create_message_history(
        self,
        account: WhatsAppAccount,
        recipient: WhatsAppMessageRecipient,
        status: WhatsAppMessageStatus = WhatsAppMessageStatus.PENDING
    ) -> WhatsAppMessage:
        """Creates a message history record"""
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
        """Gets message history for an account"""
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
        wait_time: int = 60
    ) -> Dict:
        """Send WhatsApp message using connection pooling"""
        message = None
        if message_id:
            result = await self.db.execute(
                select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
            )
            message = result.scalar_one_or_none()
            if not message:
                logger.error(f"Message {message_id} not found")
                raise ValueError(f"Message {message_id} not found")
        
        if not message_id:
            message = await self.create_message_history(account, recipient)
        
        result = {
            "success": False,
            "account_id": account.id,
            "recipient": recipient.phone,
            "message_id": message.id,
            "error": None,
            "timestamp": datetime.now()
        }
        
        if not account.is_ready:
            result["error"] = "Account is not active or not initialized"
            message.status = WhatsAppMessageStatus.ERROR
            message.error_message = result["error"]
            await self.db.commit()
            return result
        
        try:
            # Get or create browser from pool
            driver = await self._get_or_create_browser(account.profile_path)
            
            from urllib.parse import quote
            message_text = str(recipient.message)
            direct_url = (
                f"https://web.whatsapp.com/send?phone={recipient.phone.replace('+', '')}"
                f"&text={quote(message_text)}"
            )
            
            # Check if already on correct page
            current_url = driver.current_url
            if not current_url.startswith("https://web.whatsapp.com/send"):
                driver.get(direct_url)
            
            try:
                send_button = WebDriverWait(driver, wait_time).until(
                    EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="send"]'))
                )
                
                await asyncio.sleep(random.uniform(0.5, 1.0))
                send_button.click()
                await asyncio.sleep(1)
                
                result["success"] = True
                message.status = WhatsAppMessageStatus.SENT
                message.message_metadata = {"sent_at": str(datetime.now())}
                await self.db.commit()
                
            except TimeoutException:
                logger.error(f"Failed to load chat or find send button for account {account.id}, recipient {recipient.phone}")
                result["error"] = "Message sending failed"
                account.status = WhatsAppAccountStatus.ERROR
                message.status = WhatsAppMessageStatus.ERROR
                message.error_message = "Failed to send message"
                await self.db.commit()
                
        except Exception as e:
            logger.error(f"Message sending error for account {account.id}, recipient {recipient.phone}: {str(e)}")
            result["error"] = "Message sending failed"
            account.status = WhatsAppAccountStatus.ERROR
            message.status = WhatsAppMessageStatus.ERROR
            message.error_message = "Failed to send message"
            await self.db.commit()
        
        return result

    async def send_bulk_messages(
        self,
        account: WhatsAppAccount,
        recipients: List[WhatsAppMessageRecipient],
        message_ids: Optional[List[str]] = None,
        wait_time: int = 60
    ) -> List[Dict]:
        """Send bulk messages with optimized delays and connection reuse"""
        results = []
        
        logger.info(f"Starting bulk send for account {account.id}, {len(recipients)} messages")
        
        for i, recipient in enumerate(recipients):
            logger.info(f"Processing message {i+1}/{len(recipients)} to {recipient.phone}")
            message_id = message_ids[i] if message_ids and i < len(message_ids) else None
            
            try:
                if message_id:
                    logger.info(f"Using existing message ID: {message_id}")
                
                result = await self.send_message(
                    account=account,
                    recipient=recipient,
                    message_id=message_id,
                    wait_time=wait_time
                )
                
                # Логируем результат отправки
                logger.info(f"Message {i+1} result: {result.get('success', False)}")
                if not result.get('success', False):
                    logger.error(f"Message {i+1} error: {result.get('error', 'Unknown error')}")
                    
                results.append(result)
                
                # Small delay between messages
                delay = random.uniform(2, 5)  # Увеличим задержку между сообщениями
                logger.info(f"Waiting {delay:.2f} seconds before next message")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error sending message {i+1}: {str(e)}")
                # Добавляем результат с ошибкой в список
                results.append({
                    "success": False,
                    "account_id": account.id,
                    "recipient": recipient.phone,
                    "message_id": message_id,
                    "error": f"Exception: {str(e)}",
                    "timestamp": datetime.now()
                })
        
        logger.info(f"Bulk send completed. Success: {sum(1 for r in results if r.get('success', False))}/{len(results)}")
        return results

    async def delete_account(self, account: WhatsAppAccount) -> bool:
        """Deletes WhatsApp account and all associated data"""
        try:
            # Delete all associated messages first
            result = await self.db.execute(
                select(WhatsAppMessage).where(WhatsAppMessage.account_id == account.id)
            )
            messages = result.scalars().all()
            for message in messages:
                await self.db.delete(message)
            
            # Delete Chrome profile if exists
            profile_path = self._get_profile_path(account.profile_name)
            if os.path.exists(profile_path):
                import shutil
                shutil.rmtree(profile_path)

            # Delete QR code from Redis
            await delete_qr_code(account.id)
            
            # Finally delete the account
            await self.db.delete(account)
            await self.db.commit()
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete account {account.id}: {str(e)}")
            await self.db.rollback()
            return False