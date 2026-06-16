"""Shared type definitions - NewType aliases used by all layers."""

from typing import NewType

BaseId = NewType("BaseId", str)
SceneId = NewType("SceneId", str)
ObjectCode = NewType("ObjectCode", str)
ViewCode = NewType("ViewCode", str)
RelationCode = NewType("RelationCode", str)
ActionCode = NewType("ActionCode", str)
