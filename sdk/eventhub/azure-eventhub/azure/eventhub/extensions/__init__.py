# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# Extend path to include extensions from other packages (e.g., checkpoint stores)
# This is needed for editable installs where pkgutil.extend_path doesn't work with custom finders
import sys as _sys
import os as _os

__path__ = __import__("pkgutil").extend_path(__path__, __name__)  # type: ignore

# Manually add site-packages extensions path for editable install compatibility
for _p in _sys.path:
    _ext_path = _os.path.join(_p, "azure", "eventhub", "extensions")
    if _os.path.isdir(_ext_path) and _ext_path not in __path__:
        __path__.append(_ext_path)
