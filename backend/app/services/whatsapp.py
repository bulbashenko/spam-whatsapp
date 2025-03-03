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
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException
from urllib.parse import quote
from typing import Optional, Dict, List, Any, Union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import set_qr_code, delete_qr_code, get_qr_code, reset_auth_status
from app.models.whatsapp import WhatsAppAccount, WhatsAppAccountStatus, WhatsAppMessage, WhatsAppMessageStatus
from app.schemas.whatsapp import WhatsAppMessageRecipient, WhatsAppMessageHistory

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self, db: AsyncSession):
        self.db = db
        
        # Настройка директории для Chrome профилей
        if settings.CHROME_PROFILES_DIR:
            self.base_profile_dir = os.path.abspath(settings.CHROME_PROFILES_DIR)
        else:
            # Резервная директория, если настройка не указана
            self.base_profile_dir = os.path.abspath("./chrome-profiles")
        
        # Создаем директорию, если она не существует
        if not os.path.exists(self.base_profile_dir):
            os.makedirs(self.base_profile_dir, exist_ok=True)
            
        # Настройки таймингов
        self.qr_check_interval = 1
        self.qr_max_wait = 60
        
        # Блокировка для пула браузеров
        self._browser_pool_lock = asyncio.Lock()
        self._browser_pool = {}
    
    def _get_profile_path(self, profile_name: str) -> str:
        """Возвращает путь к профилю Chrome"""
        # Убираем недопустимые символы из имени профиля
        safe_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in profile_name)
        return os.path.join(self.base_profile_dir, f"profile-{safe_name}")
    
    async def _cleanup_chrome_processes(self):
        """Очищает зависшие процессы Chrome"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    proc_name = proc.info['name'].lower()
                    # Проверяем имя процесса в зависимости от ОС
                    is_chrome = False
                    if platform.system() == "Windows":
                        is_chrome = proc_name == 'chrome.exe'
                    else:
                        is_chrome = proc_name in ['chrome', 'chromium', 'chromium-browser']
                    
                    if is_chrome and proc.info['cmdline']:
                        cmdline = ' '.join(proc.info['cmdline'])
                        if 'undetected_chromedriver' in cmdline or self.base_profile_dir in cmdline:
                            logger.info(f"Terminating Chrome process: {proc.pid}")
                            proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.error(f"Error cleaning up Chrome processes: {str(e)}")
    
    async def _init_chrome(self, profile_path: str) -> uc.Chrome:
        """Инициализирует Chrome с оптимальными настройками"""
        loop = asyncio.get_event_loop()
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                # Создаем драйвер в отдельной функции, чтобы выполнить его в другом потоке
                def create_driver():
                    options = uc.ChromeOptions()
                    
                    # Основные параметры запуска
                    options.add_argument('--no-sandbox')
                    options.add_argument(f'--user-data-dir={profile_path}')
                    options.add_argument('--start-maximized')
                    options.add_argument('--window-position=0,0')
                    
                    # Отключаем ненужные функции
                    options.add_argument('--disable-dev-shm-usage')
                    options.add_argument('--disable-extensions')
                    options.add_argument('--disable-background-mode')
                    options.add_argument('--disable-popup-blocking')
                    options.add_argument('--disable-notifications')
                    options.add_argument('--disable-infobars')
                    options.add_argument('--disable-gpu') # Особенно важно для Linux VPS
                    
                    # Оптимизации производительности
                    options.add_argument('--autoplay-policy=no-user-gesture-required')
                    options.add_argument('--disable-background-networking')
                    options.add_argument('--disable-background-timer-throttling')
                    options.add_argument('--disable-client-side-phishing-detection')
                    options.add_argument('--disable-component-update')
                    options.add_argument('--no-first-run')
                    options.add_argument('--no-default-browser-check')
                    
                    # Выбираем случайный порт для отладки
                    import random
                    debug_port = random.randint(9222, 9999)
                    options.add_argument(f'--remote-debugging-port={debug_port}')
                    
                    # Всегда используем headless режим
                    headless = True
                    
                    try:
                        driver = uc.Chrome(
                            options=options,
                            headless=headless,
                            use_subprocess=True,
                            driver_executable_path=None,
                            version_main=133,  # Явно указываем версию Chrome 133
                            no_sandbox=True
                        )
                        return driver
                    except Exception as e:
                        logger.error(f"Chrome initialization error: {str(e)}")
                        raise

                # Запускаем создание драйвера в отдельном потоке
                driver = await loop.run_in_executor(None, create_driver)
                
                # Устанавливаем разумные тайм-ауты
                driver.implicitly_wait(10)
                driver.set_page_load_timeout(30)
                
                return driver
                
            except Exception as e:
                logger.error(f"Failed to initialize Chrome (attempt {attempt+1}/{max_attempts}): {str(e)}")
                
                # Если это последняя попытка, вызываем исключение
                if attempt == max_attempts - 1:
                    raise
                
                # Иначе чистим процессы и пробуем снова
                await self._cleanup_chrome_processes()
                await asyncio.sleep(5)
    
    async def get_account(self, account_id: str) -> Optional[WhatsAppAccount]:
        """Получает учетную запись WhatsApp по ID"""
        result = await self.db.execute(
            select(WhatsAppAccount).where(WhatsAppAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def initialize_session(
        self, account: WhatsAppAccount, wait_time: int = 60
    ) -> Dict:
        """Инициализирует сессию WhatsApp и возвращает QR-код для сканирования"""
        result = {
            "success": False,
            "account_id": account.id,
            "status": account.status,
            "error": None,
            "qr_code": None
        }

        # Создаем путь к профилю
        profile_path = self._get_profile_path(account.profile_name)
        account.profile_path = profile_path
        await self.db.commit()
        
        # Полностью сбрасываем статус аутентификации в Redis (удаляем QR-код и метку авторизации)
        await reset_auth_status(account.id)
        
        driver = None
        try:
            # Определяем нужно ли создавать новый профиль
            new_profile = False
            if account.status not in [WhatsAppAccountStatus.ACTIVE, WhatsAppAccountStatus.INITIALIZED]:
                if os.path.exists(profile_path):
                    import shutil
                    try:
                        shutil.rmtree(profile_path)
                        new_profile = True
                    except Exception as e:
                        logger.warning(f"Failed to clean profile directory: {str(e)}")
                else:
                    new_profile = True
                
                if new_profile:
                    os.makedirs(profile_path, exist_ok=True)
            
            # Инициализируем Chrome
            driver = await self._init_chrome(profile_path)
            
            # Открываем WhatsApp Web
            driver.get("https://web.whatsapp.com/")
            await asyncio.sleep(3)  # Даем странице немного времени загрузиться
            
            # Устанавливаем таймеры
            start_time = time.time()
            qr_found = False
            qr_disappeared = False
            authenticated = False
            
            # Обновляем статус аккаунта
            account.status = WhatsAppAccountStatus.PENDING
            await self.db.commit()
            
            # Делаем скриншот начального состояния
            try:
                screenshot_path = os.path.join(profile_path, f"init_screenshot_{int(time.time())}.png")
                driver.save_screenshot(screenshot_path)
                logger.info(f"Init screenshot saved to {screenshot_path}")
            except Exception as e:
                logger.warning(f"Failed to save init screenshot: {str(e)}")
            
            # Основной цикл проверки
            while time.time() - start_time < wait_time:
                try:
                    # Проверяем наличие QR кода
                    qr_elements = driver.find_elements(By.TAG_NAME, "canvas")
                    
                    # Если QR код найден и еще не был сохранен
                    if qr_elements and not qr_found:
                        # Извлекаем QR код как Base64 изображение
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
                            # Сохраняем QR код в Redis
                            await set_qr_code(account.id, qr_base64, expire=120)
                            
                            # Проверяем, что QR код сохранился корректно
                            saved_qr = await get_qr_code(account.id)
                            if saved_qr:
                                result["qr_code"] = qr_base64
                                qr_found = True
                                logger.info(f"QR code generated for account {account.id}")
                    
                    # Ключевая проверка: QR код был, но исчез
                    if qr_found and not qr_elements:
                        logger.info(f"QR code disappeared for account {account.id} - checking for authenticated state")
                        qr_disappeared = True
                        
                        # Даем небольшую паузу для загрузки интерфейса
                        await asyncio.sleep(2)
                    
                    # Проверяем наличие характерных элементов интерфейса WhatsApp
                    if qr_disappeared or (not qr_elements and not new_profile):
                        # Делаем скриншот для проверки
                        try:
                            screenshot_path = os.path.join(profile_path, f"auth_screenshot_{int(time.time())}.png")
                            driver.save_screenshot(screenshot_path)
                            logger.info(f"Auth screenshot saved to {screenshot_path}")
                        except Exception as e:
                            logger.warning(f"Failed to save auth screenshot: {str(e)}")
                        
                        # Проверяем наличие элементов интерфейса - любой из этих селекторов должен существовать
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
                    
                    # Если пользователь авторизован
                    if authenticated or qr_disappeared:
                        logger.info(f"WhatsApp account {account.id} authenticated")
                        
                        # Удаляем QR код из Redis и устанавливаем флаг аутентификации
                        await delete_qr_code(account.id)
                        
                        # Обновляем статус аккаунта
                        account.status = WhatsAppAccountStatus.ACTIVE
                        if not account.account_metadata:
                            account.account_metadata = {}
                        account.account_metadata["last_active"] = datetime.now().isoformat()
                        await self.db.commit()
                        
                        # ИЗМЕНЕНИЕ: Установка флага для фронтенда, чтобы закрыть модальное окно
                        result["success"] = True
                        result["status"] = WhatsAppAccountStatus.ACTIVE
                        result["authenticated"] = True  # Явный флаг для фронтенда
                        
                        # Для устранения проблемы с "зависшими" браузерами,
                        # принудительно закрываем браузер после успешной аутентификации
                        try:
                            driver.quit()
                            logger.info(f"Browser closed after successful authentication for account {account.id}")
                        except Exception as e:
                            logger.warning(f"Error closing browser: {str(e)}")
                        
                        # Сбрасываем кеш браузера
                        async with self._browser_pool_lock:
                            if profile_path in self._browser_pool:
                                del self._browser_pool[profile_path]
                        
                        return result
                
                except Exception as e:
                    logger.debug(f"Error during initialization check: {str(e)}")
                
                # Небольшая пауза перед следующей проверкой
                await asyncio.sleep(1)
            
            # Если вышло время ожидания
            if not result["success"]:
                logger.warning(f"Session initialization timeout for account {account.id}")
                if qr_found:
                    result["error"] = "QR code was not scanned in time"
                else:
                    result["error"] = "Failed to generate QR code"
                
                # Если QR код был найден, оставляем статус PENDING
                # В противном случае устанавливаем статус ERROR
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
            # ИЗМЕНЕНИЕ: Если мы не аутентифицировались, закрываем браузер для экономии ресурсов
            if driver and not result.get("authenticated", False):
                try:
                    driver.quit()
                except Exception as e:
                    logger.warning(f"Error closing driver: {str(e)}")
        
        return result

    async def _get_or_create_browser(self, profile_path: str) -> uc.Chrome:
        """Получает существующий браузер из пула или создает новый"""
        async with self._browser_pool_lock:
            if profile_path in self._browser_pool:
                browser = self._browser_pool[profile_path]
                try:
                    # Проверяем, что браузер жив
                    browser.current_url
                    return browser
                except Exception as e:
                    logger.warning(f"Browser from pool is dead, creating new one: {str(e)}")
                    # Браузер мертв, удаляем из пула
                    try:
                        browser.quit()
                    except:
                        pass
                    del self._browser_pool[profile_path]
            
            # Создаем новый браузер
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
        """Создает запись в истории сообщений"""
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
        """Получает историю сообщений"""
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
        existing_driver: Optional[uc.Chrome] = None,
        close_driver: bool = True
    ) -> Dict:
        """Отправляет сообщение WhatsApp"""
        # Получаем запись сообщения, если указан message_id
        message = None
        if message_id:
            result = await self.db.execute(
                select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
            )
            message = result.scalar_one_or_none()
            if not message:
                logger.error(f"Message {message_id} not found")
                raise ValueError(f"Message {message_id} not found")
        
        # Если message_id не указан, создаем новую запись
        if not message:
            message = await self.create_message_history(account, recipient)
        
        # Готовим результат
        result = {
            "success": False,
            "account_id": account.id,
            "recipient": recipient.phone,
            "message_id": message.id,
            "error": None,
            "timestamp": datetime.now()
        }
        
        # Проверяем, готов ли аккаунт
        if not account.is_ready:
            result["error"] = "Account is not active or not initialized"
            message.status = WhatsAppMessageStatus.ERROR
            message.error_message = result["error"]
            await self.db.commit()
            return result
        
        driver = existing_driver
        profile_path = account.profile_path or self._get_profile_path(account.profile_name)
        browser_created = False
        
        try:
            # Используем существующий драйвер или создаем новый
            if driver is None:
                # Получаем или создаем браузер из пула
                driver = await self._get_or_create_browser(profile_path)
                browser_created = True
            
            # Формируем прямую ссылку для отправки сообщения
            message_text = str(recipient.message)
            direct_url = (
                f"https://web.whatsapp.com/send?phone={recipient.phone.replace('+', '')}"
                f"&text={quote(message_text)}"
            )
            
            # Переходим по ссылке
            driver.get(direct_url)
            
            # Инициализируем переменные для отслеживания состояния отправки
            message_sent = False
            button_found = False  # Инициализируем переменную до её использования
            
            try:
                # Таймер для измерения времени загрузки
                load_start_time = time.time()
                
                # JavaScript для быстрого поиска и клика по кнопке отправки
                send_button_js = """
                function clickSendButton() {
                    // Приоритетные селекторы
                    const selectors = [
                        'span[data-icon="send"]', 
                        'div[data-icon="send"]',
                        'div[aria-label="Send"]',
                        'button.send'
                    ];
                    
                    // Ищем кнопку отправки
                    for (const selector of selectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            if (el && el.offsetParent !== null) {
                                // Элемент видим - нажимаем
                                el.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
                return clickSendButton();
                """
                
                # JavaScript для оптимальной отправки сообщения с паузой
                two_phase_send_js = """
                // Функция поиска кнопки отправки
                function findSendButton() {
                    // Проверяем базовые ошибки
                    const app = document.querySelector('#app');
                    if (!app) return { status: 'WAIT', message: 'App not loaded' };
                    
                    // Проверяем ошибки номера
                    if (document.body.innerText.includes('Phone number shared via url is invalid')) {
                        return { status: 'ERROR', message: 'Invalid phone number' };
                    }
                    
                    // Проверяем наличие QR-кода
                    const qrCanvas = document.querySelector('canvas');
                    if (qrCanvas) return { status: 'ERROR', message: 'WhatsApp account not authenticated' };
                    
                    // Проверим, загружен ли чат
                    const chatPanel = document.querySelector('[data-testid="conversation-panel"]');
                    
                    // Приоритетный поиск кнопки отправки (без клика)
                    const sendSelectors = [
                        'span[data-icon="send"]', 
                        'div[data-icon="send"]',
                        'button.send',
                        'div[aria-label="Send"]', 
                        '[role="button"][aria-label="Send"]',
                        '[data-testid="send"]'
                    ];
                    
                    for (const selector of sendSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            if (el && el.offsetParent !== null) {
                                return { status: 'BUTTON_FOUND', message: 'Send button found' };
                            }
                        }
                    }
                    
                    // Если кнопка не найдена, но чат загружен
                    if (chatPanel) {
                        return { status: 'CHAT_READY', message: 'Chat loaded, but send button not found yet' };
                    }
                    
                    return { status: 'WAIT', message: 'Waiting for chat to load' };
                }

                // Функция выполнения клика по кнопке отправки
                function clickSendButton() {
                    const sendSelectors = [
                        'span[data-icon="send"]', 
                        'div[data-icon="send"]',
                        'button.send',
                        'div[aria-label="Send"]', 
                        '[role="button"][aria-label="Send"]',
                        '[data-testid="send"]'
                    ];
                    
                    for (const selector of sendSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            if (el && el.offsetParent !== null) {
                                try {
                                    el.click();
                                    return { status: 'SUCCESS', message: 'Message sent' };
                                } catch (e) {
                                    // Игнорируем ошибки клика
                                }
                            }
                        }
                    }
                    
                    return { status: 'ERROR', message: 'Failed to click send button' };
                }
                
                return JSON.stringify(findSendButton());
                """
                
                # Немедленно начинаем проверку загрузки (без предварительных ожиданий)
                try:
                    # Делаем скриншот для отладки (не блокируя основной процесс)
                    screenshot_path = os.path.join(profile_path, f"send_message_{int(time.time())}.png")
                    driver.save_screenshot(screenshot_path)
                    logger.info(f"Screenshot saved to {screenshot_path}")
                except Exception as e:
                    logger.warning(f"Failed to save screenshot: {str(e)}")
                
                # Оптимизированный подход с паузой перед отправкой
                max_poll_time = 30  # до 30 секунд на все попытки для надежности
                poll_start = time.time()
                poll_attempts = 0
                
                # Фаза 1: Ожидаем загрузки чата и поиск кнопки отправки
                while time.time() - poll_start < max_poll_time and not message_sent and not button_found:
                    try:
                        poll_attempts += 1
                        js_result = driver.execute_script(two_phase_send_js)
                        
                        try:
                            # Пытаемся распарсить результат как JSON
                            result_obj = json.loads(js_result)
                            status = result_obj.get('status', '')
                            message_info = result_obj.get('message', '')
                            
                            if status == 'BUTTON_FOUND':
                                logger.info(f"Send button found after {poll_attempts} attempts")
                                button_found = True
                                break
                                
                            elif status == 'ERROR':
                                if "Invalid phone number" in message_info:
                                    raise ValueError(f"Invalid phone number: {recipient.phone}")
                                if "WhatsApp account not authenticated" in message_info:
                                    raise Exception("WhatsApp account not authenticated")
                                logger.debug(f"JS Error: {message_info}")
                                
                            elif status == 'CHAT_READY' and poll_attempts % 10 == 0:  # Логируем не слишком часто
                                logger.info(f"Chat loaded in {time.time() - load_start_time:.2f}s, searching for send button")
                        except json.JSONDecodeError:
                            # Если не удалось распарсить как JSON, обрабатываем как строку
                            logger.debug(f"Non-JSON response: {js_result}")
                        
                        # Очень короткая пауза между попытками поиска кнопки
                        await asyncio.sleep(0.5)
                        
                    except ValueError as e:
                        # Явная ошибка с номером телефона - прекращаем попытки
                        logger.error(f"Invalid phone number: {str(e)}")
                        result["error"] = str(e)
                        message.status = WhatsAppMessageStatus.ERROR
                        message.error_message = result["error"]
                        await self.db.commit()
                        raise
                        
                    except Exception as loop_error:
                        # Другие ошибки логируем, но продолжаем попытки
                        logger.debug(f"Error in polling loop: {str(loop_error)}")
                
                # Фаза 2: Если кнопка найдена, выполняем отправку сообщения
                if button_found:
                    logger.info("Waiting 0.2 seconds before sending message")
                    await asyncio.sleep(0.2)  # Минимальная пауза для стабилизации интерфейса
                    
                    # Метод 1: Отправка через JavaScript
                    try:
                        click_send_js = """
                        function clickSendButton() {
                            const selectors = [
                                'span[data-icon="send"]', 
                                'div[data-icon="send"]',
                                'button.send',
                                'div[aria-label="Send"]', 
                                '[role="button"][aria-label="Send"]',
                                '[data-testid="send"]'
                            ];
                            
                            for (const selector of selectors) {
                                const elements = document.querySelectorAll(selector);
                                for (const el of elements) {
                                    if (el && el.offsetParent !== null) {
                                        el.click();
                                        return true;
                                    }
                                }
                            }
                            return false;
                        }
                        return clickSendButton();
                        """
                        
                        result_js = driver.execute_script(click_send_js)
                        if result_js:
                            logger.info("Message sent via JavaScript with delay")
                            message_sent = True
                    except Exception as e:
                        logger.warning(f"Error sending via JavaScript with delay: {str(e)}")
                    
                    # Метод 2: Отправка через Enter (если JavaScript не сработал)
                    if not message_sent:
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
                                    # Фокус на элементе
                                    driver.execute_script("arguments[0].focus();", inputs[0])
                                    
                                    # Отправляем Enter
                                    from selenium.webdriver.common.keys import Keys
                                    from selenium.webdriver.common.action_chains import ActionChains
                                    actions = ActionChains(driver)
                                    actions.send_keys(Keys.ENTER)
                                    actions.perform()
                                    logger.info("Message sent via Enter key")
                                    message_sent = True
                                    break
                        except Exception as e:
                            logger.warning(f"Error sending via Enter key: {str(e)}")
                    
                    # Метод 3: Клик через Selenium Actions (если предыдущие не сработали)
                    if not message_sent:
                        try:
                            send_button_selectors = [
                                'span[data-icon="send"]', 
                                'div[data-icon="send"]',
                                'button.send',
                                'div[aria-label="Send"]'
                            ]
                            
                            for selector in send_button_selectors:
                                buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                                if buttons and len(buttons) > 0:
                                    from selenium.webdriver.common.action_chains import ActionChains
                                    actions = ActionChains(driver)
                                    actions.move_to_element(buttons[0])
                                    actions.click()
                                    actions.perform()
                                    logger.info(f"Message sent via Selenium click on {selector}")
                                    message_sent = True
                                    break
                        except Exception as e:
                            logger.warning(f"Error sending via Selenium click: {str(e)}")
                    
                    # Ожидаем 2 секунды для завершения отправки
                    await asyncio.sleep(0.5)
                
                
                # Дополнительная проверка фактической отправки сообщения
                if message_sent:
                    # Дополнительная пауза для гарантии отправки
                    await asyncio.sleep(0.5)
                    
                    # Проверяем, что поле ввода очистилось - признак успешной отправки
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
                                if not inputs[0].text.strip():
                                    input_empty = True
                                    logger.info("Input field is empty - message likely sent")
                                    break
                    except Exception as e:
                        logger.warning(f"Error checking input field: {str(e)}")
                    
                    # Проверяем наличие меток доставки
                    delivery_markers = False
                    try:
                        markers = driver.find_elements(By.CSS_SELECTOR, 
                            '[data-icon="msg-check"], [data-icon="msg-dblcheck"], .message-out .status-check')
                        if markers and len(markers) > 0:
                            delivery_markers = True
                            logger.info("Found delivery confirmation markers")
                    except Exception as e:
                        logger.warning(f"Error checking delivery markers: {str(e)}")
                    
                    # Если есть хотя бы один признак успешной отправки
                    if input_empty or delivery_markers:
                        result["success"] = True
                        message.status = WhatsAppMessageStatus.SENT
                        if not message.message_metadata:
                            message.message_metadata = {}
                        message.message_metadata["sent_at"] = datetime.now().isoformat()
                        
                        # Обновляем метаданные аккаунта
                        if not account.account_metadata:
                            account.account_metadata = {}
                        account.account_metadata["last_message_sent"] = datetime.now().isoformat()
                        account.account_metadata["last_active"] = datetime.now().isoformat()
                        
                        await self.db.commit()
                        logger.info(f"Message sent successfully to {recipient.phone} (empty_input={input_empty}, markers={delivery_markers})")
                    else:
                        # Если нет признаков успешной отправки
                        result["success"] = False
                        message.status = WhatsAppMessageStatus.ERROR
                        message.error_message = "No confirmation of successful message delivery"
                        await self.db.commit()
                        logger.warning(f"No delivery confirmation for message to {recipient.phone}")
                else:
                    if button_found:
                        logger.warning(f"Button was found but message couldn't be sent after {time.time() - poll_start:.2f}s")
                        result["error"] = "Failed to click send button after finding it"
                    else:
                        logger.warning(f"Failed to find send button after {time.time() - poll_start:.2f}s of trying")
                        result["error"] = "Failed to find send button"
                    
                    message.status = WhatsAppMessageStatus.ERROR
                    message.error_message = result["error"]
                    await self.db.commit()
                
            except Exception as e:
                # Обрабатываем ошибки и устанавливаем статус сообщения
                logger.error(f"Error sending WhatsApp message: {str(e)}")
                result["error"] = str(e)
                message.status = WhatsAppMessageStatus.ERROR
                message.error_message = result["error"]
                await self.db.commit()
                
                # Не выбрасываем исключение - просто возвращаем результат с ошибкой
                
        except Exception as e:
            # Общие ошибки
            logger.error(f"Message sending error: {str(e)}")
            result["error"] = f"Message sending failed: {str(e)}"
            message.status = WhatsAppMessageStatus.ERROR
            message.error_message = result["error"]
            
            # Проверяем, не потеряли ли мы соединение
            if isinstance(e, WebDriverException) and "not reachable" in str(e).lower():
                account.status = WhatsAppAccountStatus.ERROR
                account.set_error("Browser connection lost")
            
            await self.db.commit()
            
            # В случае критической ошибки, закрываем браузер
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                # Удаляем из пула
                async with self._browser_pool_lock:
                    if account.profile_path in self._browser_pool:
                        del self._browser_pool[account.profile_path]
        
        finally:
            # Закрываем браузер только если мы его создали и нужно закрыть
            if driver and close_driver and browser_created:
                try:
                    driver.quit()
                    logger.info(f"Browser closed after sending message to {recipient.phone}")
                except Exception as e:
                    logger.warning(f"Error closing browser: {str(e)}")
                
                # Удаляем из пула
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
        """Отправляет массовые сообщения с оптимизированной задержкой между ними"""
        results = []
        
        logger.info(f"Starting bulk send for account {account.id}, {len(recipients)} messages")
        
        # Получаем путь к профилю
        profile_path = account.profile_path or self._get_profile_path(account.profile_name)
        
        # Создаем один браузер для всех сообщений
        driver = None
        try:
            # Инициализируем браузер один раз для всех сообщений
            driver = await self._get_or_create_browser(profile_path)
            
            for i, recipient in enumerate(recipients):
                logger.info(f"Processing message {i+1}/{len(recipients)} to {recipient.phone}")
                # Получаем ID сообщения, если они были переданы
                message_id = message_ids[i] if message_ids and i < len(message_ids) else None
                
                try:
                    # Используем общий браузер для всех сообщений и не закрываем его между отправками
                    result = await self.send_message(
                        account=account,
                        recipient=recipient,
                        message_id=message_id,
                        wait_time=wait_time,
                        existing_driver=driver,
                        close_driver=False  # Не закрываем браузер между сообщениями
                    )
                    
                    # Логируем результат внутри блока try
                    if result.get('success', False):
                        logger.info(f"Message {i+1} sent successfully")
                    else:
                        logger.error(f"Message {i+1} error: {result.get('error', 'Unknown error')}")
                    
                    results.append(result)
                    
                    # Минимальная задержка между сообщениями
                    if i < len(recipients) - 1:  # Пропускаем задержку после последнего сообщения
                        import random
                        delay = random.uniform(1, 2)  # Минимальная необходимая пауза
                        logger.info(f"Waiting {delay:.2f} seconds before next message")
                        await asyncio.sleep(delay)
                
                except Exception as e:
                    logger.error(f"Error sending message {i+1}: {str(e)}")
                    # Добавляем информацию об ошибке в результат
                    results.append({
                        "success": False,
                        "account_id": account.id,
                        "recipient": recipient.phone,
                        "message_id": message_id,
                        "error": f"Exception: {str(e)}",
                        "timestamp": datetime.now()
                    })
                    
                    # Увеличиваем задержку после ошибки, но не после последнего сообщения
                    if i < len(recipients) - 1:
                        await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error during bulk send: {str(e)}")
        finally:
            # Дополнительная пауза для гарантии отправки последнего сообщения
            await asyncio.sleep(5)
            logger.info("Final pause before closing browser")
            
            # Закрываем браузер только после отправки всех сообщений
            if driver:
                try:
                    # Проверяем, все ли сообщения успешно отправлены
                    success_count = sum(1 for r in results if r.get('success', False))
                    logger.info(f"Success count before closing browser: {success_count}/{len(results)}")
                    
                    driver.quit()
                    logger.info("Browser closed after completing bulk send")
                except Exception as e:
                    logger.warning(f"Error closing browser after bulk send: {str(e)}")
                
                # Удаляем из пула
                async with self._browser_pool_lock:
                    if profile_path in self._browser_pool:
                        del self._browser_pool[profile_path]
        
        logger.info(f"Bulk send completed. Success: {sum(1 for r in results if r.get('success', False))}/{len(results)}")
        return results

    async def delete_account(self, account: WhatsAppAccount) -> bool:
        """Удаляет учетную запись WhatsApp и все связанные данные"""
        try:
            # Удаляем все связанные сообщения
            result = await self.db.execute(
                select(WhatsAppMessage).where(WhatsAppMessage.account_id == account.id)
            )
            messages = result.scalars().all()
            for message in messages:
                await self.db.delete(message)
            
            # Закрываем и удаляем браузер из пула, если есть
            profile_path = account.profile_path
            if profile_path and profile_path in self._browser_pool:
                try:
                    self._browser_pool[profile_path].quit()
                except:
                    pass
                async with self._browser_pool_lock:
                    if profile_path in self._browser_pool:
                        del self._browser_pool[profile_path]
            
            # Удаляем профиль Chrome
            profile_path = self._get_profile_path(account.profile_name)
            if os.path.exists(profile_path):
                import shutil
                try:
                    shutil.rmtree(profile_path)
                except Exception as e:
                    logger.warning(f"Failed to delete profile directory: {str(e)}")
            
            # Удаляем QR код из Redis
            await delete_qr_code(account.id)
            
            # Удаляем запись аккаунта
            await self.db.delete(account)
            await self.db.commit()
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete account {account.id}: {str(e)}")
            await self.db.rollback()
            return False
    
    async def check_account_status(self, account: WhatsAppAccount) -> Dict:
        """Проверяет статус аккаунта WhatsApp"""
        driver = None
        try:
            # Проверяем путь к профилю
            if not account.profile_path:
                account.profile_path = self._get_profile_path(account.profile_name)
                await self.db.commit()
            
            # Получаем или создаем браузер
            driver = await self._get_or_create_browser(account.profile_path)
            
            # Проверяем, открыт ли WhatsApp Web
            if not driver.current_url.startswith("https://web.whatsapp.com"):
                driver.get("https://web.whatsapp.com/")
                await asyncio.sleep(5)  # Даем время загрузиться
            
            # Проверяем наличие QR-кода
            qr_elements = driver.find_elements(By.TAG_NAME, "canvas")
            
            # Проверяем наличие элементов интерфейса
            chat_elements = driver.find_elements(By.CSS_SELECTOR, 
                "#app, #main, .app, .two, [data-testid='conversation-panel'], " +
                "[data-testid='chat-list'], .landing-wrapper")
                
            # Проверяем наличие индикаторов загрузки или ошибок
            loading_elements = driver.find_elements(By.CSS_SELECTOR, 
                ".landing-main, [data-testid='intro-text'], .landing-title")
                
            # Если есть QR-код - ждем авторизации
            if qr_elements:
                # Аккаунт не авторизован, но QR-код есть
                account.status = WhatsAppAccountStatus.PENDING
                await self.db.commit()
                
                return {
                    "status": WhatsAppAccountStatus.PENDING,
                    "is_connected": False,
                    "qr_available": True,
                    "last_check": datetime.now().isoformat()
                }
            
            # Если есть элементы чата и нет QR-кода - авторизованы
            elif chat_elements and not qr_elements and not loading_elements:
                # Аккаунт активен
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
            
            # Страница загружается или в неизвестном состоянии
            else:
                return {
                    "status": account.status,
                    "is_connected": False,
                    "is_loading": bool(loading_elements),
                    "last_check": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error checking account status: {str(e)}")
            
            # В случае ошибки, возможно, нужно переинициализировать
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
        
    async def logout(self, account: WhatsAppAccount) -> bool:
        """Выполняет выход из аккаунта WhatsApp"""
        driver = None
        try:
            if not account.profile_path:
                account.profile_path = self._get_profile_path(account.profile_name)
            
            # Получаем или создаем браузер
            driver = await self._get_or_create_browser(account.profile_path)
            
            # Переходим на страницу WhatsApp
            driver.get("https://web.whatsapp.com/")
            await asyncio.sleep(5)
            
            # Находим и нажимаем кнопку меню
            try:
                # Сначала ищем новый интерфейс
                menu_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='menu'] svg, span[data-icon='menu']"))
                )
                menu_button.click()
                await asyncio.sleep(1)
                
                # Ищем и нажимаем кнопку выхода
                logout_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@aria-label, 'Log out') or contains(text(), 'Log out')]"))
                )
                logout_button.click()
                await asyncio.sleep(1)
                
                # Подтверждаем выход
                confirm_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@aria-label, 'OK') or contains(text(), 'OK')]"))
                )
                confirm_button.click()
                await asyncio.sleep(3)
                
                # Закрываем браузер
                driver.quit()
                
                # Удаляем браузер из пула
                async with self._browser_pool_lock:
                    if account.profile_path in self._browser_pool:
                        del self._browser_pool[account.profile_path]
                
                # Обновляем статус аккаунта
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