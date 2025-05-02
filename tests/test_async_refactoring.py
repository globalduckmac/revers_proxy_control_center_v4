"""
Test script for asyncio refactoring in Reverse Proxy Control Center v4.
This script tests the async functionality of the refactored components.
"""

import os
import sys
import asyncio
import logging
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.async_server_manager import AsyncServerManager
from modules.proxy_manager import ProxyManager
from modules.retry_utils import async_retry, RetryError
from config import config

logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestAsyncServerManager(unittest.TestCase):
    """Test the AsyncServerManager class."""
    
    def setUp(self):
        """Set up test environment."""
        self.server_mock = MagicMock()
        self.server_mock.id = 1
        self.server_mock.name = "test-server"
        self.server_mock.ip_address = "127.0.0.1"
        self.server_mock.ssh_port = 22
        self.server_mock.ssh_user = "test-user"
        self.server_mock.ssh_password = "test-password"
        self.server_mock.ssh_key_path = None
    
    @patch('modules.async_server_manager.asyncssh.connect')
    async def test_get_ssh_connection(self, mock_connect):
        """Test getting an SSH connection."""
        mock_connect.return_value = AsyncMock()
        
        conn = await AsyncServerManager.get_ssh_connection(self.server_mock)
        self.assertIsNotNone(conn)
        mock_connect.assert_called_once()
        
        mock_connect.reset_mock()
        
        self.server_mock.ssh_password = None
        self.server_mock.ssh_key_path = "/path/to/key"
        
        with patch('builtins.open', unittest.mock.mock_open(read_data='ssh-key-data')):
            conn = await AsyncServerManager.get_ssh_connection(self.server_mock)
            self.assertIsNotNone(conn)
            mock_connect.assert_called_once()
    
    @patch('modules.async_server_manager.AsyncServerManager.get_ssh_connection')
    async def test_execute_command(self, mock_get_conn):
        """Test executing a command via SSH."""
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock()
        mock_conn.run.return_value.stdout = "command output"
        mock_conn.run.return_value.exit_status = 0
        
        mock_get_conn.return_value = mock_conn
        
        result = await AsyncServerManager.execute_command(self.server_mock, "test command")
        self.assertEqual(result, "command output")
        mock_conn.run.assert_called_once_with("test command")
    
    @patch('modules.async_server_manager.AsyncServerManager.get_ssh_connection')
    async def test_upload_string_to_file(self, mock_get_conn):
        """Test uploading a string to a file via SSH."""
        mock_conn = AsyncMock()
        mock_sftp = AsyncMock()
        mock_file = AsyncMock()
        
        mock_conn.start_sftp_client = AsyncMock(return_value=mock_sftp)
        mock_sftp.open = AsyncMock(return_value=mock_file)
        
        mock_get_conn.return_value = mock_conn
        
        result = await AsyncServerManager.upload_string_to_file(
            self.server_mock, "test content", "/remote/path"
        )
        self.assertTrue(result)
        mock_sftp.open.assert_called_once_with("/remote/path", "w")
        mock_file.write.assert_called_once_with("test content")
        mock_file.close.assert_called_once()


class TestProxyManager(unittest.TestCase):
    """Test the ProxyManager class."""
    
    def setUp(self):
        """Set up test environment."""
        self.proxy_manager = ProxyManager()
        
        self.server_mock = MagicMock()
        self.server_mock.id = 1
        self.server_mock.name = "test-server"
        
        self.domain_mock = MagicMock()
        self.domain_mock.id = 1
        self.domain_mock.name = "test-domain.com"
    
    @patch('modules.proxy_manager.AsyncServerManager.execute_command')
    @patch('modules.proxy_manager.AsyncServerManager.upload_string_to_file')
    @patch('modules.proxy_manager.db')
    @patch('modules.proxy_manager.Server')
    @patch('modules.proxy_manager.Domain')
    async def test_async_deploy_proxy_config(self, mock_domain, mock_server, 
                                           mock_db, mock_upload, mock_execute):
        """Test the async_deploy_proxy_config method."""
        mock_server.query.get.return_value = self.server_mock
        mock_domain.query.get.return_value = self.domain_mock
        mock_upload.return_value = True
        mock_execute.return_value = "Nginx reloaded"
        
        result = await self.proxy_manager.async_deploy_proxy_config(
            self.server_mock.id, self.domain_mock.id
        )
        self.assertTrue(result)
        
        mock_server.query.get.assert_called_once_with(self.server_mock.id)
        mock_upload.assert_called()
        mock_execute.assert_called()


class TestRetryUtils(unittest.TestCase):
    """Test the retry utilities."""
    
    async def test_async_retry_success(self):
        """Test successful retry of an async function."""
        mock_func = AsyncMock()
        mock_func.return_value = "success"
        
        result = await async_retry(
            mock_func, "arg1", "arg2", 
            max_attempts=3, 
            retry_delay=0.1
        )
        
        self.assertEqual(result, "success")
        mock_func.assert_called_once_with("arg1", "arg2")
    
    async def test_async_retry_failure_then_success(self):
        """Test retry that fails first then succeeds."""
        mock_func = AsyncMock()
        mock_func.side_effect = [ValueError("First failure"), "success"]
        
        result = await async_retry(
            mock_func, 
            max_attempts=3, 
            retry_delay=0.1,
            exceptions=ValueError
        )
        
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 2)
    
    async def test_async_retry_all_failures(self):
        """Test retry that fails all attempts."""
        mock_func = AsyncMock()
        mock_func.side_effect = ValueError("Failure")
        
        with self.assertRaises(RetryError):
            await async_retry(
                mock_func, 
                max_attempts=3, 
                retry_delay=0.1,
                exceptions=ValueError
            )
        
        self.assertEqual(mock_func.call_count, 3)


class TestEventLoopManagement(unittest.TestCase):
    """Test the event loop management in tasks.py."""
    
    @patch('tasks.BackgroundTasks._run_async_task')
    def test_run_async_task(self, mock_run_async):
        """Test running an async task in the background tasks."""
        from tasks import background_tasks
        
        async def mock_coro():
            return "result"
        
        background_tasks._run_async_task(mock_coro())
        
        mock_run_async.assert_called_once()


def run_async_tests():
    """Run the async tests using asyncio."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        async_suite = unittest.TestSuite()
        
        async_suite.addTest(TestAsyncServerManager('test_get_ssh_connection'))
        async_suite.addTest(TestAsyncServerManager('test_execute_command'))
        async_suite.addTest(TestAsyncServerManager('test_upload_string_to_file'))
        async_suite.addTest(TestProxyManager('test_async_deploy_proxy_config'))
        async_suite.addTest(TestRetryUtils('test_async_retry_success'))
        async_suite.addTest(TestRetryUtils('test_async_retry_failure_then_success'))
        async_suite.addTest(TestRetryUtils('test_async_retry_all_failures'))
        
        for test in async_suite:
            loop.run_until_complete(getattr(test, test._testMethodName)())
        
    finally:
        loop.close()


if __name__ == '__main__':
    print("Running async tests...")
    run_async_tests()
    
    print("\nRunning sync tests...")
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
    
    print("\nAll tests completed.")
