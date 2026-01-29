"""Dynamic class loading helpers for external strategies/risk managers."""

from __future__ import annotations

import importlib
from typing import Any, Type


def load_class(path: str, base_cls: Type[Any] | None = None) -> Type[Any]:
    """Load a class from a `module:ClassName` path.

    Args:
        path: String in the form ``"module.sub:ClassName"``.
        base_cls: Optional base class to enforce via ``issubclass``.

    Returns:
        The imported class object.

    Raises:
        ValueError: If the path is malformed or does not resolve to a class.
        ImportError: If the module cannot be imported.
        TypeError: If the class does not subclass ``base_cls`` when provided.
    """

    if not path or ":" not in path:
        raise ValueError("class_path must be in the form 'module:ClassName'")

    module_name, class_name = path.split(":", 1)
    if not module_name or not class_name:
        raise ValueError("class_path must include both module and class name")

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ValueError(f"Class '{class_name}' not found in module '{module_name}'")
    if not isinstance(cls, type):
        raise ValueError(f"'{class_name}' in module '{module_name}' is not a class")
    if base_cls is not None and not issubclass(cls, base_cls):
        raise TypeError(f"{cls.__name__} must subclass {base_cls.__name__}")
    return cls


def instantiate(path: str, *, base_cls: Type[Any] | None = None, **kwargs: Any) -> Any:
    """Load a class and instantiate it with the provided kwargs.

    Args:
        path: ``module:Class`` string.
        base_cls: Optional subclass requirement.
        **kwargs: Constructor kwargs passed to the class.

    Returns:
        Instantiated object.
    """

    cls = load_class(path, base_cls=base_cls)
    return cls(**kwargs)

