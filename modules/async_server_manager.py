import asyncio
import asyncssh
import logging
import io
import tempfile
import os
from datetime import datetime
from models import Server, ServerLog, db

logger = logging.getLogger(__name__)

CONNECTION_POOL = {}

class AsyncServerManager:
    """
    Handles operations related to server management using asyncio.
    Provides async alternatives to ServerManager methods.
    """
    
    @staticmethod
    async def get_ssh_connection(server):
        """
        Get or create an SSH connection from the pool.
        
        Args:
            server: Server model instance
            
        Returns:
            asyncssh.SSHClientConnection: Connected SSH client
        """
        conn_key = f"{server.ip_address}:{server.ssh_port}:{server.ssh_user}"
        
        if conn_key in CONNECTION_POOL and CONNECTION_POOL[conn_key]["client"].is_connected():
            logger.info(f"Reusing existing SSH connection for server {server.name}")
            return CONNECTION_POOL[conn_key]["client"]
        
        logger.info(f"Creating new SSH connection for server {server.name} ({server.ip_address})")
        
        options = {
            "keepalive_interval": 30,
            "keepalive_count_max": 5
        }
        
        if server.ssh_key:
            key_file = None
            
            try:
                fd, key_path = tempfile.mkstemp()
                with os.fdopen(fd, 'w') as tmp:
                    tmp.write(server.ssh_key)
                
                os.chmod(key_path, 0o600)
                
                client = await asyncssh.connect(
                    host=server.ip_address, 
                    port=server.ssh_port,
                    username=server.ssh_user,
                    client_keys=[key_path],
                    known_hosts=None,
                    **options
                )
                
                key_file = key_path
                
            except Exception as e:
                logger.error(f"Failed to connect with SSH key for server {server.name}: {str(e)}")
                if key_path:
                    try:
                        os.remove(key_path)
                    except:
                        pass
                raise
        else:
            ssh_password = server.ssh_password
            
            if not ssh_password:
                logger.error(f"SSH password not available for server {server.name}")
                raise ValueError("SSH password not available")
            
            try:
                client = await asyncssh.connect(
                    host=server.ip_address, 
                    port=server.ssh_port,
                    username=server.ssh_user,
                    password=ssh_password,
                    known_hosts=None,
                    **options
                )
                key_file = None
            except Exception as e:
                logger.error(f"Failed to connect with password for server {server.name}: {str(e)}")
                raise
        
        CONNECTION_POOL[conn_key] = {
            "client": client,
            "key_file": key_file,
            "created_at": datetime.utcnow()
        }
        
        return client
    
    @staticmethod
    async def execute_command(server, command, timeout=60):
        """
        Execute a command on the server asynchronously.
        
        Args:
            server: Server model instance
            command: String command to execute
            timeout: Command timeout in seconds
            
        Returns:
            tuple: (stdout, stderr) output from command
        """
        logger.info(f"Executing command on {server.name} ({server.ip_address}): {command}")
        
        try:
            conn = await AsyncServerManager.get_ssh_connection(server)
            
            result = await asyncio.wait_for(conn.run(command), timeout=timeout)
            
            stdout = result.stdout
            stderr = result.stderr
            
            log = ServerLog(
                server_id=server.id,
                action='command_execution',
                status='success' if result.exit_status == 0 else 'warning',
                message=f"Command: {command}\nExit Status: {result.exit_status}\nOutput: {stdout}\nErrors: {stderr}"
            )
            
            db.session.add(log)
            await asyncio.to_thread(db.session.commit)
            
            return stdout, stderr
            
        except (asyncio.TimeoutError, asyncssh.Error) as e:
            log = ServerLog(
                server_id=server.id,
                action='command_execution',
                status='error',
                message=f"Command execution failed: {command}\nError: {str(e)}"
            )
            
            db.session.add(log)
            await asyncio.to_thread(db.session.commit)
            
            logger.error(f"Command execution failed on server {server.name}: {str(e)}")
            raise
    
    @staticmethod
    async def upload_string_to_file(server, content, remote_path):
        """
        Upload a string content to a file on the server asynchronously.
        
        Args:
            server: Server model instance
            content: String content to upload
            remote_path: Destination path on server
            
        Returns:
            bool: True if successful
        """
        try:
            needs_sudo = remote_path.startswith('/etc/') or remote_path.startswith('/usr/')
            
            if needs_sudo:
                temp_path = f"/tmp/nginx_config_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                
                conn = await AsyncServerManager.get_ssh_connection(server)
                
                async with conn.start_sftp_client() as sftp:
                    await sftp.put_file(io.StringIO(content), temp_path)
                
                await AsyncServerManager.execute_command(
                    server,
                    f"sudo cp {temp_path} {remote_path} && sudo chmod 644 {remote_path} && rm {temp_path}"
                )
            else:
                conn = await AsyncServerManager.get_ssh_connection(server)
                
                async with conn.start_sftp_client() as sftp:
                    await sftp.put_file(io.StringIO(content), remote_path)
            
            log = ServerLog(
                server_id=server.id,
                action='file_creation',
                status='success',
                message=f"File created asynchronously: {remote_path}"
            )
            
            db.session.add(log)
            await asyncio.to_thread(db.session.commit)
            
            return True
            
        except Exception as e:
            log = ServerLog(
                server_id=server.id,
                action='file_creation',
                status='error',
                message=f"File creation failed: {remote_path}\nError: {str(e)}"
            )
            
            db.session.add(log)
            await asyncio.to_thread(db.session.commit)
            
            logger.error(f"File creation failed on server {server.name}: {str(e)}")
            raise
            
    @staticmethod
    async def close_connections():
        """Close all pooled connections and clean up temporary files."""
        for key, conn_data in list(CONNECTION_POOL.items()):
            try:
                if conn_data["client"].is_connected():
                    conn_data["client"].close()
                
                if conn_data["key_file"]:
                    try:
                        os.remove(conn_data["key_file"])
                    except:
                        pass
                
                del CONNECTION_POOL[key]
            except Exception as e:
                logger.error(f"Error closing connection {key}: {str(e)}")
