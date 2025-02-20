import os
import time
import base64
import asyncio
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


class WhatsAppService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_profile_dir = os.path.abspath("./chrome-profiles")
        if not os.path.exists(self.base_profile_dir):
            os.makedirs(self.base_profile_dir)
        self.qr_check_interval = 1
        self.qr_max_wait = 60

    def _get_profile_path(self, profile_name: str) -> str:
        """Returns Chrome profile path"""
        return os.path.join(self.base_profile_dir, f"profile-{profile_name}")

    async def _cleanup_chrome_processes(self):
        import psutil
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'].lower() == 'chrome.exe' and proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if 'undetected_chromedriver' in cmdline:
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    async def _init_chrome(self, profile_path: str, debug_prefix: str = "") -> uc.Chrome:
        
        await self._cleanup_chrome_processes()
        loop = asyncio.get_event_loop()
        max_attempts = 3

        for attempt in range(max_attempts):
            try:

                def create_driver():
                    options = uc.ChromeOptions()
                    options.add_argument('--no-sandbox')
                    options.add_argument(f'--user-data-dir={profile_path}')
                    
                    options.add_argument('--headless=new')
                    options.add_argument('--window-size=1920,1080')
                    options.add_argument('--start-maximized')
                    options.add_argument('--hide-scrollbars')
                    options.add_argument('--force-device-scale-factor=1')
                    
                    options.add_argument('--disable-dev-shm-usage')
                    options.add_argument('--disable-gpu')
                    options.add_argument('--disable-extensions')
                    options.add_argument('--disable-software-rasterizer')
                    options.add_argument('--disable-features=site-per-process')
                    options.add_argument('--disable-web-security')
                    options.add_argument('--allow-running-insecure-content')
                    
                    options.add_argument('--disable-notifications')
                    options.add_argument('--disable-popup-blocking')
                    options.add_argument('--disable-blink-features=AutomationControlled')
                    
                    debug_port = random.randint(9222, 9999)
                    options.add_argument(f'--remote-debugging-port={debug_port}')
                    
                    try:
                        driver = uc.Chrome(
                            options=options,
                            headless=True,
                            use_subprocess=True,
                            driver_executable_path=None
                        )
                        return driver
                    except Exception as e:
                        raise

                driver = await loop.run_in_executor(None, create_driver)
                return driver
            except Exception as e:
                if attempt < max_attempts - 1:
                    await self._cleanup_chrome_processes()
                    await asyncio.sleep(5)
                    continue
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
        """Initializes WhatsApp session"""
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
            
            driver = await self._init_chrome(profile_path, "Init")
            
            driver.get("https://web.whatsapp.com/")
            await asyncio.sleep(10)
            
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
                                
                                await set_qr_code(account.id, qr_base64)
                                
                                saved_qr = await get_qr_code(account.id)
                                if saved_qr:
                                    result["qr_code"] = qr_base64
                                    account.status = WhatsAppAccountStatus.PENDING
                                    await self.db.commit()
                                    qr_found = True
                        
                        chat_list = driver.find_elements(By.CSS_SELECTOR, "#side, .two")
                        if chat_list:
                            await asyncio.sleep(5)
                            await delete_qr_code(account.id)
                            
                            account.status = WhatsAppAccountStatus.ACTIVE
                            await self.db.commit()
                            result["success"] = True
                            driver.quit()
                            return result
                            
                    except Exception as e:
                        pass
                        
                    await asyncio.sleep(2)
                    
                if not result["success"]:
                    result["error"] = "Authorization timeout"
                    account.status = WhatsAppAccountStatus.ERROR
                    await self.db.commit()
                
            except TimeoutException:
                result["error"] = "Failed to get QR code"
                account.status = WhatsAppAccountStatus.ERROR
                await self.db.commit()
                
        except Exception as e:
            result["error"] = f"Session initialization error: {str(e)}"
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
        """Sends a message via WhatsApp"""
        message = None
        if message_id:
            result = await self.db.execute(
                select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
            )
            message = result.scalar_one_or_none()
            if not message:
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
            driver = await self._init_chrome(account.profile_path, "Send")
            from urllib.parse import quote
            message_text = str(recipient.message)
            direct_url = (
                f"https://web.whatsapp.com/send?phone={recipient.phone.replace('+', '')}"
                f"&text={quote(message_text)}"
            )
            driver.get(direct_url)
            
            try:
                send_button = WebDriverWait(driver, wait_time).until(
                    EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="send"]'))
                )
                
                time.sleep(random.uniform(0.5, 2.0))
                send_button.click()
                time.sleep(3)
                result["success"] = True
                message.status = WhatsAppMessageStatus.SENT
                message.message_metadata = {"sent_at": str(datetime.now())}
                await self.db.commit()
                
            except TimeoutException:
                result["error"] = "Failed to load chat or find send button"
                account.status = WhatsAppAccountStatus.ERROR
                message.status = WhatsAppMessageStatus.ERROR
                message.error_message = result["error"]
                await self.db.commit()
                
        except Exception as e:
            error_msg = f"Message sending error: {str(e)}"
            result["error"] = error_msg
            account.status = WhatsAppAccountStatus.ERROR
            message.status = WhatsAppMessageStatus.ERROR
            message.error_message = error_msg
            await self.db.commit()
            
        finally:
            if 'driver' in locals():
                try:
                    driver.quit()
                except:
                    pass
        
        return result

    async def send_bulk_messages(
        self,
        account: WhatsAppAccount,
        recipients: List[WhatsAppMessageRecipient],
        message_ids: Optional[List[str]] = None,
        wait_time: int = 60
    ) -> List[Dict]:
        results = []
        
        for i, recipient in enumerate(recipients):
            message_id = message_ids[i] if message_ids and i < len(message_ids) else None
            result = await self.send_message(
                account=account,
                recipient=recipient,
                message_id=message_id,
                wait_time=wait_time
            )
            results.append(result)
            
            if len(recipients) > 1 and recipient != recipients[-1]:
                delay = random.randint(5, 15)
                time.sleep(delay)
        
        return results

    async def delete_account(self, account: WhatsAppAccount) -> bool:
        try:
            profile_path = self._get_profile_path(account.profile_name)
            if os.path.exists(profile_path):
                import shutil
                shutil.rmtree(profile_path)

            await delete_qr_code(account.id)
            
            await self.db.delete(account)
            await self.db.commit()
            
            return True
        except Exception:
            return False