import paramiko
import logging
import socket
from datetime import datetime
from models import Server, ServerLog, db

logger = logging.getLogger(__name__)

class ServerManager:
    """
    Handles operations related to server management including
    connectivity checks, SSH connections, and server status updates.
    """
    
    @staticmethod
    def check_connectivity(server):
        """
        Check if the server is reachable via SSH.
        
        Args:
            server: Server model instance
            
        Returns:
            bool: True if server is reachable, False otherwise
        """
        logger.info(f"Checking connectivity for server {server.name} ({server.ip_address})")
        
        try:
            # Create SSH client
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to server with a timeout
            if server.ssh_key:
                key_file = paramiko.RSAKey.from_private_key(server.ssh_key)
                client.connect(
                    hostname=server.ip_address,
                    port=server.ssh_port,
                    username=server.ssh_user,
                    pkey=key_file,
                    timeout=10
                )
            else:
                # Use password-based authentication if no key provided
                client.connect(
                    hostname=server.ip_address,
                    port=server.ssh_port,
                    username=server.ssh_user,
                    password=server.ssh_password,
                    timeout=10
                )
            
            # Execute a simple command to verify connection
            stdin, stdout, stderr = client.exec_command("echo 'Connectivity test successful'")
            output = stdout.read().decode('utf-8').strip()
            
            # Close connection
            client.close()
            
            # Update server status and last check time
            server.status = 'active'
            server.last_check = datetime.utcnow()
            
            # Log success
            log = ServerLog(
                server_id=server.id,
                action='connectivity_check',
                status='success',
                message=f"Server is reachable: {output}"
            )
            
            db.session.add(log)
            db.session.commit()
            
            logger.info(f"Connectivity check successful for server {server.name}")
            return True
            
        except (paramiko.SSHException, socket.error, Exception) as e:
            # Update server status
            server.status = 'error'
            server.last_check = datetime.utcnow()
            
            # Log error
            log = ServerLog(
                server_id=server.id,
                action='connectivity_check',
                status='error',
                message=f"Server connection failed: {str(e)}"
            )
            
            db.session.add(log)
            db.session.commit()
            
            logger.error(f"Connectivity check failed for server {server.name}: {str(e)}")
            return False
    
    @staticmethod
    def get_ssh_client(server):
        """
        Get an SSH client connected to the specified server.
        
        Args:
            server: Server model instance
            
        Returns:
            paramiko.SSHClient: Connected SSH client
        
        Raises:
            Exception: If connection fails
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Get timeout from config or use default
            from flask import current_app
            connection_timeout = current_app.config.get('SSH_TIMEOUT', 60)  # Default 1 minute
            
            logger.info(f"Connecting to server {server.name} ({server.ip_address}), timeout: {connection_timeout}s")
            
            if server.ssh_key:
                key_file = paramiko.RSAKey.from_private_key(server.ssh_key)
                client.connect(
                    hostname=server.ip_address,
                    port=server.ssh_port,
                    username=server.ssh_user,
                    pkey=key_file,
                    timeout=connection_timeout
                )
            else:
                # Use password-based authentication
                client.connect(
                    hostname=server.ip_address,
                    port=server.ssh_port,
                    username=server.ssh_user,
                    password=server.ssh_password,
                    timeout=connection_timeout
                )
            
            return client
        
        except Exception as e:
            logger.error(f"Failed to connect to server {server.name} ({server.ip_address}): {str(e)}")
            raise
    
    @staticmethod
    def execute_command(server, command, timeout=None, long_running=False):
        """
        Execute a command on the server.
        
        Args:
            server: Server model instance
            command: String command to execute
            timeout: Override default timeout value (in seconds)
            long_running: If True, use the extended command timeout
            
        Returns:
            tuple: (stdout, stderr) output from command
            
        Raises:
            Exception: If command execution fails
        """
        # Load the appropriate timeout value
        from flask import current_app
        if timeout is None:
            if long_running:
                timeout = current_app.config.get('SSH_COMMAND_TIMEOUT', 300)  # Default 5 minutes for long commands
            else:
                timeout = current_app.config.get('SSH_TIMEOUT', 60)  # Default 1 minute
        
        logger.info(f"Executing command on {server.name} ({server.ip_address}): {command} (timeout: {timeout}s)")
        
        try:
            client = ServerManager.get_ssh_client(server)
            # Set timeout for this command
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            
            # Get command output
            stdout_str = stdout.read().decode('utf-8')
            stderr_str = stderr.read().decode('utf-8')
            
            # Check exit status
            exit_status = stdout.channel.recv_exit_status()
            status = 'success' if exit_status == 0 else 'warning'
            
            # Close connection
            client.close()
            
            # Log command execution
            log = ServerLog(
                server_id=server.id,
                action='command_execution',
                status=status,
                message=f"Command: {command}\nExit Status: {exit_status}\nOutput: {stdout_str}\nErrors: {stderr_str}"
            )
            
            db.session.add(log)
            db.session.commit()
            
            return stdout_str, stderr_str
            
        except Exception as e:
            logger.exception(f"Error executing command on {server.name}: {command}")
            # Log error
            log = ServerLog(
                server_id=server.id,
                action='command_execution',
                status='error',
                message=f"Command execution failed: {command}\nError: {str(e)}"
            )
            
            db.session.add(log)
            db.session.commit()
            
            logger.error(f"Command execution failed on server {server.name}: {str(e)}")
            raise
    
    @staticmethod
    def upload_file(server, local_path, remote_path):
        """
        Upload a file to the server.
        
        Args:
            server: Server model instance
            local_path: Path to local file
            remote_path: Destination path on server
            
        Returns:
            bool: True if successful
            
        Raises:
            Exception: If file upload fails
        """
        try:
            client = ServerManager.get_ssh_client(server)
            
            # Open SFTP session
            sftp = client.open_sftp()
            
            # Upload file
            sftp.put(local_path, remote_path)
            
            # Close SFTP session and connection
            sftp.close()
            client.close()
            
            # Log file upload
            log = ServerLog(
                server_id=server.id,
                action='file_upload',
                status='success',
                message=f"File uploaded: {local_path} -> {remote_path}"
            )
            
            db.session.add(log)
            db.session.commit()
            
            return True
            
        except Exception as e:
            # Log error
            log = ServerLog(
                server_id=server.id,
                action='file_upload',
                status='error',
                message=f"File upload failed: {local_path} -> {remote_path}\nError: {str(e)}"
            )
            
            db.session.add(log)
            db.session.commit()
            
            logger.error(f"File upload failed on server {server.name}: {str(e)}")
            raise
    
    @staticmethod
    def upload_string_to_file(server, content, remote_path):
        """
        Upload a string content to a file on the server.
        
        Args:
            server: Server model instance
            content: String content to upload
            remote_path: Destination path on server
            
        Returns:
            bool: True if successful
            
        Raises:
            Exception: If upload fails
        """
        try:
            client = ServerManager.get_ssh_client(server)
            
            # Open SFTP session
            sftp = client.open_sftp()
            
            # Create file with content
            with sftp.open(remote_path, 'w') as f:
                f.write(content)
            
            # Close SFTP session and connection
            sftp.close()
            client.close()
            
            # Log file creation
            log = ServerLog(
                server_id=server.id,
                action='file_creation',
                status='success',
                message=f"File created: {remote_path}"
            )
            
            db.session.add(log)
            db.session.commit()
            
            return True
            
        except Exception as e:
            # Log error
            log = ServerLog(
                server_id=server.id,
                action='file_creation',
                status='error',
                message=f"File creation failed: {remote_path}\nError: {str(e)}"
            )
            
            db.session.add(log)
            db.session.commit()
            
            logger.error(f"File creation failed on server {server.name}: {str(e)}")
            raise
