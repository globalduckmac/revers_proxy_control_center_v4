import asyncio
import logging
import functools
import time
from typing import Callable, Any, TypeVar, Optional, Union, List, Dict

logger = logging.getLogger(__name__)

T = TypeVar('T')

class RetryError(Exception):
    """Exception raised when all retry attempts fail."""
    def __init__(self, original_exception, attempts):
        self.original_exception = original_exception
        self.attempts = attempts
        super().__init__(f"Failed after {attempts} attempts. Last error: {original_exception}")


async def async_retry(
    func: Callable[..., Any],
    *args,
    max_attempts: int = 3,
    retry_delay: float = 2.0,
    backoff_factor: float = 1.5,
    exceptions: Union[List[Exception], Exception] = Exception,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs
) -> Any:
    """
    Retry an asynchronous function with exponential backoff.
    
    Args:
        func: Async function to retry
        *args: Arguments to pass to the function
        max_attempts: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Exception or list of exceptions to catch and retry on
        on_retry: Optional callback function called on each retry with attempt number and exception
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        The return value of the function
        
    Raises:
        RetryError: If all retry attempts fail
    """
    if not asyncio.iscoroutinefunction(func):
        raise ValueError(f"Function {func.__name__} is not a coroutine function")
    
    if isinstance(exceptions, type) and issubclass(exceptions, Exception):
        exceptions = [exceptions]
    
    attempt = 0
    current_delay = retry_delay
    last_exception = None
    
    while attempt < max_attempts:
        try:
            return await func(*args, **kwargs)
        except tuple(exceptions) as e:
            attempt += 1
            last_exception = e
            
            if attempt >= max_attempts:
                break
                
            if on_retry:
                on_retry(attempt, e)
                
            logger.warning(
                f"Retry {attempt}/{max_attempts} for {func.__name__} after error: {str(e)}. "
                f"Waiting {current_delay:.2f}s before next attempt."
            )
            
            await asyncio.sleep(current_delay)
            current_delay *= backoff_factor
    
    raise RetryError(last_exception, max_attempts)


def async_retry_decorator(
    max_attempts: int = 3,
    retry_delay: float = 2.0,
    backoff_factor: float = 1.5,
    exceptions: Union[List[Exception], Exception] = Exception,
    on_retry: Optional[Callable[[int, Exception], None]] = None
) -> Callable:
    """
    Decorator for retrying async functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Exception or list of exceptions to catch and retry on
        on_retry: Optional callback function called on each retry with attempt number and exception
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await async_retry(
                func,
                *args,
                max_attempts=max_attempts,
                retry_delay=retry_delay,
                backoff_factor=backoff_factor,
                exceptions=exceptions,
                on_retry=on_retry,
                **kwargs
            )
        return wrapper
    return decorator


def retry(
    func: Callable[..., Any],
    *args,
    max_attempts: int = 3,
    retry_delay: float = 2.0,
    backoff_factor: float = 1.5,
    exceptions: Union[List[Exception], Exception] = Exception,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs
) -> Any:
    """
    Retry a synchronous function with exponential backoff.
    
    Args:
        func: Function to retry
        *args: Arguments to pass to the function
        max_attempts: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Exception or list of exceptions to catch and retry on
        on_retry: Optional callback function called on each retry with attempt number and exception
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        The return value of the function
        
    Raises:
        RetryError: If all retry attempts fail
    """
    if isinstance(exceptions, type) and issubclass(exceptions, Exception):
        exceptions = [exceptions]
    
    attempt = 0
    current_delay = retry_delay
    last_exception = None
    
    while attempt < max_attempts:
        try:
            return func(*args, **kwargs)
        except tuple(exceptions) as e:
            attempt += 1
            last_exception = e
            
            if attempt >= max_attempts:
                break
                
            if on_retry:
                on_retry(attempt, e)
                
            logger.warning(
                f"Retry {attempt}/{max_attempts} for {func.__name__} after error: {str(e)}. "
                f"Waiting {current_delay:.2f}s before next attempt."
            )
            
            time.sleep(current_delay)
            current_delay *= backoff_factor
    
    raise RetryError(last_exception, max_attempts)


def retry_decorator(
    max_attempts: int = 3,
    retry_delay: float = 2.0,
    backoff_factor: float = 1.5,
    exceptions: Union[List[Exception], Exception] = Exception,
    on_retry: Optional[Callable[[int, Exception], None]] = None
) -> Callable:
    """
    Decorator for retrying synchronous functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Exception or list of exceptions to catch and retry on
        on_retry: Optional callback function called on each retry with attempt number and exception
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return retry(
                func,
                *args,
                max_attempts=max_attempts,
                retry_delay=retry_delay,
                backoff_factor=backoff_factor,
                exceptions=exceptions,
                on_retry=on_retry,
                **kwargs
            )
        return wrapper
    return decorator
