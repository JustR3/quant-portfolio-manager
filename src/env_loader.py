"""
Environment Variable Loader

Automatically loads environment variables from config/secrets.env at module import.
This ensures API keys (FRED, Alpha Vantage, etc.) are available throughout the application.

Usage:
    # Just import this module anywhere - variables are auto-loaded
    import src.env_loader
    
    # Or import it at the top of your main application file
    from src import env_loader
"""

import os
from pathlib import Path
from typing import Optional

# Try to import dotenv, but don't fail if not installed
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


def load_environment_variables(env_file: Optional[str] = None, verbose: bool = False) -> bool:
    """
    Load environment variables from .env file.
    
    Args:
        env_file: Path to .env file (default: config/secrets.env)
        verbose: Print debug information
    
    Returns:
        True if environment variables were loaded, False otherwise
    """
    if not HAS_DOTENV:
        if verbose:
            print("⚠️  python-dotenv not installed. Environment variables must be set manually.")
            print("   Install with: uv pip install python-dotenv")
        return False
    
    # Default to config/secrets.env in project root
    if env_file is None:
        project_root = Path(__file__).parent.parent
        env_file = project_root / "config" / "secrets.env"
    else:
        env_file = Path(env_file)
    
    # Check if file exists
    if not env_file.exists():
        if verbose:
            print(f"⚠️  Environment file not found: {env_file}")
            print("   Create config/secrets.env with your API keys")
        return False
    
    # Load environment variables
    load_dotenv(env_file, override=False)  # Don't override existing env vars
    
    if verbose:
        print(f"✓ Loaded environment variables from {env_file}")
        
        # Show which keys were loaded (without exposing values)
        keys_loaded = []
        for key in ["FRED_API_KEY", "ALPHA_VANTAGE_KEY"]:
            if os.getenv(key):
                keys_loaded.append(f"{key} ({len(os.getenv(key))} chars)")
        
        if keys_loaded:
            print(f"  Available keys: {', '.join(keys_loaded)}")
    
    return True


# Auto-load on module import
_loaded = load_environment_variables(verbose=False)

# Provide a way for other modules to check if env was loaded
def is_environment_loaded() -> bool:
    """Check if environment variables were successfully loaded."""
    return _loaded


def get_api_key(key_name: str, required: bool = False) -> Optional[str]:
    """
    Get an API key from environment variables.
    
    Args:
        key_name: Name of the environment variable (e.g., 'FRED_API_KEY')
        required: If True, raise ValueError if key not found
    
    Returns:
        API key value or None if not found
    
    Raises:
        ValueError: If required=True and key not found
    """
    value = os.getenv(key_name)
    
    if value is None and required:
        raise ValueError(
            f"{key_name} not found in environment. "
            f"Add it to config/secrets.env or set it manually:\n"
            f"export {key_name}=your_key_here"
        )
    
    return value


__all__ = [
    "load_environment_variables",
    "is_environment_loaded",
    "get_api_key",
]
