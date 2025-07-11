"""
Centralized logging configuration for factcheck-scrapers.

This module provides consistent logging configuration across all components
of the factcheck-scrapers package, including colored console output.
"""

import logging
import logging.handlers
import os
import sys
from typing import Optional

# Define project root function here to avoid circular imports
def get_project_root() -> str:
    """Get the project root directory."""
    # Start from the current file's directory and go up one level
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ANSI color codes
class Colors:
    RESET = '\033[0m'
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Custom formatter for colored output
class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: Colors.BLUE,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BOLD + Colors.RED,
    }

    def format(self, record):
        # Save the original format
        format_orig = self._style._fmt
        
        # Add color to the levelname
        color = self.COLORS.get(record.levelno, Colors.RESET)
        
        # Add emoji indicators based on log level
        emoji = ""
        if record.levelno == logging.INFO:
            emoji = "✅ "
        elif record.levelno == logging.WARNING:
            emoji = "⚠️ "
        elif record.levelno == logging.ERROR or record.levelno == logging.CRITICAL:
            emoji = "❌ "
        
        # Apply color to the whole message for better visibility
        self._style._fmt = format_orig.replace('%(levelname)s', f'{color}%(levelname)s{Colors.RESET}')
        
        # Format the message
        result = logging.Formatter.format(self, record)
        
        # Add emoji to the formatted message
        if emoji and "%(message)s" in format_orig:
            result = result.replace(record.message, f"{emoji}{record.message}")
            
        # Restore the original format
        self._style._fmt = format_orig
        
        return result

# Default log format
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Log levels
LOG_LEVELS = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL
}

def setup_logging(
    component: str,
    level: str = 'info',
    log_file: Optional[str] = None,
    console: bool = True,
    log_format: str = DEFAULT_LOG_FORMAT,
    max_bytes: int = 10485760,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Set up logging for a component with file and/or console handlers.
    
    Args:
        component: Name of the component (used as logger name)
        level: Log level (debug, info, warning, error, critical)
        log_file: Optional path to log file. If None, logs to console only.
        console: Whether to log to console
        log_format: Log format string
        max_bytes: Maximum size in bytes for log files before rotation
        backup_count: Number of backup log files to keep
        
    Returns:
        Logger: Configured logger
    """
    # Convert string level to logging level
    log_level = LOG_LEVELS.get(level.lower(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger(component)
    logger.setLevel(log_level)
    logger.handlers = []  # Clear any existing handlers
    
    # Create formatters
    file_formatter = logging.Formatter(log_format)
    color_formatter = ColoredFormatter(log_format)
    
    # Add console handler if requested
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(color_formatter)  # Use colored formatter for console
        logger.addHandler(console_handler)
    
    # Add file handler if log_file is specified
    if log_file:
        # If the log file path is not absolute, make it relative to the project root
        if not os.path.isabs(log_file):
            log_dir = os.path.join(get_project_root(), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, log_file)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setFormatter(file_formatter)  # Use plain formatter for files
        logger.addHandler(file_handler)
    
    return logger

def get_logger(component: str) -> logging.Logger:
    """
    Get a logger for a component. If the logger doesn't exist, it will be created
    with default settings.
    
    Args:
        component: Name of the component
        
    Returns:
        Logger: Logger for the component
    """
    logger = logging.getLogger(component)
    
    # If the logger doesn't have handlers, set up with default settings
    if not logger.handlers:
        return setup_logging(component)
    
    return logger