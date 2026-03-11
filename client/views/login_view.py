"""Phase-5 login view shim.

This module keeps backward compatibility while exposing the required
`login_view.py` entry point from next phase requirements.
"""

from .auth_view import AuthenticationView, CharacterSelectView

__all__ = ["AuthenticationView", "CharacterSelectView"]
