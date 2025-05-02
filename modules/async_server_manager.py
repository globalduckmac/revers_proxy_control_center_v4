import logging
import asyncio
import asyncssh
import os
import tempfile
from models import Server, db

logger = logging.getLogger(__name__)

CONNECTION_POOL = {}

class AsyncServerManager:
    """
    Handles asynchronous SSH operations for server management.
    """
    
    @staticmethod
    async def get_ssh_connection(server):
        """
        Get an SSH connection to the server, reusing existing connections when possible.
        
        Args:
            server: Server model instance
            
        Returns:
            SSHClientConnection: An established SSH connection
        """
        if server.id in CONNECTION_POOL and CONNECTION_POOL[server.id]['conn'] is not None:
            try:
                await CONNECTION_POOL[server.id]['conn'].run('echo "Connection test"')
                logger.debug(f"Reusing existing SSH connection for server {server.name}")
                return CONNECTION_POOL[server.id]['conn']
            except Exception as e:
                logger.warning(f"Existing SSH connection for server {server.name} is no longer valid: {str(e)}")
                CONNECTION_POOL[server.id]['conn'].close()
                del CONNECTION_POOL[server.id]
        
        logger.info(f"Establishing new SSH connection to server {server.name} ({server.ip_address})")
        
        connect_kwargs = {
            'host': server.ip_address,
            'port': server.ssh_port,
            'username': server.ssh_user,
            'known_hosts': None  # Skip known hosts check
        }
        
        if server.ssh_password:
            connect_kwargs['password'] = server.ssh_password
        elif server.ssh_key_path:
            try:
                with open(server.ssh_key_path, 'r') as key_file:
                    private_key = key_file.read()
                connect_kwargs['client_keys'] = [asyncssh.import_private_key(private_key)]
            except Exception as e:
                logger.error(f"Error loading SSH key from {server.ssh_key_path}: {str(e)}")
                raise
        else:
            logger.error(f"No authentication method provided for server {server.name}")
            raise ValueError("No authentication method provided")
        
        try:
            conn = await asyncssh.connect(**connect_kwargs)
            
            CONNECTION_POOL[server.id] = {
                'conn': conn,
                'last_used': asyncio.get_event_loop().time()
            }
            
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to server {server.name}: {str(e)}")
            raise
    
    @staticmethod
    async def execute_command(server, command, capture_output=False):
        """
        Execute a command via SSH.
        
        Args:
            server: Server model instance
            command: Command string to execute
            capture_output: Whether to capture and return the output
            
        Returns:
            str: Command output if capture_output is True, otherwise None
        """
        logger.info(f"Executing command on server {server.name}: {command}")
        
        conn = await AsyncServerManager.get_ssh_connection(server)
        
        try:
            result = await conn.run(command)
            
            if result.exit_status != 0:
                logger.warning(f"Command exited with non-zero status {result.exit_status} on server {server.name}: {command}")
                logger.warning(f"Stderr: {result.stderr}")
            
            if capture_output:
                return result.stdout
            
            return None
        except Exception as e:
            logger.error(f"Error executing command on server {server.name}: {str(e)}")
            raise
    
    @staticmethod
    async def execute_command_streaming(server, command, callback=None):
        """
        Execute a command via SSH and stream the output in real-time.
        
        Args:
            server: Server model instance
            command: Command string to execute
            callback: Optional async callback function for streaming output
            
        Returns:
            dict: Dictionary with command output and exit code
        """
        logger.info(f"Executing streaming command on server {server.name}: {command}")
        
        conn = await AsyncServerManager.get_ssh_connection(server)
        
        try:
            process = await conn.create_process(command)
            combined_output = []
            exit_code = None
            
            while True:
                line = await process.stdout.readline()
                if not line:
                    line = await process.stderr.readline()
                    if not line:
                        break
                
                line_str = line.decode('utf-8', errors='replace').rstrip()
                combined_output.append(line_str)
                
                if callback:
                    await callback({
                        "status": "info",
                        "step": "command_output",
                        "message": line_str
                    })
            
            exit_code = await process.wait()
            
            result = {
                "output": "\n".join(combined_output),
                "exit_code": exit_code
            }
            
            return result
            
        except Exception as e:
            error_msg = f"Error executing streaming command on {server.name}: {str(e)}"
            logger.error(error_msg)
            
            if callback:
                await callback({
                    "status": "error",
                    "step": "command_error",
                    "message": error_msg
                })
            
            return {
                "output": "",
                "error": str(e),
                "exit_code": 1
            }
    
    @staticmethod
    async def upload_string_to_file(server, content, remote_path):
        """
        Upload a string to a file on the server.
        
        Args:
            server: Server model instance
            content: String content to upload
            remote_path: Remote file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Uploading string to file {remote_path} on server {server.name}")
        
        conn = await AsyncServerManager.get_ssh_connection(server)
        
        try:
            async with conn.start_sftp_client() as sftp:
                async with sftp.open(remote_path, 'w') as f:
                    await f.write(content)
            
            return True
        except Exception as e:
            logger.error(f"Error uploading string to file on server {server.name}: {str(e)}")
            raise
    
    @staticmethod
    async def download_file(server, remote_path, local_path=None):
        """
        Download a file from the server.
        
        Args:
            server: Server model instance
            remote_path: Remote file path
            local_path: Local file path (optional, if None a temp file will be created)
            
        Returns:
            str: Local file path
        """
        logger.info(f"Downloading file {remote_path} from server {server.name}")
        
        conn = await AsyncServerManager.get_ssh_connection(server)
        
        try:
            if local_path is None:
                fd, local_path = tempfile.mkstemp()
                os.close(fd)
            
            async with conn.start_sftp_client() as sftp:
                await sftp.get(remote_path, local_path)
            
            return local_path
        except Exception as e:
            logger.error(f"Error downloading file from server {server.name}: {str(e)}")
            raise
    
    @staticmethod
    async def close_all_connections():
        """
        Close all SSH connections in the pool.
        """
        logger.info(f"Closing all SSH connections ({len(CONNECTION_POOL)} connections)")
        
        for server_id, conn_data in CONNECTION_POOL.items():
            try:
                conn_data['conn'].close()
                logger.debug(f"Closed SSH connection for server ID {server_id}")
            except Exception as e:
                logger.warning(f"Error closing SSH connection for server ID {server_id}: {str(e)}")
        
        CONNECTION_POOL.clear()

import atexit

def cleanup_connections():
    """Close all SSH connections on exit."""
    if CONNECTION_POOL:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(AsyncServerManager.close_all_connections())
        finally:
            loop.close()

atexit.register(cleanup_connections)
